"""ライブドア内部リンク（URL抽出・関連記事・ジャンルハブ）の単体テスト。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from db.blog_repository import list_livedoor_hub_blog_rows
from db import post_repository as pr
from livedoor_blog.internal_links import (
    build_genre_hub_items,
    default_genre_label,
    genre_hub_section_html,
    parse_atompub_public_url,
    pick_related_posts,
    related_posts_section_html,
    score_related_candidate,
)
from livedoor_blog.post import build_livedoor_blog_html


ATOMPUB_WITH_ALTERNATE = """<?xml version="1.0" encoding="UTF-8"?>
<entry xmlns="http://www.w3.org/2005/Atom">
  <title>T</title>
  <link rel="alternate" type="text/html"
    href="http://blog.livedoor.jp/staff/archives/12345.html" />
  <link rel="edit" type="application/atom+xml;type=entry"
    href="https://livedoor.blogcms.jp/atompub/staff/article/12345" />
</entry>
"""

ATOMPUB_XML_BASE_ONLY = """<?xml version="1.0" encoding="UTF-8"?>
<entry xmlns="http://www.w3.org/2005/Atom">
  <content type="text/html" xml:base="http://demo.blog.jp/archives/999.html">x</content>
  <link rel="edit" href="https://livedoor.blogcms.jp/atompub/demo/article/999" />
</entry>
"""

ATOMPUB_EDIT_ONLY = """<?xml version="1.0" encoding="UTF-8"?>
<entry xmlns="http://www.w3.org/2005/Atom">
  <link rel="edit" href="https://livedoor.blogcms.jp/atompub/staff/article/777" />
</entry>
"""


def test_parse_atompub_public_url_alternate() -> None:
    assert (
        parse_atompub_public_url(ATOMPUB_WITH_ALTERNATE)
        == "http://blog.livedoor.jp/staff/archives/12345.html"
    )


def test_parse_atompub_public_url_xml_base() -> None:
    assert (
        parse_atompub_public_url(ATOMPUB_XML_BASE_ONLY)
        == "http://demo.blog.jp/archives/999.html"
    )


def test_parse_atompub_public_url_edit_fallback_with_base() -> None:
    url = parse_atompub_public_url(
        ATOMPUB_EDIT_ONLY,
        public_base_url="https://blog.livedoor.jp/staff/",
    )
    assert url == "https://blog.livedoor.jp/staff/archives/777.html"


def test_parse_atompub_public_url_edit_fallback_blog_name() -> None:
    url = parse_atompub_public_url(ATOMPUB_EDIT_ONLY, blog_name="staff")
    assert url == "https://blog.livedoor.jp/staff/archives/777.html"


def test_parse_atompub_public_url_empty_and_no_fallback() -> None:
    assert parse_atompub_public_url("") is None
    assert parse_atompub_public_url(ATOMPUB_EDIT_ONLY) is None
    assert parse_atompub_public_url("<entry></entry>") is None


def test_score_and_pick_related_posts() -> None:
    current = {
        "id": "cur",
        "series": "シリーズA",
        "actress": [{"name": "花子"}],
        "maker": "メーカーX",
        "genres": ["巨乳", "中出し"],
    }
    same_series = {
        "id": "a",
        "title": "同シリーズ",
        "url": "https://blog.livedoor.jp/x/archives/1.html",
        "series": "シリーズA",
        "posted_at": "2026-01-01T00:00:00+00:00",
    }
    same_actress = {
        "id": "b",
        "title": "同出演",
        "url": "https://blog.livedoor.jp/x/archives/2.html",
        "actress": [{"name": "花子"}],
        "posted_at": "2026-02-01T00:00:00+00:00",
    }
    weak = {
        "id": "c",
        "title": "弱い関連",
        "url": "https://blog.livedoor.jp/x/archives/3.html",
        "genres": ["巨乳"],
        "posted_at": "2026-03-01T00:00:00+00:00",
    }
    assert score_related_candidate(current, same_series) > score_related_candidate(
        current, same_actress
    )
    picked = pick_related_posts(
        [weak, same_actress, same_series, {"id": "cur", "title": "自", "url": "https://x"}],
        current,
        limit=2,
    )
    assert [p["dmm_item_id"] for p in picked] == ["a", "b"]


def test_pick_related_skips_bad_urls_and_respects_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVEDOOR_RELATED_POSTS_LIMIT", "1")
    current = {"id": "cur"}
    rows = [
        {
            "id": "1",
            "title": "A",
            "url": "not-a-url",
            "posted_at": "2026-01-02",
        },
        {
            "id": "2",
            "title": "B",
            "url": "https://blog.livedoor.jp/x/archives/2.html",
            "posted_at": "2026-01-01",
        },
        {
            "id": "3",
            "title": "C",
            "url": "https://blog.livedoor.jp/x/archives/3.html",
            "posted_at": "2026-01-03",
        },
    ]
    picked = pick_related_posts(rows, current)
    assert len(picked) == 1
    assert picked[0]["dmm_item_id"] == "3"


def test_related_and_hub_html_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    related = [
        {
            "title": "関連A",
            "url": "https://blog.livedoor.jp/x/archives/1.html",
            "dmm_item_id": "1",
        }
    ]
    html = related_posts_section_html(related)
    assert "ld-related" in html
    assert "あわせて読みたい" in html
    assert "関連A" in html

    monkeypatch.setenv("LIVEDOOR_RELATED_POSTS", "0")
    assert related_posts_section_html(related) == ""

    hub = build_genre_hub_items(
        [
            {
                "genre_label": "コミック",
                "public_base_url": "https://blog.livedoor.jp/comic/",
                "floor": "comic",
            },
            {
                "genre_label": "AV",
                "public_base_url": "https://blog.livedoor.jp/av/",
                "floor": "videoa",
            },
            {
                "genre_label": "素人",
                "public_base_url": "https://blog.livedoor.jp/ama/",
                "floor": "videoc",
            },
        ],
        current_floor="videoa",
    )
    hub_html = genre_hub_section_html(hub)
    assert "ld-genre-hub" in hub_html
    assert 'href="https://blog.livedoor.jp/comic/"' in hub_html
    assert "AV" in hub_html
    assert 'href="https://blog.livedoor.jp/av/"' not in hub_html

    monkeypatch.setenv("LIVEDOOR_GENRE_HUB", "0")
    assert genre_hub_section_html(hub) == ""


def test_genre_hub_hidden_when_only_current() -> None:
    hub = build_genre_hub_items(
        [
            {
                "genre_label": "AV",
                "public_base_url": "https://blog.livedoor.jp/av/",
                "floor": "videoa",
            }
        ],
        current_floor="videoa",
    )
    assert genre_hub_section_html(hub) == ""


def test_default_genre_label() -> None:
    assert default_genre_label("comic") == "コミック"
    assert default_genre_label("digital_doujin") == "同人誌"
    assert default_genre_label("photo") == "写真集"
    assert default_genre_label("novel") == "小説"
    assert default_genre_label("unknown") == ""


def test_resolve_genre_hub_for_dmm() -> None:
    from main_livedoor_atompub import _resolve_genre_hub_for_post

    rows = [
        {
            "blog_id": "spite400k",
            "floor": "comic",
            "hub_group": "dmm",
            "genre_label": "コミック",
            "public_base_url": "https://blog.livedoor.jp/spite400k/",
        },
        {
            "blog_id": "spite400k-hp7qpmu3",
            "floor": "photo",
            "hub_group": "dmm",
            "genre_label": "写真集",
            "public_base_url": "https://blog.livedoor.jp/spite400k-hp7qpmu3/",
        },
        {
            "blog_id": "fanza-av",
            "floor": "videoa",
            "hub_group": "fanza",
            "genre_label": "AV",
            "public_base_url": "https://blog.livedoor.jp/fanza-av/",
        },
    ]
    items = _resolve_genre_hub_for_post(
        rows[1],
        rows,
        site_portal="dmm",
        floor="photo",
    )
    assert len(items) == 2
    by_label = {x["label"]: x["url"] for x in items}
    assert by_label["写真集"] == ""
    assert by_label["コミック"] == "https://blog.livedoor.jp/spite400k/"
    assert "AV" not in by_label


def test_resolve_genre_hub_prefers_matching_site_group() -> None:
    from main_livedoor_atompub import _resolve_genre_hub_for_post

    rows = [
        {
            "blog_id": "a",
            "floor": "videoa",
            "hub_group": "fanza",
            "public_base_url": "https://blog.livedoor.jp/a/",
        },
        {
            "blog_id": "b",
            "floor": "videoc",
            "hub_group": "fanza",
            "public_base_url": "https://blog.livedoor.jp/b/",
        },
        {
            "blog_id": "c",
            "floor": "comic",
            "hub_group": "dmm",
            "public_base_url": "https://blog.livedoor.jp/c/",
        },
        {
            "blog_id": "d",
            "floor": "photo",
            "hub_group": "dmm",
            "public_base_url": "https://blog.livedoor.jp/d/",
        },
    ]
    # ld_cfg に hub_group が無くても site_portal=dmm なら dmm グループを選ぶ
    items = _resolve_genre_hub_for_post(
        {"floor": "comic", "blog_id": "c"},
        rows,
        site_portal="dmm",
        floor="comic",
    )
    labels = {x["label"] for x in items}
    assert labels == {"コミック", "写真集"}


def test_resolve_genre_hub_empty_without_hub_group() -> None:
    from main_livedoor_atompub import _resolve_genre_hub_for_post

    assert (
        _resolve_genre_hub_for_post(
            {"floor": "comic"},
            [{"floor": "comic", "public_base_url": "https://blog.livedoor.jp/x/"}],
            site_portal="dmm",
            floor="comic",
        )
        == []
    )


def test_list_livedoor_hub_blog_rows() -> None:
    rows = list_livedoor_hub_blog_rows(
        [
            {
                "hub_group": "fanza",
                "public_base_url": "https://blog.livedoor.jp/c/",
                "floor": "comic",
                "blog_id": "c",
            },
            {
                "hub_group": "other",
                "public_base_url": "https://blog.livedoor.jp/x/",
                "floor": "videoa",
                "blog_id": "x",
            },
            {
                "hub_group": "fanza",
                "public_base_url": "",
                "floor": "videoc",
                "blog_id": "v",
            },
        ],
        hub_group="fanza",
    )
    assert len(rows) == 1
    assert rows[0]["genre_label"] == "コミック"


def test_build_livedoor_html_includes_related_and_hub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DMM_PREMIUM_AFFILIATE_URL", raising=False)
    monkeypatch.delenv("FANZA_PREMIUM_AFFILIATE_URL", raising=False)
    html = build_livedoor_blog_html(
        title="作品",
        twitter_text="本文",
        affiliate_url="https://example.com/item",
        portal_url="https://fanzaportal.com/videoa/cid",
        article_style="simple",
        related_posts=[
            {
                "title": "前の記事",
                "url": "https://blog.livedoor.jp/x/archives/9.html",
                "dmm_item_id": "9",
            }
        ],
        genre_hub_items=[
            {"label": "コミック", "url": "https://blog.livedoor.jp/c/"},
            {"label": "AV", "url": ""},
            {"label": "素人", "url": "https://blog.livedoor.jp/a/"},
        ],
    )
    assert "ld-related" in html
    assert "ld-genre-hub" in html
    assert html.index("ld-aff-cta") < html.index("ld-related")
    assert html.index("ld-related") < html.index("ld-genre-hub")


def test_mark_post_as_posted_writes_external_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class _Query:
        def __init__(self, table: str) -> None:
            self.table = table
            self._filters: dict[str, Any] = {}

        def select(self, *_a: Any, **_k: Any) -> "_Query":
            return self

        def eq(self, k: str, v: Any) -> "_Query":
            self._filters[k] = v
            return self

        def limit(self, *_a: Any, **_k: Any) -> "_Query":
            return self

        def update(self, payload: dict[str, Any]) -> "_Query":
            calls.append(("update", payload))
            return self

        def insert(self, payload: dict[str, Any]) -> "_Query":
            calls.append(("insert", payload))
            return self

        def execute(self) -> MagicMock:
            if self.table == "trn_dmm_item_blog_post_status" and not any(
                c[0] in ("update", "insert") for c in calls
            ):
                # existing select → 空 → insert 経路
                return MagicMock(data=[])
            return MagicMock(data=[{"id": "row1"}] if calls else [])

    class _Sb:
        def table(self, name: str) -> _Query:
            return _Query(name)

    monkeypatch.setattr(pr, "init_supabase", lambda _account: _Sb())
    pr.mark_post_as_posted(
        "item-1",
        "2",
        blog_key="livedoor:demo",
        external_ref="https://blog.livedoor.jp/demo/archives/1.html",
    )
    assert calls
    op, payload = calls[0]
    assert op == "insert"
    assert payload["external_ref"].endswith("/archives/1.html")
    assert payload["is_posted"] is True


def test_list_related_blog_posts_filters_and_ranks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StatusQ:
        def select(self, *_a: Any, **_k: Any) -> "_StatusQ":
            return self

        def eq(self, *_a: Any, **_k: Any) -> "_StatusQ":
            return self

        @property
        def not_(self) -> "_StatusQ":
            return self

        def is_(self, *_a: Any, **_k: Any) -> "_StatusQ":
            return self

        def order(self, *_a: Any, **_k: Any) -> "_StatusQ":
            return self

        def limit(self, *_a: Any, **_k: Any) -> "_StatusQ":
            return self

        def execute(self) -> MagicMock:
            return MagicMock(
                data=[
                    {
                        "dmm_item_id": "a",
                        "external_ref": "https://blog.livedoor.jp/x/archives/1.html",
                        "posted_at": "2026-01-01T00:00:00+00:00",
                    },
                    {
                        "dmm_item_id": "b",
                        "external_ref": "https://blog.livedoor.jp/x/archives/2.html",
                        "posted_at": "2026-02-01T00:00:00+00:00",
                    },
                    {
                        "dmm_item_id": "cur",
                        "external_ref": "https://blog.livedoor.jp/x/archives/9.html",
                        "posted_at": "2026-03-01T00:00:00+00:00",
                    },
                ]
            )

    class _ItemsQ:
        def select(self, *_a: Any, **_k: Any) -> "_ItemsQ":
            return self

        def in_(self, *_a: Any, **_k: Any) -> "_ItemsQ":
            return self

        def execute(self) -> MagicMock:
            return MagicMock(
                data=[
                    {
                        "id": "a",
                        "title": "同シリーズ",
                        "series": "S1",
                        "actress": None,
                        "author": None,
                        "maker": None,
                        "genres": [],
                    },
                    {
                        "id": "b",
                        "title": "別作品",
                        "series": None,
                        "actress": None,
                        "author": None,
                        "maker": None,
                        "genres": [],
                    },
                ]
            )

    class _Sb:
        def table(self, name: str) -> Any:
            if name == "trn_dmm_item_blog_post_status":
                return _StatusQ()
            return _ItemsQ()

    monkeypatch.setattr(pr, "init_supabase", lambda _a: _Sb())
    related = pr.list_related_blog_posts(
        "2",
        "livedoor:x",
        {"id": "cur", "series": "S1"},
        limit=3,
    )
    assert related[0]["dmm_item_id"] == "a"
    assert "同シリーズ" in related[0]["title"]


def test_list_related_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEDOOR_RELATED_POSTS", "0")
    assert pr.list_related_blog_posts("2", "livedoor:x", {"id": "1"}) == []
