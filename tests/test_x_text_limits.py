"""X 加重文字数と親ツイートの 280 制限。"""

from __future__ import annotations

from twitter_api.text_limits import (
    TWEET_MAX_WEIGHTED,
    clip_text_weighted,
    twitter_weighted_length,
)
from twitter_api.tweet_service import assemble_parent_post_text


def test_twitter_weighted_length_cjk_counts_double() -> None:
    assert twitter_weighted_length("あ") == 2
    assert twitter_weighted_length("A") == 1
    assert twitter_weighted_length("API接続テスト") == 13


def test_twitter_weighted_length_url_is_tco() -> None:
    assert twitter_weighted_length("https://fanzaportal.com/videoa/hmn00673") == 23
    assert twitter_weighted_length("あ\n\nhttps://example.com/x") == 2 + 2 + 23


def test_clip_text_weighted_short_unchanged() -> None:
    assert clip_text_weighted("短い。", 20) == "短い。"


def test_clip_text_weighted_breaks_at_sentence() -> None:
    text = "これは最初の文です。" + ("あ" * 80)
    clipped = clip_text_weighted(text, 40)
    assert clipped.endswith("。")
    assert twitter_weighted_length(clipped) <= 40


def test_clip_text_weighted_ellipsis_when_no_break() -> None:
    clipped = clip_text_weighted("あ" * 80, 20)
    assert clipped.endswith("…")
    assert twitter_weighted_length(clipped) <= 20


def test_assemble_parent_clips_overlong_body_keeps_cta_and_url() -> None:
    title = (
        "ギリギリおち○こかすめる鼠径部マッサージと五感を刺激する囁き誘惑"
        "Gcupセラピストの秘密の裏オプ中出し爆ヌキ20発メンズエステ 五日市芽依"
    )
    digest = (
        "健全店の体裁から始まりつつ、裏オプの要素がじわりと強度を増していく"
        "異色のエステ系作品。芽依ちゃん の色白で柔らかな肌、Gカップの存在感、"
        "衣装の変化が視覚的な魅力を最大化しており、観る者の心を掴む。"
    )
    body = f"{title}\n\n{digest}"
    portal = "https://fanzaportal.com/videoa/hmn00673"
    cta = "気になった人はこちら【PR】"
    text = assemble_parent_post_text(
        body,
        "#FANZA",
        cta,
        portal=portal,
        link_placement="parent",
    )
    assert cta in text
    assert portal in text
    assert twitter_weighted_length(text) <= TWEET_MAX_WEIGHTED
    assert twitter_weighted_length(body) > TWEET_MAX_WEIGHTED


def test_assemble_parent_short_text_unchanged() -> None:
    portal = "https://fanzaportal.com/videoa/cid"
    text = assemble_parent_post_text(
        "短い本文",
        "#FANZA",
        "詳細はこちら【PR】",
        portal=portal,
        link_placement="parent",
    )
    assert text == (
        "短い本文\n\n#FANZA\n\n詳細はこちら【PR】\n\n"
        "https://fanzaportal.com/videoa/cid"
    )
    assert twitter_weighted_length(text) <= TWEET_MAX_WEIGHTED
