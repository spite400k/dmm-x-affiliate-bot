"""main_weekly_ranking の本文組み立て（ネットワーク・Twitter API 不要）。"""

from __future__ import annotations

import logging

import pytest

import main_weekly_ranking as mwr
from utils.portal_ranking import RankingItem, RankingPage


@pytest.fixture
def sample_page() -> RankingPage:
    return RankingPage(
        headline="2026年99週目｜テストジャンル 今週の人気ランキングTOP3",
        updated="最終更新日: 2026年4月21日",
        items=[
            RankingItem(
                1,
                "短いタイトル",
                "https://www.fanzaportal.com/videoa/a",
                content_id="a",
                actress="白石るな",
            ),
            RankingItem(
                2,
                "中くらいのタイトルです",
                content_id="b",
                actress="博多彩葉",
            ),
            RankingItem(3, "女優なしの長いタイトルですよ", content_id="c"),
        ],
    )


def test_sequence_is_videoa_only() -> None:
    assert len(mwr.WEEKLY_RANKING_SEQUENCE) == 1
    url, account = mwr.WEEKLY_RANKING_SEQUENCE[0]
    assert "/videoa/" in url
    assert account == "2"


def test_twitter_weighted_length_cjk_counts_double() -> None:
    assert mwr.twitter_weighted_length("あ") == 2
    assert mwr.twitter_weighted_length("A") == 1
    # API(3) + 接続テスト(5文字×2=10) = 13
    assert mwr.twitter_weighted_length("API接続テスト") == 13
    assert mwr.twitter_weighted_length("API接続テスト") > len("API接続テスト")


def test_build_ranking_tweet_contains_headline_and_url(sample_page: RankingPage) -> None:
    url = "https://www.fanzaportal.com/ranking/videoa/weekly"
    text = mwr.build_ranking_tweet(url, sample_page)
    assert "FANZA動画" in text
    assert "99週目" in text
    assert "1位 白石るな" in text
    assert "2位 博多彩葉" in text
    assert "3位 " in text  # 女優なしはタイトルフォールバック
    assert "4位 " not in text  # TOP3のみ
    assert url in text
    assert mwr.twitter_weighted_length(text) <= mwr.TWEET_WEIGHTED_SOFT_LIMIT


def test_build_ranking_tweet_dmm_label_still_posts_url(sample_page: RankingPage) -> None:
    url = "https://www.dmmportal.jp/ranking/ebook/comic/weekly"
    text = mwr.build_ranking_tweet(url, sample_page)
    assert url in text


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
    assert line.endswith("…")
    assert mwr.twitter_weighted_length(line) <= 4 + mwr.MAX_TITLE_WEIGHTED_TWEET


def test_build_ranking_tweet_respects_weighted_limit() -> None:
    """極端に長いタイトルでも X 加重長のソフト上限を超えない。"""
    items = [RankingItem(i, "タ" * 80) for i in range(1, 11)]
    page = RankingPage(
        headline="8月2週ランキング｜動画(AV)ジャンル 今週の人気ランキングTOP20",
        updated="最終更新日: 2026年1月1日",
        items=items,
    )
    text = mwr.build_ranking_tweet(
        "https://www.fanzaportal.com/ranking/videoa/weekly", page
    )
    assert mwr.twitter_weighted_length(text) <= mwr.TWEET_WEIGHTED_SOFT_LIMIT


def test_build_ranking_blog_title_includes_week(sample_page: RankingPage) -> None:
    url = "https://www.fanzaportal.com/ranking/videoa/weekly"
    title = mwr.build_ranking_blog_title(url, sample_page)
    assert "FANZA動画" in title
    assert "週間ランキング" in title
    assert "99週目" in title


def test_build_ranking_blog_title_month_week_format() -> None:
    """本番ポータルの『8月2週ランキング｜…』形式にも対応する。"""
    url = "https://www.fanzaportal.com/ranking/videoa/weekly"
    page = RankingPage(
        headline="8月2週ランキング｜動画(AV)ジャンル 今週の人気ランキングTOP20",
        updated="",
        items=[RankingItem(1, "作品A")],
    )
    title = mwr.build_ranking_blog_title(url, page)
    assert "8月2週" in title
    assert title.startswith("FANZA動画｜")


def test_build_ranking_tweet_top3_only() -> None:
    items = [
        RankingItem(i, f"タイトル{i}", actress=f"女優{i}") for i in range(1, 8)
    ]
    page = RankingPage(
        headline="8月2週ランキング｜動画(AV)",
        updated="",
        items=items,
    )
    text = mwr.build_ranking_tweet(
        "https://www.fanzaportal.com/ranking/videoa/weekly", page
    )
    assert "1位 女優1" in text
    assert "3位 女優3" in text
    assert "4位 " not in text
    assert mwr.twitter_weighted_length(text) <= mwr.TWEET_WEIGHTED_SOFT_LIMIT


def test_build_ranking_blog_html_lists_and_links(sample_page: RankingPage) -> None:
    url = "https://www.fanzaportal.com/ranking/videoa/weekly"
    html = mwr.build_ranking_blog_html(url, sample_page)
    assert "<ol>" in html
    assert "白石るな" in html
    assert "短いタイトル" in html
    assert 'href="https://www.fanzaportal.com/videoa/a"' in html
    assert url in html
    assert "ランキングページを見る" in html


def test_parse_actress_names_from_json() -> None:
    raw = '[{"id":1,"name":"白石るな","ruby":"しらいしるな"}]'
    assert mwr._parse_actress_names(raw) == ["白石るな"]


def test_log_ranking_post_content_does_not_raise(
    sample_page: RankingPage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    url = "https://www.fanzaportal.com/ranking/videoa/weekly"
    text = mwr.build_ranking_tweet(url, sample_page)
    blog_title = mwr.build_ranking_blog_title(url, sample_page)
    blog_html = mwr.build_ranking_blog_html(url, sample_page)
    mwr.log_ranking_post_content(
        logging.getLogger("test"),
        url=url,
        account_id="2",
        screen_name="test_user",
        page=sample_page,
        tweet_text=text,
        blog_title=blog_title,
        blog_html=blog_html,
        dry_run=True,
    )
    assert "週間ランキング" in caplog.text
