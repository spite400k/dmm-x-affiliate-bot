"""main_weekly_ranking の本文組み立て（ネットワーク・Twitter API 不要）。"""

from __future__ import annotations

import pytest

import main_weekly_ranking as mwr
from utils.portal_ranking import RankingItem, RankingPage


@pytest.fixture
def sample_page() -> RankingPage:
    return RankingPage(
        headline="2026年99週目｜テストジャンル 今週の人気ランキングTOP3",
        updated="最終更新日: 2026年4月21日",
        items=[
            RankingItem(1, "短いタイトル"),
            RankingItem(2, "中くらいのタイトルです"),
            RankingItem(3, "三"),
        ],
    )


def test_build_ranking_tweet_contains_headline_and_url(sample_page: RankingPage) -> None:
    url = "https://www.fanzaportal.com/ranking/videoa/weekly"
    text = mwr.build_ranking_tweet(url, sample_page)
    assert "FANZA Portal" in text
    assert sample_page.headline in text
    assert sample_page.updated in text
    assert "1位 短いタイトル" in text
    assert url in text


def test_build_ranking_tweet_dmm_label(sample_page: RankingPage) -> None:
    url = "https://www.dmmportal.jp/ranking/ebook/comic/weekly"
    text = mwr.build_ranking_tweet(url, sample_page)
    assert "DMMポータル" in text


def test_build_ranking_tweet_clips_long_title(sample_page: RankingPage) -> None:
    long = "あ" * 100
    page = RankingPage(
        headline=sample_page.headline,
        updated=sample_page.updated,
        items=[RankingItem(1, long)],
    )
    text = mwr.build_ranking_tweet(
        "https://www.fanzaportal.com/ranking/videoa/weekly", page
    )
    line = [ln for ln in text.splitlines() if ln.startswith("1位 ")][0]
    assert line.endswith("…") or len(line) < len(long) + 10


def test_build_ranking_tweet_respects_soft_limit() -> None:
    """極端に長い見出し・タイトルでもソフト上限を超えにくい（順位件数の短縮が効く）。"""
    long_h = "長" * 120
    items = [RankingItem(i, "タ" * 80) for i in range(1, 11)]
    page = RankingPage(headline=long_h, updated="最終更新日: 2026年1月1日", items=items)
    text = mwr.build_ranking_tweet(
        "https://www.fanzaportal.com/ranking/videoa/weekly", page
    )
    assert len(text) <= mwr.TWEET_CHAR_SOFT_LIMIT + 5


def test_log_ranking_post_content_does_not_raise(
    sample_page: RankingPage, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    caplog.set_level(logging.INFO)
    text = mwr.build_ranking_tweet(
        "https://www.fanzaportal.com/ranking/videoa/weekly", sample_page
    )
    mwr.log_ranking_post_content(
        logging.getLogger("test"),
        url="https://www.fanzaportal.com/ranking/videoa/weekly",
        account_id="2",
        screen_name="test_user",
        page=sample_page,
        tweet_text=text,
        dry_run=True,
    )
    assert "週間ランキング" in caplog.text
    assert "char_count" in caplog.text or "文字数" in caplog.text
