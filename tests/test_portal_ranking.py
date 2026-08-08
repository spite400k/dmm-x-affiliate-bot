"""utils.portal_ranking のパース処理のユニットテスト（ネットワーク不要）。"""

from __future__ import annotations

import pytest

from utils.portal_ranking import (
    parse_dmm_portal_weekly,
    parse_fanza_portal_weekly,
    parse_weekly_ranking_page,
)


FANZA_HTML_MIN = """
<!DOCTYPE html>
<html><body>
<main class="mx-auto max-w-6xl">
<h1 class="text-2xl font-bold mb-4">2026年1週目｜動画(AV)ジャンル 今週の人気ランキングTOP2</h1>
<p class="text-sm text-gray-500 mb-6">最終更新日: 2026年1月1日</p>
<article id="rank-2" class="group">
  <div class="flex flex-1 flex-col p-4 pt-3">
    <h2 class="line-clamp-2 text-base font-bold">
      <a href="/videoa/aaa">2位の作品タイトル</a>
    </h2>
  </div>
</article>
<article id="rank-1" class="group">
  <div class="flex flex-1 flex-col p-4 pt-3">
    <h2 class="line-clamp-2 text-base font-bold">
      <a href="/videoa/bbb">1位の作品タイトル</a>
    </h2>
  </div>
</article>
</main>
</body></html>
"""

DMM_HTML_MIN = """
<!DOCTYPE html>
<html><body>
<main class="max-w-4xl mx-auto px-4 py-8">
<h1 class="text-2xl font-bold mb-4">2026年1週目｜コミックジャンル 今週の人気ランキングTOP2</h1>
<p class="text-sm text-gray-500 mb-6">最終更新日: 2026年1月2日</p>
<ol class="space-y-8">
<li>
  <h2 class="text-lg font-semibold">#<!-- -->1<!-- -->
    <a class="text-blue-600 hover:underline" href="/ebook/comic/x">テストコミックA</a>
  </h2>
  <div class="text-sm text-gray-600 mt-2"><p>人気スコア: <!-- -->10</p></div>
</li>
<li>
  <h2 class="text-lg font-semibold">#2 <a class="text-blue-600" href="/ebook/comic/y">テストコミックB</a></h2>
</li>
</ol>
</main>
</body></html>
"""


def test_parse_fanza_portal_weekly_minimal() -> None:
    page = parse_fanza_portal_weekly(FANZA_HTML_MIN)
    assert page is not None
    assert "2026年1週目" in page.headline
    assert "動画(AV)" in page.headline
    assert "2026年1月1日" in page.updated
    assert len(page.items) == 2
    ranks = [x.rank for x in page.items]
    assert ranks == [1, 2]
    assert page.items[0].title == "1位の作品タイトル"
    assert page.items[1].title == "2位の作品タイトル"
    assert page.items[0].url.endswith("/videoa/bbb")
    assert page.items[1].url.endswith("/videoa/aaa")


def test_parse_dmm_portal_weekly_minimal() -> None:
    page = parse_dmm_portal_weekly(DMM_HTML_MIN)
    assert page is not None
    assert "コミック" in page.headline
    assert "2026年1月2日" in page.updated
    assert len(page.items) == 2
    assert [x.rank for x in page.items] == [1, 2]
    assert page.items[0].title == "テストコミックA"
    assert page.items[1].title == "テストコミックB"
    assert page.items[0].url.endswith("/ebook/comic/x")
    assert page.items[1].url.endswith("/ebook/comic/y")


def test_parse_weekly_ranking_page_dispatches_by_url() -> None:
    u_f = "https://www.fanzaportal.com/ranking/videoa/weekly"
    u_d = "https://www.dmmportal.jp/ranking/ebook/comic/weekly"
    assert parse_weekly_ranking_page(u_f, FANZA_HTML_MIN) is not None
    assert parse_weekly_ranking_page(u_d, DMM_HTML_MIN) is not None


def test_parse_weekly_ranking_page_unknown_domain() -> None:
    assert (
        parse_weekly_ranking_page("https://example.com/ranking", FANZA_HTML_MIN)
        is None
    )


def test_parse_fanza_returns_none_without_main_h1() -> None:
    assert parse_fanza_portal_weekly("<html><body></body></html>") is None


def test_parse_dmm_returns_none_without_ol() -> None:
    html = """
    <main><h1 class="text-2xl font-bold mb-4">タイトル</h1>
    <p class="text-sm text-gray-500 mb-6">更新</p></main>
    """
    assert parse_dmm_portal_weekly(html) is None
