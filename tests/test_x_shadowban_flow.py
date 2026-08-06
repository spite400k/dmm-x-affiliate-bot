"""シャドウバン回避フロー（モード抽選・本文組み立て・リプ条件）のテスト。"""

from __future__ import annotations

import random

import pytest

from config.casual_posts import CASUAL_TEMPLATES, pick_casual_text
from config.x_settings import POST_MODE_WEIGHTS
from main_x import pick_post_mode, resolve_post_skip_rate, should_skip_slot
from twitter_api.tweet_service import (
    assemble_parent_post_text,
    build_portal_url,
    pick_hashtag_block,
    pick_parent_cta,
    pick_reply_text,
    should_post_reply,
)


def test_pick_post_mode_respects_weights() -> None:
    rng = random.Random(42)
    counts = {"casual": 0, "promo_parent": 0, "promo_reply": 0}
    for _ in range(1000):
        mode = pick_post_mode(POST_MODE_WEIGHTS, rng=rng)
        counts[mode] += 1
    # ざっくり期待分布（seed 固定でも幅を持たせる）
    assert counts["casual"] > 250
    assert counts["promo_parent"] > 150
    assert counts["promo_reply"] > 150
    assert sum(counts.values()) == 1000


def test_pick_post_mode_zero_weights_falls_back() -> None:
    assert pick_post_mode({"casual": 0, "promo_parent": 0}, rng=random.Random(0)) == "casual"


def test_should_skip_slot() -> None:
    assert should_skip_slot(0.0, rng=random.Random(1)) is False
    assert should_skip_slot(1.0, rng=random.Random(1)) is True


def test_resolve_post_skip_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POST_SKIP_RATE", raising=False)
    from config.x_settings import DEFAULT_POST_SKIP_RATE

    assert resolve_post_skip_rate() == DEFAULT_POST_SKIP_RATE

    monkeypatch.setenv("POST_SKIP_RATE", "0")
    assert resolve_post_skip_rate() == 0.0

    monkeypatch.setenv("POST_SKIP_RATE", "0.4")
    assert resolve_post_skip_rate() == 0.4

    monkeypatch.setenv("POST_SKIP_RATE", "not-a-float")
    assert resolve_post_skip_rate() == DEFAULT_POST_SKIP_RATE


def test_build_portal_url() -> None:
    assert (
        build_portal_url("fanza", "abc123", floor="videoa")
        == "https://fanzaportal.com/videoa/abc123"
    )
    assert (
        build_portal_url("dmm", "xyz", floor="comic", service="ebook")
        == "https://dmmportal.jp/ebook/comic/xyz"
    )


def test_assemble_parent_puts_url_only_for_parent_mode() -> None:
    portal = "https://fanzaportal.com/videoa/cid"
    with_url = assemble_parent_post_text(
        "本文",
        "#FANZA",
        "詳細はこちら【PR】",
        portal=portal,
        link_placement="parent",
    )
    assert portal in with_url
    assert "詳細はこちら【PR】" in with_url

    reply_mode = assemble_parent_post_text(
        "本文",
        "#FANZA",
        "詳細はリプで【PR】",
        portal=portal,
        link_placement="reply",
    )
    assert portal not in reply_mode
    assert "詳細はリプで【PR】" in reply_mode


def test_should_post_reply_only_when_parent_succeeded() -> None:
    assert should_post_reply("reply", 12345) is True
    assert should_post_reply("reply", "987") is True
    assert should_post_reply("reply", None) is False
    assert should_post_reply("parent", 12345) is False
    assert should_post_reply("reply", "not-an-id") is False


def test_pick_parent_cta_differs_by_placement() -> None:
    rng = random.Random(7)
    parent_cta = pick_parent_cta("parent", rng=rng)
    assert "リプ" not in parent_cta
    assert "【PR】" in parent_cta

    rng2 = random.Random(7)
    reply_cta = pick_parent_cta("reply", rng=rng2)
    assert "リプ" in reply_cta


def test_pick_reply_text_contains_portal() -> None:
    portal = "https://fanzaportal.com/videoa/cid"
    text = pick_reply_text(portal, rng=random.Random(3))
    assert portal in text
    assert "【PR】" in text


def test_pick_hashtag_block_fanza() -> None:
    rng = random.Random(99)
    block = pick_hashtag_block(
        "fanza",
        actresses=["テスト女優"],
        rng=rng,
    )
    assert isinstance(block, str)


def test_pick_casual_text_from_pool() -> None:
    assert len(CASUAL_TEMPLATES) >= 20
    text = pick_casual_text(rng=random.Random(1))
    assert text
    assert "【PR】" not in text
    # ベース文のいずれかが含まれる
    assert any(t in text for t in CASUAL_TEMPLATES)
