"""Supabase 等に依存しない最小限の X 投稿ヘルパー。"""

from __future__ import annotations

import logging
import random
import time

import tweepy

logger = logging.getLogger(__name__)

# ---------------------
# X 投稿
# ---------------------
def safe_post_tweet(
    client: tweepy.Client,
    text: str,
    media_ids: list[str] | None = None,
    reply_to: str | None = None,
    max_retries: int = 5,
) -> str | None:
    """Twitter に安全に投稿する。レート制限が来たら待機してリトライ。"""
    for attempt in range(max_retries):
        try:
            response = client.create_tweet(
                text=text,
                media_ids=media_ids if media_ids else None,
                in_reply_to_tweet_id=(
                    str(reply_to) if reply_to and str(reply_to).isdigit() else None
                ),
            )
            logger.info("✅ 投稿成功: %s", response.data)
            return response.data["id"]

        except tweepy.errors.TooManyRequests as e:
            reset_time = int(
                e.response.headers.get("x-rate-limit-reset", time.time() + 300)
            )
            wait_time = max(reset_time - int(time.time()), 60)
            logger.warning(
                "⚠️ レート制限 → %s秒待機 (attempt %s/%s)",
                wait_time,
                attempt + 1,
                max_retries,
            )
            time.sleep(wait_time)

            if wait_time > 600:
                logger.error("❌ 待機時間が長すぎるため投稿中止")
                return None

        except tweepy.errors.TwitterServerError:
            logger.warning("⚠ Xサーバーエラー。指数バックオフで再試行")
            wait = (2**attempt) + random.uniform(0, 3)
            time.sleep(wait)

        except tweepy.errors.Forbidden as e:
            detail = getattr(e.response, "text", None) or str(e)
            logger.critical(
                "❌ 権限エラー(403)。Developer Portal で次を確認: "
                "①アプリ User authentication が Read and write "
                "②権限変更後に Access Token を再発行して .env の "
                "ACCESS_TOKEN_* / ACCESS_TOKEN_SECRET_* を更新 "
                "③有料プランで Tweet write が使えること。API詳細: %s",
                detail[:2000] if detail else "(なし)",
            )
            return None

        except Exception as e:
            logger.error(
                "❌ 投稿失敗 (attempt %s/%s): %s",
                attempt + 1,
                max_retries,
                e,
                exc_info=True,
            )
            time.sleep(10)

    logger.error("❌ 最大リトライ回数を超えました → 投稿中止")
    return None
