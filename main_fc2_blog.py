"""
FC2ブログへ XML-RPC（metaWeblog.newPost）で記事を1件投稿するスタンドアロンスクリプト。

既定: Supabase（trn_dmm_items）から、trn_dmm_item_blog_post_status（blog_key は
マスタの blog_key 列、無ければ fc2:{account_id}:{blog_id}）で未投稿の1件を取得し、
dmm_ai_review_summaries.review_digest がある作品のみ本文に取り込み、HTML を組み立てて
metaWeblog.newPost で投稿する。

処理の順序:
  1) config.blog_settings.BLOG_ACCOUNT_SETTINGS[--account].enabled が True のときだけ続行
  2) Supabase mst_blog_accounts を取得（platform=fc2, enabled=true, account_id=--account）
  3) mst_blog_accounts（platform=fc2, enabled=true）の各行の site / service / floor に応じて
     未投稿キューを取得し FC2 へ XML-RPC 投稿。
     本文は livedoor と同様 ①review_digest → ②パッケージ画像 → ③サンプル画像 → ④ポータルリンク の順。
     行に service/floor が無い場合のみ、BLOG_ACCOUNT_SETTINGS の targets にフォールバック。
     --all-targets で複数行を順に試行（DRY_RUN 時も全ターゲットを試し、最初の成功で打ち切らない）

.env:
  SUPABASE_URL_{ACCOUNT}, SUPABASE_KEY_{ACCOUNT}（ACCOUNT は既定 1 → _1）
  LIVEDOOR_ARTICLE_STYLE=popular …長文レビュー風 HTML（simple で従来に近い体裁）
  DRY_RUN=1 … 投稿せず本文のみログ

使用例:
  python main_fc2_blog.py --service ebook --floor comic
  python main_fc2_blog.py --account 2 --service digital --floor videoa
  python main_fc2_blog.py --account 1 --all-targets
  python main_fc2_blog.py --manual "テスト" --body "<p>HTML</p>"
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import xmlrpc.client
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from config.blog_settings import BLOG_ACCOUNT_SETTINGS
from db.blog_repository import list_enabled_fc2_blog_configs
from db.post_repository import (
    get_ai_review_summary,
    get_next_livedoor_post,
    mark_post_as_posted,
    mark_post_failed_skip_queue,
)
from livedoor_blog.post import (
    blog_post_title_for_item,
    build_livedoor_blog_html,
)
from twitter_api.tweet_service import format_campaigns
from utils.blog_targets import normalize_portal_site, resolve_post_targets

logger = logging.getLogger(__name__)

SLEEP_SECONDS_AFTER_POST = 10


def build_twitter_text(
    title: str,
    comment: str,
    summary: str,
    point: str,
    campaigns: list | None,
    affiliate_url: str,
) -> str:
    """main_livedoor_atompub.build_twitter_text と同じ（本文ブロック用）。"""
    parts: list[str] = [title]
    if comment:
        parts.append(comment)
    campaign_text = format_campaigns(campaigns)
    if campaign_text:
        parts.append(campaign_text)
    return "\n\n".join(parts)


def meta_weblog_new_post(
    xmlrpc_url: str,
    blog_id: str,
    username: str,
    password: str,
    title: str,
    description: str,
    publish: bool,
) -> str:
    """metaWeblog.newPost を実行し、作成された postid（文字列）を返す。"""
    proxy = xmlrpc.client.ServerProxy(xmlrpc_url, allow_none=True)
    contents: dict[str, Any] = {
        "title": title,
        "description": description,
    }
    post_id = proxy.metaWeblog.newPost(
        blog_id,
        username,
        password,
        contents,
        1 if publish else 0,
    )
    return str(post_id)


def _dry_run() -> bool:
    return os.environ.get("DRY_RUN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _fc2_rows_with_service_floor(
    fc2_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """mst_blog_accounts の site/service/floor が揃った行（投稿キュー用）。"""
    out: list[dict[str, str]] = []
    for c in fc2_rows:
        if str(c.get("service") or "").strip() and str(c.get("floor") or "").strip():
            out.append(c)
    return out


def _exclude_item_after_post_failure(
    item_id: str, account_id: str, blog_key: str, screen_name: str
) -> None:
    try:
        mark_post_failed_skip_queue(item_id, account_id, blog_key=blog_key)
        logger.info(
            "投稿失敗のためキューから除外（次回は別作品）: %s - %s",
            screen_name,
            item_id,
        )
    except Exception as e:
        logger.error(
            "失敗時のキュー除外マークに失敗: %s (%s)",
            screen_name,
            e,
        )


def run_fc2_one_item(
    account_id: str,
    service: str,
    floor: str,
    site: str,
    fc2_cfg: dict[str, str],
    *,
    dry: bool,
    no_mark_posted: bool,
    publish: bool,
) -> bool:
    """Supabase から1件取り FC2 へ XML-RPC 投稿する。投稿または DRY プレビューができれば True。"""
    blog_key = fc2_cfg["blog_key"]
    post = get_next_livedoor_post(service, floor, account_id, blog_key)
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
    affiliate_url = post.get("affiliate_url") or ""
    image_large_url = post.get("image_large_url", "")
    image_small_url = post.get("image_small_url", "")
    comment = post.get("auto_comment", "")
    summary = post.get("auto_summary", "")
    point = post.get("auto_point", "")
    campaigns = post.get("campaign") or []
    title = post["title"]

    site_portal = normalize_portal_site(site, fallback="fanza")
    if site_portal == "dmm":
        portal_url = f"https://dmmportal.jp/{service_pg}/{floor_pg}/{content_id}"
    else:
        portal_url = f"https://fanzaportal.com/{floor_pg}/{content_id}"

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
        account_id=account_id,
        portal_site=site_portal,
    )
    logger.info(
        "Supabase 取得: %s - %s（投稿タイトル: %s）",
        item_id,
        title,
        display_title,
    )

    if dry:
        logger.info("DRY_RUN: 送信せず本文先頭800文字:\n%s", body_html[:8000])
        return True

    try:
        post_id = meta_weblog_new_post(
            fc2_cfg["xmlrpc_url"],
            fc2_cfg["blog_id"],
            fc2_cfg["username"],
            fc2_cfg["password"],
            display_title,
            body_html,
            publish=publish,
        )
    except xmlrpc.client.Fault as e:
        logger.exception(
            "FC2 XML-RPC Fault: account=%s item=%s faultCode=%s faultString=%s",
            account_id,
            item_id,
            e.faultCode,
            e.faultString,
        )
        _exclude_item_after_post_failure(
            item_id, account_id, blog_key, account_id
        )
        time.sleep(SLEEP_SECONDS_AFTER_POST)
        return False
    except OSError as e:
        logger.exception(
            "FC2 接続エラー: account=%s item=%s %s",
            account_id,
            item_id,
            e,
        )
        _exclude_item_after_post_failure(
            item_id, account_id, blog_key, account_id
        )
        time.sleep(SLEEP_SECONDS_AFTER_POST)
        return False
    except Exception as e:
        logger.exception(
            "FC2 投稿例外: account=%s item=%s %s",
            account_id,
            item_id,
            e,
        )
        _exclude_item_after_post_failure(
            item_id, account_id, blog_key, account_id
        )
        time.sleep(SLEEP_SECONDS_AFTER_POST)
        return False

    logger.info(
        "FC2 投稿完了: account=%s blog_key=%s item=%s postid=%s",
        account_id,
        blog_key,
        item_id,
        post_id,
    )

    if not no_mark_posted:
        try:
            mark_post_as_posted(item_id, account_id, blog_key=blog_key)
            logger.info("Supabase 投稿済みマーク: %s", item_id)
        except Exception as e:
            logger.exception(
                "投稿済みマークに失敗しました（ブログは投稿済み）: %s", e
            )
            sys.exit(1)

    logger.info("投稿が完了しました: %s", display_title)
    time.sleep(SLEEP_SECONDS_AFTER_POST)
    return True


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="FC2ブログ XML-RPC で記事を1件投稿します。",
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
            "mst_blog_accounts の fc2 行ごと（各行の service/floor/site）を順に試し、"
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
        help="下書きとして投稿（publish=0）",
    )
    parser.add_argument(
        "--no-mark-posted",
        action="store_true",
        help="投稿成功後も Supabase のブログ投稿済みを立てない（検証用）",
    )
    args = parser.parse_args()
    logger.info("args: %s", args)

    acc_cfg = BLOG_ACCOUNT_SETTINGS.get(args.account, {})
    if not acc_cfg.get("enabled"):
        logger.info(
            "account=%s は BLOG_ACCOUNT_SETTINGS.enabled=False のため終了します（投稿しません）",
            args.account,
        )
        sys.exit(0)

    fc2_rows = list_enabled_fc2_blog_configs(args.account)
    if not fc2_rows:
        logger.error(
            "mst_blog_accounts から fc2 行を取得できませんでした。"
            " account_id=%s, platform=fc2, enabled=true の行と、"
            "blog_id / username / api_password を確認してください。"
            " テーブル未作成の場合は db/DDL/ddl_mst_blog_accounts.sql を Supabase で実行してください。",
            args.account,
        )
        sys.exit(1)

    for i, rowc in enumerate(fc2_rows):
        logger.info(
            "mst_blog_accounts fc2[%d] blog_id=%s service=%s floor=%s site=%s blog_key=%s",
            i,
            rowc.get("blog_id"),
            rowc.get("service") or "",
            rowc.get("floor") or "",
            rowc.get("site") or "",
            rowc.get("blog_key") or "",
        )

    publish = not args.draft
    dry = _dry_run()

    if args.manual:
        if not args.title:
            parser.error(
                "--manual のときは記事タイトルを先頭の位置引数で指定してください"
            )
        if not args.body and not args.body_file:
            parser.error("--manual のときは --body か --body-file が必要です")
        if args.body_file:
            path = os.path.abspath(args.body_file)
            with open(path, encoding="utf-8") as f:
                body_html = f.read()
        else:
            body_html = args.body or ""
        display_title = args.title

        if dry:
            logger.info(
                "DRY_RUN: 送信せず title=%r 本文先頭800文字:\n%s",
                display_title,
                body_html[:8000],
            )
            sys.exit(0)

        fc2_cfg = fc2_rows[0]
        try:
            post_id = meta_weblog_new_post(
                fc2_cfg["xmlrpc_url"],
                fc2_cfg["blog_id"],
                fc2_cfg["username"],
                fc2_cfg["password"],
                display_title,
                body_html,
                publish=publish,
            )
        except Exception as e:
            logger.exception("投稿に失敗しました: %s", e)
            sys.exit(1)
        logger.info("手動投稿完了: postid=%s title=%s", post_id, display_title)
        return

    if args.all_targets and (args.service or args.floor):
        parser.error("--all-targets のときは --service / --floor を併用しないでください")
    if not args.all_targets and (not args.service or not args.floor):
        parser.error(
            "Supabase から取得するには --service と --floor、または --all-targets を指定してください"
        )

    fallback_site_norm = normalize_portal_site(
        str(acc_cfg.get("site") or "").strip(),
        fallback="fanza",
    )

    if args.all_targets:
        master_jobs = _fc2_rows_with_service_floor(fc2_rows)
        if master_jobs:
            any_done = False
            for fc2_cfg in master_jobs:
                site = normalize_portal_site(
                    fc2_cfg.get("site"),
                    fallback=fallback_site_norm,
                )
                logger.info(
                    "ターゲット試行（mst_blog_accounts）: blog_id=%s service=%s floor=%s site=%s",
                    fc2_cfg.get("blog_id"),
                    fc2_cfg.get("service"),
                    fc2_cfg.get("floor"),
                    site,
                )
                if run_fc2_one_item(
                    args.account,
                    str(fc2_cfg["service"]).strip(),
                    str(fc2_cfg["floor"]).strip(),
                    site,
                    fc2_cfg,
                    dry=dry,
                    no_mark_posted=args.no_mark_posted,
                    publish=publish,
                ):
                    any_done = True
            if not any_done:
                logger.info("全ターゲットで投稿対象なし。正常終了します。")
            return

        fc2_cfg = fc2_rows[0]
        targets_list = resolve_post_targets(acc_cfg, fc2_cfg)
        if not targets_list:
            logger.error(
                "投稿ターゲットが解決できませんでした。"
                " mst_blog_accounts の fc2 行に service と floor を入れるか、"
                " BLOG_ACCOUNT_SETTINGS[%r][targets] を設定してください。",
                args.account,
            )
            sys.exit(2)
        any_done = False
        for t in targets_list:
            logger.info(
                "ターゲット試行（config targets）: service=%s floor=%s site=%s",
                t["service"],
                t["floor"],
                t["site"],
            )
            if run_fc2_one_item(
                args.account,
                t["service"],
                t["floor"],
                t["site"],
                fc2_cfg,
                dry=dry,
                no_mark_posted=args.no_mark_posted,
                publish=publish,
            ):
                any_done = True
        if not any_done:
            logger.info("全ターゲットで投稿対象なし。正常終了します。")
        return

    rows_sf = _fc2_rows_with_service_floor(fc2_rows)
    matches = [
        c
        for c in fc2_rows
        if str(c.get("service") or "").strip() == args.service
        and str(c.get("floor") or "").strip() == args.floor
    ]
    if matches:
        fc2_cfg = matches[0]
    elif rows_sf:
        logger.error(
            "mst_blog_accounts に service=%s floor=%s の fc2 行がありません。"
            " 登録済み: %s",
            args.service,
            args.floor,
            [(c.get("blog_id"), c.get("service"), c.get("floor")) for c in rows_sf],
        )
        sys.exit(1)
    else:
        fc2_cfg = fc2_rows[0]

    site = normalize_portal_site(
        fc2_cfg.get("site"),
        fallback=fallback_site_norm,
    )
    ok = run_fc2_one_item(
        args.account,
        args.service,
        args.floor,
        site,
        fc2_cfg,
        dry=dry,
        no_mark_posted=args.no_mark_posted,
        publish=publish,
    )
    if dry and ok:
        sys.exit(0)


if __name__ == "__main__":
    # 例: ["--account", "1", "--service", "ebook", "--floor", "comic"]
    # 例: ["--account", "1", "--all-targets"]
    # 例: ["--manual", "タイトル", "--body", "<p>HTML</p>"]
    _argv_override: list[str] = []
    if _argv_override:
        sys.argv = [sys.argv[0]] + _argv_override
    main()
