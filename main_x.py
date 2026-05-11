import logging
import random
import time

from config.x_settings import X_ACCOUNT_SETTINGS
from db.post_repository import (
    get_next_post,
    mark_post_as_posted,
    mark_post_failed_skip_queue,
)
from twitter_api.tweet_service import format_campaigns, post_full_twitter
from utils.logger import setup_logger

setup_logger("main.log")
logger = logging.getLogger(__name__)

# 連続投稿によるレート制限を避けるための待機（秒）
SLEEP_SECONDS_AFTER_POST = 10


def build_twitter_text(
    title: str,
    comment: str,
    summary: str,
    point: str,
    campaigns: list | None,
    affiliate_url: str,
) -> str:
    """Twitter 用本文（post_full_twitter に渡す comment 用）。"""
    parts: list[str] = [title]
    if comment:
        parts.append(comment)
    campaign_text = format_campaigns(campaigns)
    if campaign_text:
        parts.append(campaign_text)
    return "\n\n".join(parts)


def _exclude_item_after_post_failure(
    item_id: str, account_id: str, screen_name: str
) -> None:
    """投稿失敗時にキューから外し、次回は別作品が選ばれるようにする。"""
    try:
        mark_post_failed_skip_queue(item_id, account_id)
        logger.info(
            "投稿失敗のためキューから除外（次回は別作品）: %s - %s",
            screen_name,
            item_id,
        )
    except Exception as e:
        logger.error(
            "🚨 失敗時のキュー除外マークに失敗: %s (%s)",
            screen_name,
            e,
        )


def main() -> None:
    for account_id, config in X_ACCOUNT_SETTINGS.items():
        if not config.get("enabled"):
            logger.info(
                "⚠️ %s は実施フラグOFFのためスキップします",
                config.get("screen_name", account_id),
            )
            continue

        site = config["site"]
        targets = config.get("targets", [])
        if not targets:
            logger.info(
                "⚠️ %s は targets が空のためスキップします",
                config.get("screen_name", account_id),
            )
            continue

        target = random.choice(targets)
        service = target["service"]
        floor = target["floor"]

        post = get_next_post(service, floor, account_id)
        if not post:
            logger.warning(
                "⚠ 投稿対象なし: %s (%s/%s)",
                config.get("screen_name", account_id),
                service,
                floor,
            )
            continue

        item_id = post["id"]
        content_id = post["content_id"]
        floor = post["floor"]
        service = post["service"]
        image_urls = post["sample_images"]
        affiliate_url = post["affiliate_url"]
        image_large_url = post.get("image_large_url", "")
        image_small_url = post.get("image_small_url", "")
        comment = post.get("auto_comment", "")
        summary = post.get("auto_summary", "")
        point = post.get("auto_point", "")
        sample_movie_url = post.get("sample_movie_url")
        campaigns = post.get("campaign") or []
        tachiyomi_url = post.get("tachiyomi_url")
        authors = post.get("author", [])
        actresses = post.get("actress", [])

        logger.info("タイトル: %s-%s", post["id"], post["title"])

        twitter_text = build_twitter_text(
            post["title"],
            comment,
            summary,
            point,
            campaigns,
            affiliate_url,
        )

        try:
            twitter_result = post_full_twitter(
                comment=twitter_text,
                title=post["title"],
                image_urls=image_urls,
                affiliate_url=affiliate_url,
                image_large_url=image_large_url,
                image_small_url=image_small_url,
                account=account_id,
                campaigns=campaigns,
                content_id=content_id,
                floor=floor,
                item_id=item_id,
                service=service,
                sample_movie_url=sample_movie_url,
                tachiyomi_url=tachiyomi_url,
                screen_name=config["screen_name"],
                site=site,
                authors=authors,
                actresses=actresses,
            )
        except Exception as e:
            logger.exception(
                "🚨 Twitter投稿例外: %s (%s)",
                config.get("screen_name", account_id),
                e,
            )
            _exclude_item_after_post_failure(
                item_id, account_id, config.get("screen_name", account_id)
            )
            time.sleep(SLEEP_SECONDS_AFTER_POST)
            continue

        if not twitter_result[0]:
            logger.warning(
                "⚠ Twitter投稿失敗: %s - %s",
                config.get("screen_name", account_id),
                twitter_result[1],
            )
            _exclude_item_after_post_failure(
                item_id, account_id, config.get("screen_name", account_id)
            )
            time.sleep(SLEEP_SECONDS_AFTER_POST)
            continue

        logger.info(
            "✅ Twitter投稿完了: %s - %s",
            config.get("screen_name", account_id),
            item_id,
        )

        try:
            mark_post_as_posted(item_id, account_id)
            logger.info(
                "🏁 投稿済みマーク完了: %s - %s",
                config.get("screen_name", account_id),
                item_id,
            )
        except Exception as e:
            logger.error(
                "🚨 投稿済みマーク失敗: %s (%s)",
                config.get("screen_name", account_id),
                e,
            )

        time.sleep(SLEEP_SECONDS_AFTER_POST)


if __name__ == "__main__":
    main()
