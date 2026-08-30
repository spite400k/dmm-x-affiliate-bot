"""Seesaa 投稿のアダルト除外と XML-RPC ヘルパーのテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

from config.blog_settings import BLOG_ACCOUNT_SETTINGS
from seesaa_blog.rpc import (
    is_seesaa_access_denied,
    normalize_rpc_url,
    rpc_endpoint_candidates,
)
from utils.blog_targets import is_adult_blog_target, is_adult_item_row


def test_dmm_ebook_targets_are_not_adult() -> None:
    assert is_adult_blog_target("dmm", "ebook", "comic") is False
    assert is_adult_blog_target("DMM.com", "ebook", "photo") is False
    assert is_adult_blog_target("dmm", "ebook", "novel") is False


def test_fanza_and_adult_floors_are_adult() -> None:
    assert is_adult_blog_target("fanza", "ebook", "comic") is True
    assert is_adult_blog_target("dmm", "digital", "videoa") is True
    assert is_adult_blog_target("dmm", "digital", "videoc") is True
    assert is_adult_blog_target("", "doujin", "digital_doujin") is True
    assert is_adult_blog_target(None, "digital", "anime") is True


def test_account_1_config_targets_are_non_adult() -> None:
    acc = BLOG_ACCOUNT_SETTINGS["1"]
    assert acc["site"] == "dmm"
    for t in acc["targets"]:
        assert is_adult_blog_target(acc["site"], t["service"], t["floor"]) is False


def test_is_adult_item_row_detects_fanza_site() -> None:
    assert is_adult_item_row({"site": "FANZA", "service": "ebook", "floor": "comic"})
    assert not is_adult_item_row(
        {"site": "DMM.com", "service": "ebook", "floor": "comic"}
    )
    assert not is_adult_item_row(None)


def test_run_seesaa_one_item_skips_adult_target(monkeypatch) -> None:
    from main_seesaa_blog import run_seesaa_one_item

    fetch = MagicMock()
    monkeypatch.setattr("main_seesaa_blog.get_next_livedoor_post", fetch)
    ok = run_seesaa_one_item(
        "1",
        "digital",
        "videoa",
        "fanza",
        {"blog_key": "seesaa:test"},
        dry=True,
        no_mark_posted=True,
        publish=False,
    )
    assert ok is False
    fetch.assert_not_called()


def test_run_seesaa_one_item_skips_adult_item_without_posting(monkeypatch) -> None:
    from main_seesaa_blog import run_seesaa_one_item

    monkeypatch.setattr(
        "main_seesaa_blog.get_next_livedoor_post",
        lambda *a, **k: {
            "id": "item-1",
            "content_id": "abc",
            "service": "ebook",
            "floor": "comic",
            "site": "FANZA",
            "title": "adult title",
        },
    )
    post_fn = MagicMock()
    monkeypatch.setattr("main_seesaa_blog.meta_weblog_new_post", post_fn)
    ok = run_seesaa_one_item(
        "1",
        "ebook",
        "comic",
        "dmm",
        {"blog_key": "seesaa:test"},
        dry=True,
        no_mark_posted=True,
        publish=False,
    )
    assert ok is False
    post_fn.assert_not_called()


def test_list_seesaa_blogs_passes_appkey(monkeypatch) -> None:
    from main_seesaa_blog import list_seesaa_blogs

    calls: list[tuple] = []

    class _Proxy:
        class blogger:
            @staticmethod
            def getUsersBlogs(*args: object) -> list:
                calls.append(args)
                return []

    monkeypatch.setattr(
        "main_seesaa_blog.seesaa_xmlrpc_call",
        lambda url, fn: fn(_Proxy()),
    )
    assert list_seesaa_blogs("https://blog.seesaa.jp/rpc", "user@example.com", "secret") == []
    assert calls == [("", "user@example.com", "secret")]


def test_seesaa_rpc_endpoint_candidates() -> None:
    assert normalize_rpc_url("https://blog.seesaa.jp/rpc/") == "https://blog.seesaa.jp/rpc"
    urls = rpc_endpoint_candidates("https://blog.seesaa.jp/rpc")
    assert urls == ["https://blog.seesaa.jp/rpc"]
    assert rpc_endpoint_candidates("https://ssl.seesaa.jp/blog/rpc") == []


def test_is_seesaa_access_denied_includes_405() -> None:
    import xmlrpc.client

    assert is_seesaa_access_denied(
        xmlrpc.client.ProtocolError("https://ssl.seesaa.jp/blog/rpc", 405, "Not Allowed", {})
    )
    assert is_seesaa_access_denied(
        xmlrpc.client.ProtocolError("https://blog.seesaa.jp/rpc", 403, "Forbidden", {})
    )
