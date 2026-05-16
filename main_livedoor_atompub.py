"""
ライブドアブログへ AtomPub API で1件投稿するスタンドアロンスクリプト。

既定: Supabase（trn_dmm_items）から、trn_dmm_item_blog_post_status（blog_key は livedoor:{blog_id} 固定）で
未投稿の1件を取得し、dmm_ai_review_summaries.review_digest がある作品のみ
本文に取り込み、HTML を組み立てて AtomPub で投稿する。

処理の順序:
  1) config.blog_settings.BLOG_ACCOUNT_SETTINGS[--account].enabled が True のときだけ続行
     （False ならログを出して終了コード 0）
  2) Supabase mst_blog_accounts を取得（platform=livedoor, enabled=true, account_id=--account）
     行が無い・テーブルが無い・必須列が欠ける場合はエラーで終了（.env の LIVEDOOR_* は使わない）
  3) mst_blog_accounts（platform=livedoor, enabled=true）の各行の site / service / floor に応じて
     未投稿キューを取得し livedoor.blogcms.jp へ AtomPub POST。
     本文は ①review_digest → ②パッケージ画像 → ③サンプル画像 → ④ポータル（アフィリエイト）リンク の順。
     行に service/floor が無い場合のみ、BLOG_ACCOUNT_SETTINGS の targets（または先頭行の service/floor）にフォールバック。
     --all-targets で複数行を順に試行（DRY_RUN 時も全ターゲットを試し、最初の成功で打ち切らない）

.env:
  SUPABASE_URL_{ACCOUNT}, SUPABASE_KEY_{ACCOUNT}（ACCOUNT は既定 1 → _1）
  LIVEDOOR_ARTICLE_STYLE=popular …長文レビュー風 HTML（simple で従来どおり）

使用例:
  python main_livedoor_atompub.py --service ebook --floor comic
  python main_livedoor_atompub.py --account 2 --service digital --floor videoa --draft
  python main_livedoor_atompub.py --account 1 --all-targets
    … mst_blog_accounts の livedoor 行ごとの service/floor（なければ config targets）を順に試す
  python main_livedoor_atompub.py --manual "テスト" --body "<p>HTML</p>"

手動デバッグをソースに直書きする場合:
  下の MANUAL_DEBUG_FROM_SOURCE を True にし、DEBUG_MANUAL_TITLE / DEBUG_MANUAL_BODY_HTML を編集して
  `python post_livedoor_atompub.py` のように引数なしで実行できる（--draft は併用可）。

ファイル末尾の _argv_override に、--account / --service / --floor などをリストで書いても同様に指定できる。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 手動デバッグ（ソース内指定）
# True のとき、Supabase も CLI の --manual も使わず、次の定数だけで AtomPub 投稿する。
# 運用コミット時は必ず False に戻すこと。
# ---------------------------------------------------------------------------
MANUAL_DEBUG_FROM_SOURCE = False
DEBUG_MANUAL_TITLE = "ソース内デバッグタイトル"
DEBUG_MANUAL_BODY_HTML = """<p>ここに HTML 本文を直接書けます。</p>
<p>CDATA 内に入るため、本文に <code>]]&gt;</code> 連続は避けてください。</p>"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from config.blog_settings import BLOG_ACCOUNT_SETTINGS
from db.blog_repository import (
    apply_livedoor_env_from_config,
    list_enabled_livedoor_blog_configs,
)
from db.post_repository import (
    get_ai_review_summary,
    get_next_livedoor_post,
    mark_post_as_posted,
)
from livedoor_blog.post import (
    blog_post_title_for_item,
    build_livedoor_blog_html,
    post_to_livedoor_blog,
)
from twitter_api.tweet_service import format_campaigns
from utils.blog_targets import normalize_portal_site, resolve_post_targets

logger = logging.getLogger(__name__)


def build_twitter_text(
    title: str,
    comment: str,
    summary: str,
    point: str,
    campaigns: list | None,
    affiliate_url: str,
) -> str:
    """main.py の build_twitter_text と同じ（Livedoor 用本文ブロック）。"""
    parts: list[str] = [title]
    if comment:
        parts.append(comment)
    campaign_text = format_campaigns(campaigns)
    if campaign_text:
        parts.append(campaign_text)
    return "\n\n".join(parts)


def _dry_run() -> bool:
    return os.environ.get("DRY_RUN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _livedoor_rows_with_service_floor(
    ld_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """mst_blog_accounts の site/service/floor が揃った行（投稿キュー用）。"""
    out: list[dict[str, str]] = []
    for c in ld_rows:
        if str(c.get("service") or "").strip() and str(c.get("floor") or "").strip():
            out.append(c)
    return out


def run_livedoor_one_item(
    account_id: str,
    service: str,
    floor: str,
    site: str,
    blog_key_for_status: str,
    *,
    dry: bool,
    no_mark_posted: bool,
) -> bool:
    """Supabase から1件取り AtomPub 投稿する。投稿または DRY プレビューができれば True。"""
    post = get_next_livedoor_post(
        service,
        floor,
        account_id,
        blog_key_for_status,
    )
    if not post:
        logger.info(
            "投稿対象なし（未投稿かつ review_digest あり）: account=%s service=%s floor=%s",
            account_id,
            service,
            floor,
        )
        return False

    item_id = post["id"]
    content_id = post["content_id"]
    service_pg = post["service"]
    floor_pg = post["floor"]
    affiliate_url = post["affiliate_url"]
    image_large_url = post.get("image_large_url", "")
    image_small_url = post.get("image_small_url", "")
    comment = post.get("auto_comment", "")
    summary = post.get("auto_summary", "")
    point = post.get("auto_point", "")
    campaigns = post.get("campaign") or []

    site_portal = normalize_portal_site(site, fallback="fanza")
    if site_portal == "dmm":
        portal_url = f"https://dmmportal.jp/{service_pg}/{floor_pg}/{content_id}"
    else:
        portal_url = f"https://fanzaportal.com/{floor_pg}/{content_id}"

    title = post["title"]
    ai_review = get_ai_review_summary(account_id, content_id)
    if not ai_review or not str(ai_review.get("review_digest") or "").strip():
        logger.warning(
            "review_digest なしのためスキップ: content_id=%s item_id=%s",
            content_id,
            item_id,
        )
        return False
    display_title = blog_post_title_for_item(title, post, ai_review)
    twitter_text = build_twitter_text(
        display_title,
        comment,
        summary,
        point,
        campaigns,
        affiliate_url,
    )
    body_html = build_livedoor_blog_html(
        title=display_title,
        twitter_text=twitter_text,
        affiliate_url=affiliate_url,
        portal_url=portal_url,
        image_large_url=image_large_url,
        image_small_url=image_small_url,
        summary=summary,
        point=point,
        comment=comment,
        campaigns=campaigns,
        item_row=post,
        ai_review_row=ai_review,
    )
    logger.info("Supabase 取得: %s - %s（投稿タイトル: %s）", item_id, title, display_title)

    if dry:
        logger.info("DRY_RUN: 送信せず本文先頭800文字:\n%s", body_html[:8000])
        return True

    try:
        post_to_livedoor_blog(display_title, body_html)
    except Exception as e:
        logger.exception("投稿に失敗しました: %s", e)
        sys.exit(1)

    if not no_mark_posted:
        try:
            mark_post_as_posted(item_id, account_id, blog_key=blog_key_for_status)
            logger.info("Supabase 投稿済みマーク: %s", item_id)
        except Exception as e:
            logger.exception("投稿済みマークに失敗しました（ブログは投稿済み）: %s", e)
            sys.exit(1)

    logger.info("投稿が完了しました: %s", display_title)
    return True


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="ライブドアブログ AtomPub で記事を1件投稿します。",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Supabase を使わず、タイトルと本文を直接指定する",
    )
    parser.add_argument(
        "title",
        nargs="?",
        help="--manual のとき必須。通常モードでは Supabase のタイトルを使うため不要",
    )
    parser.add_argument(
        "--account",
        default="1",
        help="Supabase 接続に使うアカウント番号（SUPABASE_URL_1 等）。既定: 1",
    )
    parser.add_argument(
        "--service",
        help="未投稿行の service（例: ebook, digital）。--all-targets 時は不要",
    )
    parser.add_argument(
        "--floor",
        help="未投稿行の floor（例: comic, videoa）。--all-targets 時は不要",
    )
    parser.add_argument(
        "--all-targets",
        action="store_true",
        help=(
            "mst_blog_accounts の livedoor 行ごと（各行の service/floor/site）を順に試し、"
            "キューがある組み合わせで投稿。行に service/floor が無いときのみ config の targets を使用"
        ),
    )
    mg = parser.add_mutually_exclusive_group()
    mg.add_argument("--body", dest="body", help="--manual 時の本文 HTML")
    mg.add_argument(
        "--body-file",
        dest="body_file",
        metavar="PATH",
        help="--manual 時、本文 HTML を UTF-8 ファイルから読み込む",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="下書きとして投稿",
    )
    parser.add_argument(
        "--no-mark-posted",
        action="store_true",
        help="投稿成功後も Supabase のブログ投稿済み（trn_dmm_item_blog_post_status）を立てない（検証用）",
    )
    args = parser.parse_args()
    logger.info(f"args: {args}")

    # 1) blog_settings: ブログジョブ対象アカウントのみ続行
    acc_cfg = BLOG_ACCOUNT_SETTINGS.get(args.account, {})
    if not acc_cfg.get("enabled"):
        logger.info(
            "account=%s は BLOG_ACCOUNT_SETTINGS.enabled=False のため終了します（投稿しません）",
            args.account,
        )
        sys.exit(0)

    if args.draft:
        os.environ["LIVEDOOR_ATOMPUB_DRAFT"] = "1"

    # 2) mst_blog_accounts（ライブドア有効行）必須
    logger.info(f"args.account: {args.account}")
    ld_rows = list_enabled_livedoor_blog_configs(args.account)
    if not ld_rows:
        logger.error(
            "mst_blog_accounts から livedoor 行を取得できませんでした。"
            " account_id=%s, platform=livedoor, enabled=true の行と、"
            "blog_id / username / api_password を確認してください。"
            " テーブル未作成の場合は db/DDL/ddl_mst_blog_accounts.sql を Supabase で実行してください。",
            args.account,
        )
        sys.exit(1)

    for i, rowc in enumerate(ld_rows):
        logger.info(
            "mst_blog_accounts livedoor[%d] blog_id=%s service=%s floor=%s site=%s memo=%s",
            i,
            rowc.get("blog_id"),
            rowc.get("service") or "",
            rowc.get("floor") or "",
            rowc.get("site") or "",
            str(rowc.get("blog_memo") or "").strip(),
        )

    apply_livedoor_env_from_config(ld_rows[0])
    blog_key_for_status = ld_rows[0]["blog_key"]

    os.environ["LIVEDOOR_BLOG_ENABLED"] = "1"
    os.environ["LIVEDOOR_POST_METHOD"] = "atompub"

    manual_from_source = False
    if MANUAL_DEBUG_FROM_SOURCE:
        if not DEBUG_MANUAL_TITLE.strip() or not str(DEBUG_MANUAL_BODY_HTML).strip():
            logger.error(
                "MANUAL_DEBUG_FROM_SOURCE 利用時は DEBUG_MANUAL_TITLE と "
                "DEBUG_MANUAL_BODY_HTML を編集してください（空不可）"
            )
            sys.exit(1)
        title = DEBUG_MANUAL_TITLE.strip()
        display_title = title
        body_html = DEBUG_MANUAL_BODY_HTML
        item_id = None
        manual_from_source = True
        logger.info("手動デバッグ: ソース内の DEBUG_MANUAL_* を使用して投稿します")

    elif args.manual:
        if not args.title:
            parser.error("--manual のときは記事タイトルを先頭の位置引数で指定してください")
        if not args.body and not args.body_file:
            parser.error("--manual のときは --body か --body-file が必要です")
        if args.body_file:
            path = os.path.abspath(args.body_file)
            with open(path, encoding="utf-8") as f:
                body_html = f.read()
        else:
            body_html = args.body or ""
        title = args.title
        display_title = title
        item_id = None
    else:
        if args.all_targets and (args.service or args.floor):
            parser.error("--all-targets のときは --service / --floor を併用しないでください")
        if not args.all_targets and (not args.service or not args.floor):
            parser.error(
                "Supabase から取得するには --service と --floor、または --all-targets を指定してください"
            )

        dry = _dry_run()
        fallback_site_norm = normalize_portal_site(
            str(acc_cfg.get("site") or "").strip(),
            fallback="fanza",
        )

        if args.all_targets:
            master_jobs = _livedoor_rows_with_service_floor(ld_rows)
            if master_jobs:
                any_done = False
                for ld_cfg in master_jobs:
                    apply_livedoor_env_from_config(ld_cfg)
                    site = normalize_portal_site(
                        ld_cfg.get("site"),
                        fallback=fallback_site_norm,
                    )
                    logger.info(
                        "ターゲット試行（mst_blog_accounts）: blog_id=%s service=%s floor=%s site=%s",
                        ld_cfg.get("blog_id"),
                        ld_cfg.get("service"),
                        ld_cfg.get("floor"),
                        site,
                    )
                    if run_livedoor_one_item(
                        args.account,
                        str(ld_cfg["service"]).strip(),
                        str(ld_cfg["floor"]).strip(),
                        site,
                        ld_cfg["blog_key"],
                        dry=dry,
                        no_mark_posted=args.no_mark_posted,
                    ):
                        any_done = True
                if not any_done:
                    sys.exit(2)
                return

            apply_livedoor_env_from_config(ld_rows[0])
            targets_list = resolve_post_targets(acc_cfg, ld_rows[0])
            if not targets_list:
                logger.error(
                    "投稿ターゲットが解決できませんでした。"
                    " mst_blog_accounts の livedoor 行に service と floor を入れるか、"
                    " BLOG_ACCOUNT_SETTINGS[%r][targets] を設定してください。",
                    args.account,
                )
                sys.exit(2)
            any_done = False
            bk0 = ld_rows[0]["blog_key"]
            for t in targets_list:
                logger.info(
                    "ターゲット試行（config targets）: service=%s floor=%s site=%s",
                    t["service"],
                    t["floor"],
                    t["site"],
                )
                if run_livedoor_one_item(
                    args.account,
                    t["service"],
                    t["floor"],
                    t["site"],
                    bk0,
                    dry=dry,
                    no_mark_posted=args.no_mark_posted,
                ):
                    any_done = True
            if not any_done:
                sys.exit(2)
            return

        rows_sf = _livedoor_rows_with_service_floor(ld_rows)
        matches = [
            c
            for c in ld_rows
            if str(c.get("service") or "").strip() == args.service
            and str(c.get("floor") or "").strip() == args.floor
        ]
        if matches:
            ld_cfg = matches[0]
        elif rows_sf:
            logger.error(
                "mst_blog_accounts に service=%s floor=%s の livedoor 行がありません。"
                " 登録済み: %s",
                args.service,
                args.floor,
                [(c.get("blog_id"), c.get("service"), c.get("floor")) for c in rows_sf],
            )
            sys.exit(1)
        else:
            ld_cfg = ld_rows[0]

        apply_livedoor_env_from_config(ld_cfg)
        site = normalize_portal_site(
            ld_cfg.get("site"),
            fallback=fallback_site_norm,
        )
        ok = run_livedoor_one_item(
            args.account,
            args.service,
            args.floor,
            site,
            ld_cfg["blog_key"],
            dry=dry,
            no_mark_posted=args.no_mark_posted,
        )
        if not ok:
            sys.exit(2)
        if dry:
            sys.exit(0)
        return

    dry = _dry_run()
    if dry:
        logger.info("DRY_RUN: 送信せず本文先頭800文字:\n%s", body_html[:8000])
        sys.exit(0)

    # 3) AtomPub POST（手動・ソース内デバッグのみ）
    try:
        post_to_livedoor_blog(display_title, body_html)
    except Exception as e:
        logger.exception("投稿に失敗しました: %s", e)
        sys.exit(1)

    if (
        not manual_from_source
        and not args.manual
        and item_id
        and not args.no_mark_posted
    ):
        try:
            mark_post_as_posted(
                item_id, args.account, blog_key=blog_key_for_status
            )
            logger.info("Supabase 投稿済みマーク: %s", item_id)
        except Exception as e:
            logger.exception("投稿済みマークに失敗しました（ブログは投稿済み）: %s", e)
            sys.exit(1)

    logger.info("投稿が完了しました: %s", display_title)


if __name__ == "__main__":
    # ターミナルに渡さず、ここに argparse と同じ並びで書く（空 [] なら通常の sys.argv）
    # 例: ["--account", "1", "--service", "ebook", "--floor", "comic", "--draft"]
    # 例: ["--manual", "タイトル", "--body", "<p>HTML</p>"]
    # _argv_override: list[str] = ["--account", "1", "--service", "ebook", "--floor", "photo", "--draft"]
    # _argv_override: list[str] = ["--account", "2", "--all-targets"]
    _argv_override: list[str] = []
    if _argv_override:
        sys.argv = [sys.argv[0]] + _argv_override
    main()
