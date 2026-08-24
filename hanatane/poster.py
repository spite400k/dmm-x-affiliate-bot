"""X への親投稿 + スレッド返信。"""

from __future__ import annotations

import logging
import os
import time

import tweepy

from config.hanatane_settings import THREAD_WAIT_SECONDS, X_ACCOUNT_ID
from twitter_api.safe_post import safe_post_tweet
from twitter_api.twitter_client import get_clients

logger = logging.getLogger(__name__)


def post_thread(
    parent_text: str,
    thread_text: str,
    *,
    account: str | None = None,
    media_ids: list[str] | None = None,
    wait_seconds: int = THREAD_WAIT_SECONDS,
) -> tuple[bool, str]:
    """親投稿のあと、短い待機を挟んで自己スレッド返信する。"""
    acct = account or X_ACCOUNT_ID
    _, client = get_clients(acct)

    parent = (parent_text or "").strip()
    thread = (thread_text or "").strip()
    if not parent:
        return False, "親投稿が空"

    tweet_id = safe_post_tweet(client, parent, media_ids=media_ids)
    if not tweet_id:
        return False, "親投稿に失敗"

    if not thread:
        return True, f"親のみ投稿 tweet_id={tweet_id}"

    time.sleep(max(0, wait_seconds))
    reply_id = safe_post_tweet(client, thread, reply_to=tweet_id)
    if not reply_id:
        return False, f"親は成功({tweet_id})だがスレッド返信に失敗"

    logger.info("✅ スレッド投稿完了 parent=%s reply=%s", tweet_id, reply_id)
    return True, f"投稿成功 parent={tweet_id} reply={reply_id}"


def upload_video_if_configured(api_v1: tweepy.API) -> list[str] | None:
    """環境変数 HANATANE_DEMO_VIDEO_PATH があれば動画をアップロード。"""
    path = os.environ.get("HANATANE_DEMO_VIDEO_PATH", "").strip()
    if not path or not os.path.isfile(path):
        return None
    media = api_v1.media_upload(filename=path, media_category="tweet_video")
    logger.info("📹 デモ動画アップロード media_id=%s", media.media_id)
    return [str(media.media_id)]
