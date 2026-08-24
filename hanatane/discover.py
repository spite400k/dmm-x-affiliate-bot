"""ハナタネ Discover から公開ネタを取得する。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import unescape

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_DISCOVER_URL = "https://hanatane.onecoin-photo.net/discover"
USER_AGENT = "HanataneXBot/1.0 (+https://hanatane.onecoin-photo.net/discover)"


@dataclass(frozen=True)
class DiscoverTopic:
    """Discover 上の1ネタ。"""

    title: str
    hint: str
    category: str
    source_url: str

    @property
    def key(self) -> str:
        return self.title.strip()


def fetch_discover_html(url: str = DEFAULT_DISCOVER_URL, *, timeout: int = 30) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ja"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def parse_discover_topics(html: str) -> list[DiscoverTopic]:
    """Discover HTML からネタカードを抽出する。"""
    soup = BeautifulSoup(html, "html.parser")
    topics: list[DiscoverTopic] = []

    for h2 in soup.find_all("h2"):
        title = h2.get_text(strip=True)
        if not title:
            continue

        container = h2.find_parent("li") or h2.find_parent("article") or h2.parent
        if container is None:
            continue

        hint = _extract_hint(container)
        source_url = _extract_source_url(container)
        category = _extract_category(container)

        topics.append(
            DiscoverTopic(
                title=title,
                hint=hint,
                category=category,
                source_url=source_url,
            )
        )

    return topics


def _extract_hint(container) -> str:
    for p in container.find_all("p"):
        prev = p.find_previous("p")
        if prev and "話題のヒント" in prev.get_text():
            return unescape(p.get_text(strip=True))
    return ""


def _extract_source_url(container) -> str:
    for a in container.find_all("a", href=True):
        if "元記事" in a.get_text():
            return a["href"].strip()
    return ""


def _extract_category(container) -> str:
    for span in container.find_all("span"):
        text = span.get_text(strip=True)
        if text in {"ゲーム", "VTuber", "音楽", "カルチャー", "その他"}:
            return text
    return ""


def fetch_vtuber_topics(url: str = DEFAULT_DISCOVER_URL) -> list[DiscoverTopic]:
    """VTuberニュース系（ゲーム/VTuber/音楽）を優先して返す。"""
    topics = parse_discover_topics(fetch_discover_html(url))
    preferred = {"ゲーム", "VTuber", "音楽"}
    ranked = [t for t in topics if t.category in preferred]
    if ranked:
        return ranked
    return topics


def short_title(title: str, max_chars: int = 28) -> str:
    """【今日のネタ】行用に短縮。"""
    text = re.sub(r"\s+", " ", (title or "").strip())
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rstrip(" 、。")
    return cut + "…"
