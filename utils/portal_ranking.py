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
    url: str = ""
    content_id: str = ""
    actress: str = ""


@dataclass
class RankingPage:
    headline: str
    updated: str
    items: list[RankingItem]


def _absolute_portal_url(page_url: str, href: str) -> str:
    h = (href or "").strip()
    if not h:
        return ""
    if h.startswith("http://") or h.startswith("https://"):
        return h
    if "fanzaportal.com" in page_url:
        origin = "https://www.fanzaportal.com"
    elif "dmmportal.jp" in page_url:
        origin = "https://www.dmmportal.jp"
    else:
        return h
    if h.startswith("/"):
        return origin + h
    return f"{origin}/{h}"


def content_id_from_portal_url(url: str) -> str:
    """ポータル詳細URLから content_id を抜く（例: …/videoa/ipzz00893）。"""
    path = (url or "").strip().rstrip("/")
    if not path:
        return ""
    # /videoa/xxx or /ebook/comic/xxx
    m = re.search(r"/(?:videoa|videoc|anime|nikkatsu|digital_doujin)/([^/?#]+)$", path)
    if m:
        return m.group(1).strip()
    m = re.search(r"/ebook/(?:comic|novel|photo|otherbooks)/([^/?#]+)$", path)
    if m:
        return m.group(1).strip()
    # 最終パス要素のフォールバック
    tail = path.rsplit("/", 1)[-1]
    if tail and "ranking" not in tail and "." not in tail:
        return tail
    return ""

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
def parse_fanza_portal_weekly(html: str, *, page_url: str = "") -> RankingPage | None:
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

    base = page_url or "https://www.fanzaportal.com/"
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
        href = _absolute_portal_url(base, str(link.get("href") or ""))
        if title:
            items.append(
                RankingItem(
                    rank=rank,
                    title=title,
                    url=href,
                    content_id=content_id_from_portal_url(href),
                )
            )

    items.sort(key=lambda x: x.rank)
    if not items:
        logger.warning("FANZA Portal: ランキング項目が0件です")
        return None
    return RankingPage(headline=headline, updated=updated, items=items)

# ---------------------
# DMM Portal 週間ランキングパース
# ---------------------
def parse_dmm_portal_weekly(html: str, *, page_url: str = "") -> RankingPage | None:
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

    base = page_url or "https://www.dmmportal.jp/"
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
        href = _absolute_portal_url(base, str(link.get("href") or ""))
        if title:
            items.append(
                RankingItem(
                    rank=rank,
                    title=title,
                    url=href,
                    content_id=content_id_from_portal_url(href),
                )
            )

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
        return parse_fanza_portal_weekly(html, page_url=url)
    if "dmmportal.jp" in url:
        return parse_dmm_portal_weekly(html, page_url=url)
    logger.error("未対応のポータル URL です: %s", url)
    return None

# ---------------------
# 週間ランキングページ取得
# ---------------------
def fetch_weekly_ranking(url: str) -> RankingPage | None:
    html = fetch_ranking_html(url)
    return parse_weekly_ranking_page(url, html)
