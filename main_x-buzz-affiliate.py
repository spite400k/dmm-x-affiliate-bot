"""
Buzz 用エントリ: Supabase trn_posts / trn_post_replies と X API v2 で
予約投稿 → 記事URLリプライ（5分後）を処理する。
cron で定期実行することを想定（例: 1分ごと）。

config.settings.ACCOUNT_SETTINGS を参照し、enabled なアカウントを順に処理する。

環境変数（アカウント番号 N は各エントリのキーに対応）:
  SUPABASE_URL_N, SUPABASE_KEY_N
  API_KEY_N, API_SECRET_KEY_N, ACCESS_TOKEN_N, ACCESS_TOKEN_SECRET_N, BEARER_TOKEN_N
  ARTICLE_BASE_URL … 記事URLのベース（全アカウント共通の既定）。
    個別に上書きする場合は ACCOUNT_SETTINGS の各要素に article_base_url を追加。

リプライ文は {article_base}/{article_id}
"""
from __future__ import annotations

import io
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar

from dotenv import load_dotenv

from config.settings import ACCOUNT_SETTINGS
from db.supabase_client import init_supabase
from twitter_api.twitter_client import get_clients
from twitter_api.tweet_service import fetch_image_buffer_from_url, safe_post_tweet, upload_images_v1
from utils.logger import setup_logger

load_dotenv()

# ---------------------
# ログ設定
# ---------------------
setup_logger("buzz_affiliate.log")

REPLY_DELAY = timedelta(minutes=5)
API_RETRIES = 3
DB_RETRIES = 3
MAX_POSTS_PER_RUN = 20
MAX_REPLIES_PER_RUN = 20

# ---------------------
# 時刻処理
# ---------------------
def utc_now() -> datetime:
    return datetime.now(timezone.utc)

# ---------------------
# 時刻処理(ISO形式)
# ---------------------
def utc_now_iso(dt: datetime | None = None) -> str:
    d = dt or utc_now()
    return d.isoformat()


# ---------------------
# アカウント設定処理
# ---------------------
def resolve_article_base(account_config: dict) -> str:
    """アカウント個別の article_base_url があれば優先、なければ環境変数 ARTICLE_BASE_URL。"""
    return (account_config.get("article_base_url") or os.getenv("ARTICLE_BASE_URL") or "").strip().rstrip("/")


T = TypeVar("T")


# ---------------------
# リトライ取得処理
# ---------------------
def retry_fetch(fn: Callable[[], T], label: str, max_attempts: int = DB_RETRIES) -> T | None:
    last: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            logger.error("%s 失敗 (%s/%s): %s", label, attempt, max_attempts, e, exc_info=attempt == max_attempts)
            if attempt < max_attempts:
                time.sleep(min(2 ** (attempt - 1), 30))
    logger.error("%s 最終失敗: %s", label, last)
    return None


# ---------------------
# リトライ実行処理
# ---------------------
def retry_run(fn: Callable[[], None], label: str, max_attempts: int = DB_RETRIES) -> bool:
    last: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            fn()
            return True
        except Exception as e:
            last = e
            logger.error("%s 失敗 (%s/%s): %s", label, attempt, max_attempts, e, exc_info=attempt == max_attempts)
            if attempt < max_attempts:
                time.sleep(min(2 ** (attempt - 1), 30))
    logger.error("%s 最終失敗: %s", label, last)
    return False


# ---------------------
# 投稿画像取得処理
# ---------------------
def build_reply_url(article_id: str | None, base: str) -> str | None:
    if not base:
        return None
    if not article_id:
        return None
    return f"{base}/{article_id}"


# ---------------------
# 投稿画像取得処理
# ---------------------
def fetch_image_urls_for_post(supabase: Any, post_id: str) -> list[str]:
    res = (
        supabase.table("trn_post_images")
        .select("image_url")
        .eq("post_id", post_id)
        .order("created_at")
        .limit(4)
        .execute()
    )
    rows = res.data or []
    urls: list[str] = []
    for row in rows:
        u = row.get("image_url")
        if u and isinstance(u, str):
            urls.append(u.strip())
    return urls


# ---------------------
# 画像アップロード処理
# ---------------------
def upload_images_from_urls(api_v1: Any, urls: list[str]) -> list[str]:
    if not urls:
        return []
    buffers: list[io.BytesIO] = []
    for url in urls:
        try:
            buf = fetch_image_buffer_from_url(url)
            buffers.append(buf)
        except Exception as e:
            logger.warning("画像取得スキップ: %s → %s", url, e)
    if not buffers:
        return []
    return upload_images_v1(api_v1, buffers)


# ---------------------
# 予約投稿更新処理
# ---------------------
def get_due_scheduled_posts(supabase: Any, now_iso: str) -> list[dict[str, Any]]:
    res = (
        supabase.table("trn_posts")
        .select("*")
        .eq("status", "scheduled")
        .lte("scheduled_at", now_iso)
        .order("scheduled_at")
        .limit(MAX_POSTS_PER_RUN)
        .execute()
    )
    return list(res.data or [])


# ---------------------
# 予約投稿更新処理
# ---------------------
def update_post_posted(
    supabase: Any, post_id: str, tweet_id: str, posted_iso: str
) -> None:
    supabase.table("trn_posts").update(
        {"status": "posted", "posted_at": posted_iso, "tweet_id": tweet_id}
    ).eq("id", post_id).execute()


# ---------------------
# リプライ処理
# ---------------------
def insert_scheduled_reply(
    supabase: Any, post_id: str, content: str, scheduled_iso: str
) -> None:
    supabase.table("trn_post_replies").insert(
        {"post_id": post_id, "content": content, "scheduled_at": scheduled_iso}
    ).execute()

# ---------------------
# リプライ取得処理
# ---------------------
def fetch_due_replies(supabase: Any, now_iso: str) -> list[dict[str, Any]]:
    res = (
        supabase.table("trn_post_replies")
        .select("id, post_id, content, scheduled_at")
        .is_("posted_at", "null")
        .lte("scheduled_at", now_iso)
        .order("scheduled_at")
        .limit(MAX_REPLIES_PER_RUN)
        .execute()
    )
    return list(res.data or [])

# ---------------------
# 親投稿取得処理
# ---------------------
def fetch_parent_post_tweet_id(supabase: Any, post_id: str) -> str | None:
    res = supabase.table("trn_posts").select("tweet_id").eq("id", post_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        return None
    tid = rows[0].get("tweet_id")
    return str(tid) if tid else None


# ---------------------
# リプライ処理
# ---------------------
def mark_reply_posted(supabase: Any, reply_id: str, posted_iso: str) -> None:
    supabase.table("trn_post_replies").update({"posted_at": posted_iso}).eq("id", reply_id).execute()


# ---------------------
# 投稿処理
# ---------------------
def process_scheduled_posts(account_id: str, article_base: str) -> None:
    supabase = init_supabase(account_id)
    api_v1, client_v2 = get_clients(account_id)

    now_iso = utc_now_iso()

    posts = retry_fetch(lambda: get_due_scheduled_posts(supabase, now_iso), "予約投稿の取得")
    if posts is None:
        return
    if not posts:
        logger.info("予約投稿（scheduled / 時刻到来）なし account=%s", account_id)
        return

    for post in posts:
        post_id = str(post["id"])
        content = post.get("content") or ""
        article_id = post.get("article_id")
        if not content.strip():
            logger.warning("post_id=%s の content が空のためスキップ", post_id)
            continue

        image_urls = fetch_image_urls_for_post(supabase, post_id)
        media_ids = upload_images_from_urls(api_v1, image_urls) if image_urls else None

        tweet_id = safe_post_tweet(
            client_v2,
            text=content,
            media_ids=media_ids if media_ids else None,
            reply_to=None,
            max_retries=API_RETRIES,
        )
        if not tweet_id:
            logger.error("X 投稿失敗のため DB は更新しません: post_id=%s", post_id)
            continue

        posted_iso = utc_now_iso()

        def _upd() -> None:
            update_post_posted(supabase, post_id, str(tweet_id), posted_iso)

        if not retry_run(_upd, f"trn_posts 更新 post_id={post_id}"):
            continue

        reply_url = build_reply_url(article_id, article_base)
        if not reply_url:
            logger.warning(
                "記事URLを組み立てられません（ARTICLE_BASE_URL または article_id 不足）。リプライ行は作成しません: post_id=%s",
                post_id,
            )
            continue

        reply_scheduled_at = utc_now() + REPLY_DELAY
        reply_scheduled_iso = utc_now_iso(reply_scheduled_at)

        def _ins() -> None:
            insert_scheduled_reply(supabase, post_id, reply_url, reply_scheduled_iso)

        if not retry_run(_ins, f"trn_post_replies 挿入 post_id={post_id}"):
            logger.error("リプライ予約の保存に失敗しました（手動確認推奨）: post_id=%s", post_id)

# ---------------------
# リプライ処理
# ---------------------
def process_due_replies(account_id: str) -> None:
    supabase = init_supabase(account_id)
    _, client_v2 = get_clients(account_id)

    now_iso = utc_now_iso()
    replies = retry_fetch(lambda: fetch_due_replies(supabase, now_iso), "期限到来リプライの取得")
    if replies is None:
        return
    if not replies:
        logger.info("投稿予定のリプライなし account=%s", account_id)
        return

    for row in replies:
        reply_id = str(row["id"])
        post_id = str(row["post_id"])
        reply_text = (row.get("content") or "").strip()
        if not reply_text:
            logger.warning("reply_id=%s の content が空のためスキップ", reply_id)
            continue

        parent_tid = retry_fetch(
            lambda: fetch_parent_post_tweet_id(supabase, post_id), f"tweet_id 取得 post_id={post_id}"
        )
        if parent_tid is None:
            logger.error("親投稿の tweet_id が取得できません: post_id=%s", post_id)
            continue

        new_id = safe_post_tweet(
            client_v2,
            text=reply_text,
            media_ids=None,
            reply_to=parent_tid,
            max_retries=API_RETRIES,
        )
        if not new_id:
            logger.error("リプライ投稿失敗、posted_at は更新しません: reply_id=%s", reply_id)
            continue

        posted_iso = utc_now_iso()

        def _mark() -> None:
            mark_reply_posted(supabase, reply_id, posted_iso)

        if not retry_run(_mark, f"trn_post_replies 更新 reply_id={reply_id}"):
            logger.error("リプライは投稿済みだが DB 更新失敗（要確認）: reply_id=%s", reply_id)

# ---------------------
# メイン処理
# ---------------------
def main() -> None:
    logger.info("Buzz affiliate ジョブ開始（ACCOUNT_SETTINGS 走査）")
    for account_id, config in ACCOUNT_SETTINGS.items():
        if not config.get("enabled"):
            logger.info(
                "⚠️ %s は実施フラグOFFのためスキップ",
                config.get("screen_name", account_id),
            )
            continue
        screen = config.get("screen_name", account_id)
        article_base = resolve_article_base(config)
        logger.info("Buzz affiliate account=%s (%s)", account_id, screen)
        try:
            process_scheduled_posts(account_id, article_base)
            process_due_replies(account_id)
        except Exception as e:
            logger.exception(
                "Buzz affiliate ジョブで未処理例外 account=%s (%s): %s",
                account_id,
                screen,
                e,
            )
    logger.info("Buzz affiliate ジョブ完了（全アカウント）")


if __name__ == "__main__":
    main()
