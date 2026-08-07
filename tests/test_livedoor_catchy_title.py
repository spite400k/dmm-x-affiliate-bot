"""Livedoor キャッチタイトル（スマホ新着向け）の単体テスト。"""

from __future__ import annotations

import pytest

from livedoor_blog.post import (
    _ATOMPUB_TITLE_MAX_CHARS,
    _build_mobile_catchy_title,
    _strip_trailing_credit,
    _title_hook_front,
    blog_post_title_for_item,
)


@pytest.fixture(autouse=True)
def _catchy_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEDOOR_CATCHY_TITLE", "1")


def test_hook_front_keeps_first_sentence() -> None:
    raw = "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。 明日葉みつは"
    assert _title_hook_front(raw) == "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。"


def test_strip_trailing_credit() -> None:
    core = "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。 明日葉みつは"
    assert _strip_trailing_credit(core, ["明日葉みつは"]) == (
        "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る"
    )


def test_mobile_catchy_leads_with_actress() -> None:
    core = "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。 明日葉みつは"
    got = _build_mobile_catchy_title(core, ["明日葉みつは"])
    assert got.startswith("明日葉みつは｜")
    assert "高身長の貧困女学生" in got
    assert got.endswith("｜レビュー")
    assert len(got) <= _ATOMPUB_TITLE_MAX_CHARS


def test_blog_post_title_for_item_with_actress() -> None:
    title = "高身長の貧困女学生は小さいおじさん達に群がられ貪られ春を売る。 明日葉みつは"
    item = {"actress": [{"name": "明日葉みつは"}], "service": "digital"}
    got = blog_post_title_for_item(title, item)
    assert got.startswith("明日葉みつは｜高身長")
    assert "｜レビュー" in got


def test_blog_post_title_off_returns_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEDOOR_CATCHY_TITLE", "0")
    title = "長い商品名そのままです。"
    assert blog_post_title_for_item(title, {"actress": "誰か"}) == title


def test_blog_post_title_without_credit_still_shortens() -> None:
    title = (
        "ガテン女上司と突然の豪雨で現場から帰れなくなり…"
        "カラダを温めあううち色っぽい濡れ髪濡れ肌に理性爆発ワゴン車内"
    )
    got = blog_post_title_for_item(title, {"service": "digital"})
    assert got.endswith("｜レビュー")
    assert len(got) < len(title) + 10
    # 先頭フックが残っている
    assert got.startswith("ガテン女上司")


def test_ebook_bonus_title_is_compact() -> None:
    title = "【電子版限定特典付き】なにかの写真集タイトルがとても長い場合の例です 誰か"
    item = {
        "service": "ebook",
        "floor": "photo",
        "author": [{"name": "誰か"}],
    }
    got = blog_post_title_for_item(title, item)
    assert "【電子版" in got
    assert "誰か" in got
    assert len(got) <= _ATOMPUB_TITLE_MAX_CHARS
