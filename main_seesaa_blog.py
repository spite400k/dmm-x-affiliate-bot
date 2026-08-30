"""
Seesaaブログ（セイサーブログ／通称シーサー）へ XML-RPC（metaWeblog.newPost）で1件投稿する。

既定: Supabase（trn_dmm_items）から、trn_dmm_item_blog_post_status（blog_key は
mst_blog_accounts の blog_key 列、無ければ seesaa:{blog_id}）で未投稿の1件を取得し、
dmm_ai_review_summaries.review_digest がある作品のみ本文に取り込み、HTML を組み立てて投稿する。

処理の順序:
  1) config.blog_settings.BLOG_ACCOUNT_SETTINGS[--account].enabled が True のときだけ続行
  2) Supabase mst_blog_accounts（platform=seesaa, enabled=true, account_id=--account）
  3) 各行の site / service / floor に応じて未投稿キューを取得し Seesaa へ XML-RPC 投稿
     本文は livedoor / FC2 と同様 ①review_digest → ②パッケージ画像 → ③サンプル画像 → ④ポータルリンク
     FANZA / アダルト floor は利用規約のため投稿しない（DMM.com の ebook 等のみ）

mst_blog_accounts（platform=seesaa）:
  blog_id … metaWeblog の blogid（ホスト名。例: gravure.seesaa.blog。https:// 付き URL も可）
  username … アカウント登録メールアドレス
  api_password … マイブログへのログインパスワード
  xmlrpc_url … 省略時 https://blog.seesaa.jp/rpc

公式: https://faq.seesaa.net/article/376863567.html

.env:
  SUPABASE_URL_{ACCOUNT}, SUPABASE_KEY_{ACCOUNT}
  LIVEDOOR_ARTICLE_STYLE=popular … 長文レビュー風 HTML
  DRY_RUN=1 … 投稿せず本文のみログ

使用例:
  python main_seesaa_blog.py --service ebook --floor comic
  python main_seesaa_blog.py --account 1 --service ebook --floor comic --draft
  python main_seesaa_blog.py --account 1 --all-targets
  python main_seesaa_blog.py --manual "テスト" --body "<p>HTML</p>"
  python main_seesaa_blog.py --account 1 --list-blogs
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import xmlrpc.client
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from config.blog_settings import BLOG_ACCOUNT_SETTINGS
from db.blog_repository import (
    list_enabled_seesaa_blog_configs,
    normalize_seesaa_blog_id_hint,
)
from seesaa_blog.rpc import (
    is_seesaa_access_denied,
    seesaa_xmlrpc_call,
)
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
from utils.blog_targets import (
    is_adult_blog_target,
    is_adult_item_row,
    normalize_portal_site,
    resolve_post_targets,
)

logger = logging.getLogger(__name__)

SLEEP_SECONDS_AFTER_POST = 10
_resolved_blog_id_cache: dict[tuple[str, str, str], str] = {}


def _seesaa_blog_host(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    return (parsed.netloc or parsed.path.split("/")[0]).strip().lower()


def list_seesaa_blogs(
    xmlrpc_url: str, username: str, password: str
) -> list[dict[str, Any]]:
    """blogger.getUsersBlogs でアカウント配下のブログ一覧を返す。"""

    def _call(proxy: xmlrpc.client.ServerProxy) -> Any:
        # Blogger API: appkey, username, password（appkey は Seesaa では未使用）
        return proxy.blogger.getUsersBlogs("", username, password)

    blogs = seesaa_xmlrpc_call(xmlrpc_url, _call)
    if isinstance(blogs, list):
        return [b for b in blogs if isinstance(b, dict)]
    return []


def resolve_seesaa_blog_id(seesaa_cfg: dict[str, str]) -> str:
    """mst_blog_accounts の blog_id ヒントから metaWeblog 用 blogid を解決する。"""
    xmlrpc_url = seesaa_cfg["xmlrpc_url"]
    username = seesaa_cfg["username"]
    password = seesaa_cfg["password"]
    hint_raw = seesaa_cfg["blog_id"]
    hint = normalize_seesaa_blog_id_hint(hint_raw)
    cache_key = (xmlrpc_url, username, hint)
    if cache_key in _resolved_blog_id_cache:
        return _resolved_blog_id_cache[cache_key]

    try:
        blogs = list_seesaa_blogs(xmlrpc_url, username, password)
    except Exception as e:
        logger.warning(
            "blogger.getUsersBlogs に失敗したため blog_id=%r をそのまま使います: %s",
            hint,
            e,
        )
        _resolved_blog_id_cache[cache_key] = hint
        return hint

    if not blogs:
        logger.warning(
            "blogger.getUsersBlogs が空のため blog_id=%r をそのまま使います",
            hint,
        )
        _resolved_blog_id_cache[cache_key] = hint
        return hint

    hint_lower = hint.lower()

    for blog in blogs:
        blogid = str(blog.get("blogid") or "").strip()
        if blogid.lower() == hint_lower:
            _log_resolved_blog_id(hint_raw, hint, blogid, blog)
            _resolved_blog_id_cache[cache_key] = blogid
            return blogid

    for blog in blogs:
        blogid = str(blog.get("blogid") or "").strip()
        host = _seesaa_blog_host(str(blog.get("url") or ""))
        if host and (host == hint_lower or host.endswith("." + hint_lower)):
            _log_resolved_blog_id(hint_raw, hint, blogid, blog)
            _resolved_blog_id_cache[cache_key] = blogid
            return blogid

    for blog in blogs:
        blogid = str(blog.get("blogid") or "").strip()
        if hint_lower and (
            hint_lower in blogid.lower() or blogid.lower() in hint_lower
        ):
            _log_resolved_blog_id(hint_raw, hint, blogid, blog)
            _resolved_blog_id_cache[cache_key] = blogid
            return blogid

    if len(blogs) == 1:
        blog = blogs[0]
        blogid = str(blog.get("blogid") or "").strip()
        if blogid:
            logger.info(
                "blog_id=%r は一覧と一致しませんでしたが、ブログが1件のみのため blogid=%r を使用します "
                "（url=%r）",
                hint_raw,
                blogid,
                blog.get("url"),
            )
            _resolved_blog_id_cache[cache_key] = blogid
            return blogid

    available = [
        {
            "blogid": b.get("blogid"),
            "url": b.get("url"),
            "blogName": b.get("blogName"),
        }
        for b in blogs
    ]
    raise ValueError(
        f"Seesaa blog_id={hint_raw!r}（正規化: {hint!r}）に一致するブログがありません。"
        f" --list-blogs で確認してください。利用可能: {available}"
    )


def _log_resolved_blog_id(
    hint_raw: str, hint: str, blogid: str, blog: dict[str, Any]
) -> None:
    if blogid.lower() != hint.lower() or hint_raw != hint:
        logger.info(
            "Seesaa blog_id を解決: 設定=%r → blogid=%r（url=%r, name=%r）",
            hint_raw,
            blogid,
            blog.get("url"),
            blog.get("blogName"),
        )


def print_seesaa_blogs(seesaa_cfg: dict[str, str]) -> None:
    """利用可能な Seesaa ブログ一覧をログ出力する。"""
    blogs = list_seesaa_blogs(
        seesaa_cfg["xmlrpc_url"],
        seesaa_cfg["username"],
        seesaa_cfg["password"],
    )
    if not blogs:
        logger.info("Seesaa ブログが見つかりませんでした（getUsersBlogs が空）")
        return
    for i, blog in enumerate(blogs):
        logger.info(
            "Seesaa ブログ[%d] blogid=%r url=%r name=%r",
            i,
            blog.get("blogid"),
            blog.get("url"),
            blog.get("blogName"),
        )


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
    contents: dict[str, Any] = {
        "title": title,
        "description": description,
    }

    def _call(proxy: xmlrpc.client.ServerProxy) -> Any:
        return proxy.metaWeblog.newPost(
            blog_id,
            username,
            password,
            contents,
            1 if publish else 0,
        )

    return str(seesaa_xmlrpc_call(xmlrpc_url, _call))


def _dry_run() -> bool:
    return os.environ.get("DRY_RUN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _seesaa_rows_with_service_floor(
    seesaa_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """mst_blog_accounts の site/service/floor が揃った行（投稿キュー用）。"""
    out: list[dict[str, str]] = []
    for c in seesaa_rows:
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


def _skip_adult_target(site: str, service: str, floor: str) -> bool:
    """Seesaa はアダルト（FANZA）投稿不可。対象なら True。"""
    if not is_adult_blog_target(site, service, floor):
        return False
    logger.warning(
        "アダルト対象のため Seesaa 投稿をスキップ: site=%s service=%s floor=%s",
        site,
        service,
        floor,
    )
    return True


def run_seesaa_one_item(
    account_id: str,
    service: str,
    floor: str,
    site: str,
    seesaa_cfg: dict[str, str],
    *,
    dry: bool,
    no_mark_posted: bool,
    publish: bool,
) -> bool:
    """Supabase から1件取り Seesaa へ XML-RPC 投稿する。"""
    if _skip_adult_target(site, service, floor):
        return False

    blog_key = seesaa_cfg["blog_key"]
    post: dict[str, Any] | None = None
    for _ in range(10):
        post = get_next_livedoor_post(service, floor, account_id, blog_key)
        if not post:
            logger.info(
                "投稿対象なし（未投稿かつ review_digest あり）: account=%s service=%s floor=%s",
                account_id,
                service,
                floor,
            )
            return False
        if not is_adult_item_row(post):
            break
        logger.warning(
            "アダルト作品のため Seesaa 投稿をスキップ: content_id=%s item_id=%s site=%s",
            post.get("content_id"),
            post.get("id"),
            post.get("site"),
        )
        if dry or no_mark_posted:
            return False
        _exclude_item_after_post_failure(
            str(post["id"]), account_id, blog_key, account_id
        )
    else:
        logger.warning(
            "アダルト作品のスキップが上限に達した: account=%s service=%s floor=%s",
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
        blog_id = resolve_seesaa_blog_id(seesaa_cfg)
        post_id = meta_weblog_new_post(
            seesaa_cfg["xmlrpc_url"],
            blog_id,
            seesaa_cfg["username"],
            seesaa_cfg["password"],
            display_title,
            body_html,
            publish=publish,
        )
    except ValueError as e:
        logger.error("%s", e)
        _exclude_item_after_post_failure(
            item_id, account_id, blog_key, account_id
        )
        time.sleep(SLEEP_SECONDS_AFTER_POST)
        return False
    except xmlrpc.client.Fault as e:
        logger.exception(
            "Seesaa XML-RPC Fault: account=%s item=%s blog_id=%s faultCode=%s faultString=%s",
            account_id,
            item_id,
            seesaa_cfg.get("blog_id"),
            e.faultCode,
            e.faultString,
        )
        if "Invalid blog_id" in str(e.faultString):
            logger.error(
                "Invalid blog_id: mst_blog_accounts.blog_id はホスト名（例: gravure.seesaa.blog）か、"
                " --list-blogs で表示される blogid を設定してください。"
                " URL 全体（https://...）は正規化しますが、別ブログの blogid が必要な場合があります。"
            )
        _exclude_item_after_post_failure(
            item_id, account_id, blog_key, account_id
        )
        time.sleep(SLEEP_SECONDS_AFTER_POST)
        return False
    except xmlrpc.client.ProtocolError as e:
        if is_seesaa_access_denied(e):
            logger.error(
                "Seesaa XML-RPC が拒否されました（HTTP %s %s）。"
                " GitHub Actions 等のクラウド IP からは 403 になることがあります。"
                " 自宅 PC・self-hosted runner・ローカル cron での実行を検討してください。"
                " xmlrpc_url は https://blog.seesaa.jp/rpc のみ有効です"
                "（ssl.seesaa.jp/blog/rpc は 2021 年に提供終了）。"
                " 作品はキューから除外しません（次回再試行）。",
                e.errcode,
                e.errmsg,
            )
        else:
            logger.exception(
                "Seesaa XML-RPC ProtocolError: account=%s item=%s %s",
                account_id,
                item_id,
                e,
            )
            _exclude_item_after_post_failure(
                item_id, account_id, blog_key, account_id
            )
        time.sleep(SLEEP_SECONDS_AFTER_POST)
        return False
    except OSError as e:
        logger.exception(
            "Seesaa 接続エラー: account=%s item=%s %s",
            account_id,
            item_id,
            e,
        )
        if not is_seesaa_access_denied(e):
            _exclude_item_after_post_failure(
                item_id, account_id, blog_key, account_id
            )
        time.sleep(SLEEP_SECONDS_AFTER_POST)
        return False
    except Exception as e:
        logger.exception(
            "Seesaa 投稿例外: account=%s item=%s %s",
            account_id,
            item_id,
            e,
        )
        if is_seesaa_access_denied(e):
            logger.error(
                "アクセス拒否のためキューからは除外しません（次回再試行）。"
            )
        else:
            _exclude_item_after_post_failure(
                item_id, account_id, blog_key, account_id
            )
        time.sleep(SLEEP_SECONDS_AFTER_POST)
        return False

    logger.info(
        "Seesaa 投稿完了: account=%s blog_key=%s item=%s postid=%s",
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
        description="Seesaaブログ（セイサーブログ）XML-RPC で記事を1件投稿します。",
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
            "mst_blog_accounts の seesaa 行ごと（各行の service/floor/site）を順に試し、"
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
        "--list-blogs",
        action="store_true",
        help="blogger.getUsersBlogs で利用可能な Seesaa ブログ一覧（blogid）を表示して終了",
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

    seesaa_rows = list_enabled_seesaa_blog_configs(args.account)
    if not seesaa_rows:
        logger.error(
            "mst_blog_accounts から seesaa 行を取得できませんでした。"
            " account_id=%s, platform=seesaa, enabled=true の行と、"
            "blog_id（ブログホスト名）/ username（登録メール）/ api_password を確認してください。"
            " テーブル未作成の場合は db/DDL/ddl_mst_blog_accounts.sql を Supabase で実行してください。",
            args.account,
        )
        sys.exit(1)

    for i, rowc in enumerate(seesaa_rows):
        logger.info(
            "mst_blog_accounts seesaa[%d] blog_id=%s service=%s floor=%s site=%s blog_key=%s",
            i,
            rowc.get("blog_id"),
            rowc.get("service") or "",
            rowc.get("floor") or "",
            rowc.get("site") or "",
            rowc.get("blog_key") or "",
        )

    if args.list_blogs:
        for seesaa_cfg in seesaa_rows:
            logger.info(
                "=== account=%s blog_id=%r ===",
                args.account,
                seesaa_cfg.get("blog_id"),
            )
            print_seesaa_blogs(seesaa_cfg)
        return

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

        seesaa_cfg = seesaa_rows[0]
        try:
            blog_id = resolve_seesaa_blog_id(seesaa_cfg)
            post_id = meta_weblog_new_post(
                seesaa_cfg["xmlrpc_url"],
                blog_id,
                seesaa_cfg["username"],
                seesaa_cfg["password"],
                display_title,
                body_html,
                publish=publish,
            )
        except ValueError as e:
            logger.error("%s", e)
            sys.exit(1)
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
        master_jobs = _seesaa_rows_with_service_floor(seesaa_rows)
        if master_jobs:
            any_done = False
            attempted = 0
            for seesaa_cfg in master_jobs:
                site = normalize_portal_site(
                    seesaa_cfg.get("site"),
                    fallback=fallback_site_norm,
                )
                service = str(seesaa_cfg.get("service") or "").strip()
                floor = str(seesaa_cfg.get("floor") or "").strip()
                if _skip_adult_target(site, service, floor):
                    continue
                attempted += 1
                logger.info(
                    "ターゲット試行（mst_blog_accounts）: blog_id=%s service=%s floor=%s site=%s",
                    seesaa_cfg.get("blog_id"),
                    service,
                    floor,
                    site,
                )
                if run_seesaa_one_item(
                    args.account,
                    service,
                    floor,
                    site,
                    seesaa_cfg,
                    dry=dry,
                    no_mark_posted=args.no_mark_posted,
                    publish=publish,
                ):
                    any_done = True
            if attempted:
                if not any_done:
                    logger.info("全ターゲットで投稿対象なし。正常終了します。")
                return
            logger.warning(
                "mst_blog_accounts の seesaa 行はアダルトのみのため、"
                " BLOG_ACCOUNT_SETTINGS の非アダルト targets にフォールバックします"
            )

        seesaa_cfg = seesaa_rows[0]
        targets_list = resolve_post_targets(acc_cfg, seesaa_cfg)
        if not targets_list:
            logger.error(
                "投稿ターゲットが解決できませんでした。"
                " mst_blog_accounts の seesaa 行に service と floor を入れるか、"
                " BLOG_ACCOUNT_SETTINGS[%r][targets] を設定してください。",
                args.account,
            )
            sys.exit(2)
        any_done = False
        for t in targets_list:
            if _skip_adult_target(t["site"], t["service"], t["floor"]):
                continue
            logger.info(
                "ターゲット試行（config targets）: service=%s floor=%s site=%s",
                t["service"],
                t["floor"],
                t["site"],
            )
            if run_seesaa_one_item(
                args.account,
                t["service"],
                t["floor"],
                t["site"],
                seesaa_cfg,
                dry=dry,
                no_mark_posted=args.no_mark_posted,
                publish=publish,
            ):
                any_done = True
        if not any_done:
            logger.info("全ターゲットで投稿対象なし。正常終了します。")
        return

    rows_sf = _seesaa_rows_with_service_floor(seesaa_rows)
    matches = [
        c
        for c in seesaa_rows
        if str(c.get("service") or "").strip() == args.service
        and str(c.get("floor") or "").strip() == args.floor
    ]
    if matches:
        seesaa_cfg = matches[0]
    elif rows_sf:
        logger.error(
            "mst_blog_accounts に service=%s floor=%s の seesaa 行がありません。"
            " 登録済み: %s",
            args.service,
            args.floor,
            [(c.get("blog_id"), c.get("service"), c.get("floor")) for c in rows_sf],
        )
        sys.exit(1)
    else:
        seesaa_cfg = seesaa_rows[0]

    site = normalize_portal_site(
        seesaa_cfg.get("site"),
        fallback=fallback_site_norm,
    )
    if is_adult_blog_target(site, args.service, args.floor):
        logger.error(
            "Seesaa はアダルト投稿不可のため終了します: site=%s service=%s floor=%s",
            site,
            args.service,
            args.floor,
        )
        sys.exit(2)
    ok = run_seesaa_one_item(
        args.account,
        args.service,
        args.floor,
        site,
        seesaa_cfg,
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
