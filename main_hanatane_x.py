"""@hanatane_app 向け X 自動投稿。

改善案 §3: 時事ネタカード(A)を主軸、沈黙対策同文は出さない。
"""

from __future__ import annotations

import logging
import os
import sys

from config.hanatane_settings import (
    DISCOVER_URL,
    MAX_POSTED_HISTORY,
    SCREEN_NAME,
    SILENCE_TIPS,
    X_ACCOUNT_ID,
)
from hanatane.discover import fetch_vtuber_topics
from hanatane.post_text import build_demo_post, build_news_card_post, build_silence_tip_post
from hanatane.poster import post_thread, upload_video_if_configured
from hanatane.schedule import resolve_mode_for_today
from hanatane.state import (
    mark_tip_posted,
    mark_topic_posted,
    pick_silence_tip_index,
    pick_unposted_topic,
    PostState,
    resolve_state_path,
)
from twitter_api.twitter_client import get_clients
from utils.logger import setup_logger

setup_logger("main.log")
logger = logging.getLogger(__name__)


def _post_news_card(state: PostState, state_path) -> int:
    topics = fetch_vtuber_topics(DISCOVER_URL)
    if not topics:
        logger.error("Discover からネタを取得できませんでした")
        return 1

    topic = pick_unposted_topic(topics, state, max_history=MAX_POSTED_HISTORY)
    if topic is None:
        logger.error("投稿可能なネタがありません")
        return 1

    parent, thread = build_news_card_post(topic)
    logger.info("news_card: %s → %s", SCREEN_NAME, topic.title)

    ok, msg = post_thread(parent, thread, account=X_ACCOUNT_ID)
    if not ok:
        logger.error("投稿失敗: %s", msg)
        return 1

    mark_topic_posted(state, topic.key, max_history=MAX_POSTED_HISTORY)
    state.save(state_path)
    logger.info("✅ %s", msg)
    return 0


def _post_silence_tip(state: PostState, state_path) -> int:
    idx = pick_silence_tip_index(len(SILENCE_TIPS), state)
    tip = SILENCE_TIPS[idx]
    parent, thread = build_silence_tip_post(tip)
    logger.info("silence_tip: %s (index=%s)", SCREEN_NAME, idx)

    ok, msg = post_thread(parent, thread, account=X_ACCOUNT_ID)
    if not ok:
        logger.error("投稿失敗: %s", msg)
        return 1

    mark_tip_posted(state, idx)
    state.save(state_path)
    logger.info("✅ %s", msg)
    return 0


def _post_demo(state: PostState, state_path) -> int:
    api_v1, _ = get_clients(X_ACCOUNT_ID)
    media_ids = upload_video_if_configured(api_v1)
    if not media_ids:
        logger.info("デモ動画未設定 → news_card にフォールバック")
        return _post_news_card(state, state_path)

    parent, thread = build_demo_post()
    logger.info("demo: %s (video)", SCREEN_NAME)
    ok, msg = post_thread(parent, thread, account=X_ACCOUNT_ID, media_ids=media_ids)
    if not ok:
        logger.error("投稿失敗: %s", msg)
        return 1

    state.save(state_path)
    logger.info("✅ %s", msg)
    return 0


def main() -> int:
    if os.environ.get("HANATANE_X_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        logger.info("HANATANE_X_ENABLED=0 のためスキップ")
        return 0

    mode = resolve_mode_for_today()
    logger.info("hanatane_x mode=%s account=%s", mode, X_ACCOUNT_ID)

    if mode == "skip":
        logger.info("本日は投稿スキップ（スケジュール）")
        return 0

    state_path = resolve_state_path()
    state = PostState.load(state_path)

    if mode == "news_card":
        return _post_news_card(state, state_path)
    if mode == "silence_tip":
        return _post_silence_tip(state, state_path)
    if mode == "demo":
        return _post_demo(state, state_path)

    logger.error("未知のモード: %s", mode)
    return 1


if __name__ == "__main__":
    sys.exit(main())
