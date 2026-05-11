"""
週間ランキングを main.py と同様にアカウント単位で処理し、
WEEKLY_RANKING_SEQUENCE の第2要素がそのアカウントIDと一致する URL のみ取得・投稿する。

環境変数 DRY_RUN=1 のときは投稿せず本文のみログ出力する。
"""

from __future__ import annotations

import logging
import os
import time

from config.x_settings import X_ACCOUNT_SETTINGS
from twitter_api.safe_post import safe_post_tweet
from twitter_api.twitter_client import get_clients
from utils.logger import setup_logger
from utils.portal_ranking import RankingPage, fetch_weekly_ranking

setup_logger("main_weekly_ranking.log")
logger = logging.getLogger(__name__)

# (ランキングページ URL, Twitter アカウント ID … x_settings.X_ACCOUNT_SETTINGS と同一キー)
# main2.py は API_KEY_1 固定。FANZA 行が "2" のときは get_clients("2")→403 になり main2 と差が出る。
WEEKLY_RANKING_SEQUENCE: list[tuple[str, str]] = [
    ("https://www.fanzaportal.com/ranking/videoa/weekly", "2"),
    ("https://www.fanzaportal.com/ranking/videoc/weekly", "2"),
    ("https://www.fanzaportal.com/ranking/comic/weekly", "2"),
    ("https://www.fanzaportal.com/ranking/digital_doujin/weekly", "2"),
    ("https://www.dmmportal.jp/ranking/ebook/comic/weekly", "1"),
    ("https://www.dmmportal.jp/ranking/ebook/novel/weekly", "1"),
    ("https://www.dmmportal.jp/ranking/ebook/otherbooks/weekly", "1"),
    ("https://www.dmmportal.jp/ranking/ebook/photo/weekly", "1"),
]

# 1投稿に含める順位の最大件数（長いタイトルでも文字数オーバーしにくくする）
TOP_RANKS_IN_TWEET = 7
# 1タイトルの最大文字数（省略）
MAX_TITLE_CHARS = 72
# 連続投稿の間隔（秒）
SLEEP_SECONDS_BETWEEN_POSTS = 15
# 本文のおおよそ上限（余裕を見て少し下げる）
TWEET_CHAR_SOFT_LIMIT = 268

# ---------------------
# ポータルラベル
# ---------------------
def _portal_label(url: str) -> str:
    if "fanzaportal.com" in url:
        return "FANZA Portal 週間ランキング"
    if "dmmportal.jp" in url:
        return "DMMポータル 週間ランキング"
    return "週間ランキング"

# ---------------------
# タイトル省略
# ---------------------
def _clip_title(title: str) -> str:
    t = title.strip()
    if len(t) <= MAX_TITLE_CHARS:
        return t
    return t[: MAX_TITLE_CHARS - 1] + "…"

# ---------------------
# 投稿本文構築
# ---------------------
def build_ranking_tweet(url: str, page: RankingPage) -> str:
    label = _portal_label(url)
    lines: list[str] = [f"📊 {label}", page.headline]
    if page.updated:
        lines.append(page.updated)
    lines.append("")
    for it in page.items[:TOP_RANKS_IN_TWEET]:
        lines.append(f"{it.rank}位 {_clip_title(it.title)}")
    lines.append("")
    lines.append(url)
    text = "\n".join(lines)
    if len(text) > TWEET_CHAR_SOFT_LIMIT:
        # 順位件数を減らして再構成（極端に長い見出しでも 0 件まで落とす）
        max_n = min(TOP_RANKS_IN_TWEET, len(page.items))
        for n in range(max_n, -1, -1):
            lines = [f"📊 {label}", page.headline]
            if page.updated:
                lines.append(page.updated)
            lines.append("")
            for it in page.items[:n]:
                lines.append(f"{it.rank}位 {_clip_title(it.title)}")
            lines.append("")
            lines.append(url)
            text = "\n".join(lines)
            if len(text) <= TWEET_CHAR_SOFT_LIMIT:
                break
    return text


def log_ranking_post_content(
    logger: logging.Logger,
    *,
    url: str,
    account_id: str,
    screen_name: str,
    page: RankingPage,
    tweet_text: str,
    dry_run: bool,
) -> None:
    """運用前確認用に、取得結果と投稿本文をログへ詳細出力する。"""
    char_count = len(tweet_text)
    logger.info("---------- 週間ランキング 投稿内容ログ ----------")
    logger.info(
        "meta url=%s account_id=%s screen_name=%s dry_run=%s parsed_items=%s char_count=%s",
        url,
        account_id,
        screen_name,
        dry_run,
        len(page.items),
        char_count,
    )
    logger.info("parsed_headline=%s", page.headline)
    logger.info("parsed_updated=%s", page.updated)
    titles_preview = " | ".join(f"{it.rank}:{it.title[:40]}" for it in page.items[:12])
    if len(page.items) > 12:
        titles_preview += " | ..."
    logger.info("parsed_titles_preview=%s", titles_preview)
    logger.info(
        "tweet_body (開始)\n%s\ntweet_body (終了) char_count=%s",
        tweet_text,
        char_count,
    )
    logger.info("---------- 以上 ----------")


# ---------------------
# メイン
# ---------------------
def main() -> None:
    dry = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes", "on")

    for account_id, config in X_ACCOUNT_SETTINGS.items():
        if not config.get("enabled"):
            logger.info(
                "⚠️ %s は実施フラグOFFのためスキップします",
                config.get("screen_name", account_id),
            )
            continue

        matches = [(u, a) for u, a in WEEKLY_RANKING_SEQUENCE if a == account_id]
        if not matches:
            logger.info(
                "⚠️ %s は週間ランキングの対象URLが定義されていません",
                config.get("screen_name", account_id),
            )
            continue

        for url, _ in matches:
            try:
                page = fetch_weekly_ranking(url)
            except Exception as e:
                logger.exception("取得失敗: %s (%s)", url, e)
                continue

            if not page:
                continue

            text = build_ranking_tweet(url, page)
            screen = config.get("screen_name", account_id)
            log_ranking_post_content(
                logger,
                url=url,
                account_id=account_id,
                screen_name=screen,
                page=page,
                tweet_text=text,
                dry_run=dry,
            )

            if dry:
                time.sleep(1)
                continue

            try:
                _, client_v2 = get_clients(account_id)
            except Exception as e:
                logger.error("Twitter クライアント取得失敗 account=%s: %s", account_id, e)
                break

            tweet_id = safe_post_tweet(client_v2, text)
            if tweet_id:
                logger.info(
                    "✅ 投稿完了 (%s) tweet_id=%s body_char_count=%s",
                    screen,
                    tweet_id,
                    len(text),
                )
            else:
                logger.warning("⚠ 投稿失敗 (%s): %s", screen, url)

            time.sleep(SLEEP_SECONDS_BETWEEN_POSTS)


if __name__ == "__main__":
    main()
