"""
FC2ブログへ XML-RPC（metaWeblog.newPost）で自動投稿するエントリポイント。

main.py と同様に config.settings.ACCOUNT_SETTINGS と DB キュー（get_next_post）を利用する。
FC2 のブログID・ユーザー名・XML-RPCパスワードは Supabase のマスタテーブルから取得する。

既定マスタテーブル: mst_blog_accounts
必須カラム:
  account_id, platform, enabled, blog_id, username, api_password
任意カラム:
  blog_key, xmlrpc_url

FC2 の行は platform='fc2', enabled=true にする。
ライブドアは同テーブルで platform='livedoor'（post_livedoor_atompub が
db/blog_repository を参照。main.py はブログ投稿を行わない）。

blog_key は trn_dmm_item_blog_post_status.blog_key と一致する投稿済み管理キー。
FC2: マスタの blog_key 列があればそれを使い、無ければ fc2:{account_id}:{blog_id}。
ライブドア: マスタの blog_key は備考のみ。投稿済みキーは常に livedoor:{blog_id}。

任意:
  BLOG_ACCOUNT_MASTER_TABLE … マスタテーブル名（省略時 mst_blog_accounts）
  DRY_RUN=1                 … 投稿せず本文のみログ（.env の他スクリプトと同様）
"""

from __future__ import annotations

import html
import logging
import os
import random
import time
import xmlrpc.client
from typing import Any

from dotenv import load_dotenv

from config.settings import ACCOUNT_SETTINGS
from db.blog_repository import get_enabled_fc2_blog_config
from db.post_repository import (
    get_next_post,
    mark_post_as_posted,
    mark_post_failed_skip_queue,
)
from twitter_api.tweet_service import format_campaigns
from utils.logger import setup_logger

load_dotenv()

setup_logger("main_fc2_blog.log")
logger = logging.getLogger(__name__)

SLEEP_SECONDS_AFTER_POST = 10


def build_fc2_description(
    title: str,
    comment: str,
    summary: str,
    point: str,
    campaigns: list | None,
    affiliate_url: str,
    image_urls: list | None,
) -> str:
    """FC2 記事本文（HTML）。画像は先頭数枚のみ埋め込む。"""
    parts: list[str] = []

    if image_urls:
        for url in image_urls[:5]:
            if not url:
                continue
            safe = html.escape(url, quote=True)
            parts.append(f'<p><img src="{safe}" alt="" loading="lazy" /></p>')

    blocks: list[str] = []
    if comment:
        blocks.append(html.escape(comment, quote=False))
    if summary:
        blocks.append(f"概要: {html.escape(summary, quote=False)}")
    if point:
        blocks.append(f"注目ポイント: {html.escape(point, quote=False)}")
    campaign_text = format_campaigns(campaigns)
    if campaign_text:
        blocks.append(html.escape(campaign_text, quote=False))

    for b in blocks:
        parts.append(f"<p>{b.replace(chr(10), '<br />')}</p>")

    if affiliate_url:
        u = html.escape(affiliate_url, quote=True)
        parts.append(f'<p><a href="{u}" rel="nofollow noopener">公式・詳細はこちら</a></p>')

    parts.append(f"<p><small>{html.escape(title, quote=False)}</small></p>")
    return "\n".join(parts)


def meta_weblog_new_post(
    xmlrpc_url: str,
    blog_id: str,
    username: str,
    password: str,
    title: str,
    description: str,
    publish: bool,
) -> str:
    """
    metaWeblog.newPost を実行し、作成された postid（文字列）を返す。
    """
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


def main() -> None:
    dry = os.getenv("DRY_RUN", "").strip() in ("1", "true", "True", "yes", "YES")

    for account_id, config in ACCOUNT_SETTINGS.items():
        if not config.get("enabled_blog"):
            logger.info(
                "%s は enabled_blog=OFF のためスキップします",
                config.get("screen_name", account_id),
            )
            continue

        fc2 = get_enabled_fc2_blog_config(account_id)
        if not fc2:
            logger.info(
                "FC2ブログマスタが未設定または無効のためスキップ: %s",
                config.get("screen_name", account_id),
            )
            continue

        targets = config.get("targets", [])
        if not targets:
            logger.info(
                "%s は targets が空のためスキップします",
                config.get("screen_name", account_id),
            )
            continue

        target = random.choice(targets)
        service = target["service"]
        floor = target["floor"]

        post = get_next_post(service, floor, account_id, blog_key=fc2["blog_key"])
        if not post:
            logger.warning(
                "投稿対象なし: %s (%s/%s)",
                config.get("screen_name", account_id),
                service,
                floor,
            )
            continue

        item_id = post["id"]
        image_urls = post.get("sample_images") or []
        affiliate_url = post.get("affiliate_url") or ""
        comment = post.get("auto_comment", "")
        summary = post.get("auto_summary", "")
        point = post.get("auto_point", "")
        campaigns = post.get("campaign") or []
        title = post["title"]

        logger.info("FC2 投稿対象: %s-%s", item_id, title)

        description = build_fc2_description(
            title=title,
            comment=comment,
            summary=summary,
            point=point,
            campaigns=campaigns,
            affiliate_url=affiliate_url,
            image_urls=image_urls if isinstance(image_urls, list) else [],
        )

        if dry:
            logger.info(
                "[DRY_RUN] FC2 投稿をスキップ。title=%r 本文先頭200文字=%r",
                title,
                description[:200],
            )
            time.sleep(SLEEP_SECONDS_AFTER_POST)
            continue

        try:
            post_id = meta_weblog_new_post(
                fc2["xmlrpc_url"],
                fc2["blog_id"],
                fc2["username"],
                fc2["password"],
                title,
                description,
                publish=True,
            )
        except xmlrpc.client.Fault as e:
            logger.exception(
                "FC2 XML-RPC Fault: %s (%s) faultCode=%s faultString=%s",
                config.get("screen_name", account_id),
                item_id,
                e.faultCode,
                e.faultString,
            )
            _exclude_item_after_post_failure(
                item_id,
                account_id,
                fc2["blog_key"],
                config.get("screen_name", account_id),
            )
            time.sleep(SLEEP_SECONDS_AFTER_POST)
            continue
        except OSError as e:
            logger.exception(
                "FC2 接続エラー: %s (%s) %s",
                config.get("screen_name", account_id),
                item_id,
                e,
            )
            _exclude_item_after_post_failure(
                item_id,
                account_id,
                fc2["blog_key"],
                config.get("screen_name", account_id),
            )
            time.sleep(SLEEP_SECONDS_AFTER_POST)
            continue
        except Exception as e:
            logger.exception(
                "FC2 投稿例外: %s (%s) %s",
                config.get("screen_name", account_id),
                item_id,
                e,
            )
            _exclude_item_after_post_failure(
                item_id,
                account_id,
                fc2["blog_key"],
                config.get("screen_name", account_id),
            )
            time.sleep(SLEEP_SECONDS_AFTER_POST)
            continue

        logger.info(
            "FC2 投稿完了: %s - blog_key=%s item=%s postid=%s",
            config.get("screen_name", account_id),
            fc2["blog_key"],
            item_id,
            post_id,
        )

        try:
            mark_post_as_posted(item_id, account_id, blog_key=fc2["blog_key"])
            logger.info(
                "投稿済みマーク完了: %s - %s (%s)",
                config.get("screen_name", account_id),
                item_id,
                fc2["blog_key"],
            )
        except Exception as e:
            logger.error(
                "投稿済みマーク失敗: %s (%s)",
                config.get("screen_name", account_id),
                e,
            )

        time.sleep(SLEEP_SECONDS_AFTER_POST)


if __name__ == "__main__":
    main()
