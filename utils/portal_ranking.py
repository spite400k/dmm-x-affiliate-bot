"""FANZA Portal / DMM Portal の週間ランキングページを取得してタイトル一覧を抽出する。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}


@dataclass
class RankingItem:
    rank: int
    title: str


@dataclass
class RankingPage:
    headline: str
    updated: str
    items: list[RankingItem]

# ---------------------
# ランキングHTML取得
# ---------------------
def fetch_ranking_html(url: str, timeout: int = 25) -> str:
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text

# ---------------------
# 文字列正規化
# ---------------------
def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

# ---------------------
# FANZA Portal 週間ランキングパース
# ---------------------
def parse_fanza_portal_weekly(html: str) -> RankingPage | None:
    """www.fanzaportal.com の週間ランキング SSR HTML をパースする。"""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("main h1.text-2xl")
    if not h1:
        h1 = soup.select_one("main h1")
    if not h1:
        logger.warning("FANZA Portal: h1 が見つかりません")
        return None
    headline = _norm_ws(h1.get_text())

    updated_el = soup.select_one("main p.text-sm.text-gray-500.mb-6")
    updated = _norm_ws(updated_el.get_text()) if updated_el else ""

    items: list[RankingItem] = []
    for art in soup.select('main article[id^="rank-"]'):
        rid = art.get("id") or ""
        m = re.match(r"rank-(\d+)", rid)
        if not m:
            continue
        rank = int(m.group(1))
        link = art.select_one("h2 a")
        if not link:
            continue
        title = _norm_ws(link.get_text())
        if title:
            items.append(RankingItem(rank=rank, title=title))

    items.sort(key=lambda x: x.rank)
    if not items:
        logger.warning("FANZA Portal: ランキング項目が0件です")
        return None
    return RankingPage(headline=headline, updated=updated, items=items)

# ---------------------
# DMM Portal 週間ランキングパース
# ---------------------
def parse_dmm_portal_weekly(html: str) -> RankingPage | None:
    """www.dmmportal.jp の週間ランキング SSR HTML をパースする。"""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("main h1.text-2xl")
    if not h1:
        h1 = soup.select_one("main h1")
    if not h1:
        logger.warning("DMM Portal: h1 が見つかりません")
        return None
    headline = _norm_ws(h1.get_text())

    updated_el = soup.select_one("main p.text-sm.text-gray-500.mb-6")
    updated = _norm_ws(updated_el.get_text()) if updated_el else ""

    ol = soup.select_one("main ol.space-y-8")
    if not ol:
        logger.warning("DMM Portal: ランキングの ol が見つかりません")
        return None

    items: list[RankingItem] = []
    for li in ol.find_all("li", recursive=False):
        h2 = li.find("h2")
        if not h2:
            continue
        link = h2.find("a", href=True)
        if not link:
            continue
        raw = _norm_ws(h2.get_text())
        m = re.match(r"#\s*(\d+)", raw)
        if not m:
            continue
        rank = int(m.group(1))
        title = _norm_ws(link.get_text())
        if title:
            items.append(RankingItem(rank=rank, title=title))

    items.sort(key=lambda x: x.rank)
    if not items:
        logger.warning("DMM Portal: ランキング項目が0件です")
        return None
    return RankingPage(headline=headline, updated=updated, items=items)

# ---------------------
# 週間ランキングページパース
# ---------------------
def parse_weekly_ranking_page(url: str, html: str) -> RankingPage | None:
    if "fanzaportal.com" in url:
        return parse_fanza_portal_weekly(html)
    if "dmmportal.jp" in url:
        return parse_dmm_portal_weekly(html)
    logger.error("未対応のポータル URL です: %s", url)
    return None

# ---------------------
# 週間ランキングページ取得
# ---------------------
def fetch_weekly_ranking(url: str) -> RankingPage | None:
    html = fetch_ranking_html(url)
    return parse_weekly_ranking_page(url, html)
