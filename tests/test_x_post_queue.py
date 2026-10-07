"""X 投稿キュー（status テーブル / 連投防止）のテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from db.post_repository import x_post_status_key


def test_x_post_status_key() -> None:
    assert x_post_status_key("2") == "x:2"
    assert x_post_status_key("1") == "x:1"


def test_get_next_x_post_prefers_digest_via_status_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from db import post_repository as pr

    calls: list[tuple] = []

    def fake_livedoor(service, floor, account_id, blog_key):
        calls.append(("livedoor", service, floor, account_id, blog_key))
        return {"id": "item-digest", "content_id": "cid1"}

    def fake_next(*_a, **_k):
        calls.append(("fallback",))
        return {"id": "item-plain"}

    monkeypatch.setattr(pr, "get_next_livedoor_post", fake_livedoor)
    monkeypatch.setattr(pr, "get_next_post", fake_next)

    got = pr.get_next_x_post("digital", "videoa", "2", prefer_review_digest=True)
    assert got["id"] == "item-digest"
    assert calls == [("livedoor", "digital", "videoa", "2", "x:2")]


def test_get_next_x_post_falls_back_without_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    from db import post_repository as pr

    monkeypatch.setattr(pr, "get_next_livedoor_post", lambda *_a, **_k: None)

    seen: dict[str, object] = {}

    def fake_next(service, floor, account_id, blog_key=None):
        seen["args"] = (service, floor, account_id, blog_key)
        return {"id": "plain"}

    monkeypatch.setattr(pr, "get_next_post", fake_next)

    got = pr.get_next_x_post("digital", "videoa", "2", prefer_review_digest=True)
    assert got["id"] == "plain"
    assert seen["args"] == ("digital", "videoa", "2", "x:2")


def test_get_next_x_post_skips_digest_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from db import post_repository as pr

    livedoor = MagicMock()
    monkeypatch.setattr(pr, "get_next_livedoor_post", livedoor)

    def fake_next(service, floor, account_id, blog_key=None):
        return {"id": "no-digest-path", "blog_key": blog_key}

    monkeypatch.setattr(pr, "get_next_post", fake_next)

    got = pr.get_next_x_post("digital", "videoa", "2", prefer_review_digest=False)
    assert got["id"] == "no-digest-path"
    assert got["blog_key"] == "x:2"
    livedoor.assert_not_called()


def test_post_promo_marks_with_x_status_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from main_x import _post_promo_for_account

    monkeypatch.setattr(
        "main_x.get_next_x_post",
        lambda *_a, **_k: {
            "id": "item-1",
            "content_id": "cid",
            "floor": "videoa",
            "service": "digital",
            "sample_images": [],
            "affiliate_url": "https://example.com/a",
            "title": "作品タイトル",
            "auto_comment": "c",
            "auto_summary": "",
            "auto_point": "",
            "campaign": [],
            "author": [],
            "actress": [],
        },
    )
    monkeypatch.setattr("main_x.get_ai_review_summary", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "main_x.post_full_twitter",
        lambda **_k: (True, "ok"),
    )
    marked: list[tuple] = []

    def fake_mark(post_id, account_id, blog_key=None):
        marked.append((post_id, account_id, blog_key))

    monkeypatch.setattr("main_x.mark_post_as_posted", fake_mark)

    _post_promo_for_account(
        "2",
        {
            "site": "fanza",
            "screen_name": "Ren47291",
            "targets": [{"service": "digital", "floor": "videoa"}],
        },
        "promo_parent",
    )
    assert marked == [("item-1", "2", "x:2")]


def test_post_promo_raises_when_mark_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from main_x import _post_promo_for_account

    monkeypatch.setattr(
        "main_x.get_next_x_post",
        lambda *_a, **_k: {
            "id": "item-1",
            "content_id": "cid",
            "floor": "videoa",
            "service": "digital",
            "sample_images": [],
            "affiliate_url": "https://example.com/a",
            "title": "作品タイトル",
            "auto_comment": "c",
            "auto_summary": "",
            "auto_point": "",
            "campaign": [],
            "author": [],
            "actress": [],
        },
    )
    monkeypatch.setattr("main_x.get_ai_review_summary", lambda *_a, **_k: None)
    monkeypatch.setattr("main_x.post_full_twitter", lambda **_k: (True, "ok"))

    def boom(*_a, **_k):
        raise PermissionError("permission denied for table trn_dmm_items")

    monkeypatch.setattr("main_x.mark_post_as_posted", boom)

    with pytest.raises(RuntimeError, match="投稿済みマーク失敗"):
        _post_promo_for_account(
            "2",
            {
                "site": "fanza",
                "screen_name": "Ren47291",
                "targets": [{"service": "digital", "floor": "videoa"}],
            },
            "promo_parent",
        )


def test_exclude_after_failure_uses_x_status_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from main_x import _exclude_item_after_post_failure

    marked: list[tuple] = []

    def fake_skip(post_id, account_id, blog_key=None):
        marked.append((post_id, account_id, blog_key))

    monkeypatch.setattr("main_x.mark_post_failed_skip_queue", fake_skip)
    _exclude_item_after_post_failure("item-9", "2", "Ren47291")
    assert marked == [("item-9", "2", "x:2")]
