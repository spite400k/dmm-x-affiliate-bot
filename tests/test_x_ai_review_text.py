"""X 投稿の AI レビュー要約組み込みテスト。"""

from __future__ import annotations

from main_x import REVIEW_DIGEST_MAX_CHARS, build_twitter_text, clip_review_digest_for_x


def test_clip_review_digest_short_unchanged() -> None:
    assert clip_review_digest_for_x("短い要約。") == "短い要約。"


def test_clip_review_digest_breaks_at_sentence() -> None:
    long = "あ" * 80 + "。これは続きの文でかなり長いので切られるはずです。" + "い" * 50
    clipped = clip_review_digest_for_x(long, max_chars=100)
    assert len(clipped) <= 100
    assert clipped.endswith("。")


def test_clip_review_digest_ellipsis_when_no_break() -> None:
    long = "あ" * 200
    clipped = clip_review_digest_for_x(long, max_chars=50)
    assert clipped.endswith("…")
    assert len(clipped) <= 51


def test_build_twitter_text_prefers_digest_over_comment() -> None:
    text = build_twitter_text(
        title="作品タイトル",
        comment="自動コメントは使わない",
        summary="",
        point="",
        campaigns=None,
        affiliate_url="",
        review_digest="レビュー要約の一文です。さらに続く説明。",
    )
    assert "作品タイトル" in text
    assert "レビュー要約の一文です。" in text
    assert "自動コメントは使わない" not in text


def test_build_twitter_text_falls_back_to_comment() -> None:
    text = build_twitter_text(
        title="作品タイトル",
        comment="フォールバックコメント",
        summary="",
        point="",
        campaigns=None,
        affiliate_url="",
        review_digest="",
    )
    assert "フォールバックコメント" in text


def test_build_twitter_text_clips_long_digest() -> None:
    digest = ("とても長いレビュー要約です。" * 20)
    text = build_twitter_text(
        title="T",
        comment="C",
        summary="",
        point="",
        campaigns=None,
        affiliate_url="",
        review_digest=digest,
    )
    # タイトル行以外が digest 由来で、丸ごと全文は入らない
    assert digest not in text
    body = text.split("\n\n", 1)[1]
    assert len(body) <= REVIEW_DIGEST_MAX_CHARS + 5
