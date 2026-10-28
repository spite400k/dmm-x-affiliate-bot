"""ライブドア記事の内部リンク（関連記事・FANZAジャンルハブ）。

docs/livedoor-internal-links-design.md 参照。
"""

from __future__ import annotations

import html as html_module
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_GENRE_LABEL_BY_FLOOR: dict[str, str] = {
    "comic": "コミック",
    "digital_doujin": "同人誌",
    "videoa": "AV",
    "videoc": "素人",
}

_RE_LINK_ALTERNATE = re.compile(
    r"""<link\b[^>]*\brel\s*=\s*["']alternate["'][^>]*>""",
    re.IGNORECASE,
)
_RE_HREF = re.compile(r"""\bhref\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_RE_TYPE_HTML = re.compile(
    r"""\btype\s*=\s*["']text/html["']""",
    re.IGNORECASE,
)
_RE_XML_BASE = re.compile(
    r"""<content\b[^>]*\bxml:base\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_RE_LINK_EDIT = re.compile(
    r"""<link\b[^>]*\brel\s*=\s*["']edit["'][^>]*>""",
    re.IGNORECASE,
)
_RE_ARTICLE_ID = re.compile(r"/article/(\d+)\s*$", re.IGNORECASE)


def related_posts_enabled() -> bool:
    raw = os.environ.get("LIVEDOOR_RELATED_POSTS", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def related_posts_limit() -> int:
    raw = os.environ.get("LIVEDOOR_RELATED_POSTS_LIMIT", "3").strip()
    try:
        n = int(raw)
    except ValueError:
        return 3
    return max(1, min(5, n))


def related_posts_pool_size() -> int:
    raw = os.environ.get("LIVEDOOR_RELATED_POOL", "30").strip()
    try:
        n = int(raw)
    except ValueError:
        return 30
    return max(related_posts_limit(), min(100, n))


def genre_hub_enabled() -> bool:
    raw = os.environ.get("LIVEDOOR_GENRE_HUB", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def default_genre_label(floor: str | None) -> str:
    fl = str(floor or "").strip().lower()
    return DEFAULT_GENRE_LABEL_BY_FLOOR.get(fl, "")


def is_http_url(url: str) -> bool:
    try:
        p = urlparse((url or "").strip())
    except Exception:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)


def normalize_public_base_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if not u.endswith("/"):
        u += "/"
    return u


def parse_atompub_public_url(
    response_text: str,
    *,
    public_base_url: str = "",
    blog_name: str = "",
) -> str | None:
    """AtomPub 投稿応答から公開記事 URL を抽出する。見つからなければ None。"""
    text = response_text or ""
    if not text.strip():
        return None

    for m in _RE_LINK_ALTERNATE.finditer(text):
        tag = m.group(0)
        if not _RE_TYPE_HTML.search(tag):
            # type 省略の alternate も許容
            pass
        hm = _RE_HREF.search(tag)
        if not hm:
            continue
        href = hm.group(1).strip()
        if is_http_url(href) and "blogcms.jp" not in urlparse(href).netloc:
            return href
        if is_http_url(href) and "/archives/" in href:
            return href

    bm = _RE_XML_BASE.search(text)
    if bm:
        base = bm.group(1).strip()
        if is_http_url(base):
            return base

    article_id = ""
    for m in _RE_LINK_EDIT.finditer(text):
        tag = m.group(0)
        hm = _RE_HREF.search(tag)
        if not hm:
            continue
        am = _RE_ARTICLE_ID.search(hm.group(1).strip())
        if am:
            article_id = am.group(1)
            break
    if not article_id:
        return None

    base = normalize_public_base_url(public_base_url)
    if not base:
        name = (blog_name or "").strip()
        if name:
            base = f"https://blog.livedoor.jp/{name}/"
    if not base:
        return None
    return f"{base}archives/{article_id}.html"


def _credit_names(val: object) -> set[str]:
    if val is None:
        return set()
    if isinstance(val, dict):
        n = val.get("name")
        s = str(n).strip() if n is not None else ""
        return {s} if s else set()
    if isinstance(val, list):
        out: set[str] = set()
        for x in val:
            out |= _credit_names(x)
        return out
    s = str(val).strip()
    if not s:
        return set()
    if s.startswith("["):
        import json

        try:
            parsed = json.loads(s.replace("'", '"'))
        except json.JSONDecodeError:
            return {s}
        return _credit_names(parsed)
    return {s}


def _genre_set(val: object) -> set[str]:
    if val is None:
        return set()
    if isinstance(val, list):
        return {str(g).strip() for g in val if str(g).strip()}
    s = str(val).strip()
    return {s} if s else set()


def score_related_candidate(
    current: dict[str, Any], candidate: dict[str, Any]
) -> int:
    """同一ブログ前提の近さスコア（高いほど優先）。"""
    score = 0
    cur_series = str(current.get("series") or "").strip()
    cand_series = str(candidate.get("series") or "").strip()
    if cur_series and cand_series and cur_series == cand_series:
        score += 100

    cur_credits = _credit_names(current.get("actress")) | _credit_names(
        current.get("author")
    )
    cand_credits = _credit_names(candidate.get("actress")) | _credit_names(
        candidate.get("author")
    )
    if cur_credits and cand_credits and (cur_credits & cand_credits):
        score += 50

    cur_maker = str(current.get("maker") or "").strip()
    cand_maker = str(candidate.get("maker") or "").strip()
    if cur_maker and cand_maker and cur_maker == cand_maker:
        score += 20

    overlap = len(_genre_set(current.get("genres")) & _genre_set(candidate.get("genres")))
    if overlap:
        score += min(25, overlap * 5)
    return score


def pick_related_posts(
    candidates: list[dict[str, Any]],
    current_item: dict[str, Any],
    *,
    limit: int | None = None,
) -> list[dict[str, str]]:
    """候補（item 行 + url）から関連を選ぶ。

    各 candidate に必須: id, title, url（= external_ref）
    任意: series, actress, author, maker, genres, posted_at
    """
    lim = related_posts_limit() if limit is None else max(1, min(5, int(limit)))
    exclude = str(current_item.get("id") or "").strip()
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for row in candidates:
        cid = str(row.get("id") or "").strip()
        url = str(row.get("url") or "").strip()
        title = str(row.get("title") or "").strip()
        if not cid or cid == exclude or not url or not is_http_url(url) or not title:
            continue
        sc = score_related_candidate(current_item, row)
        posted = str(row.get("posted_at") or "")
        ranked.append((sc, posted, row))
    ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)
    out: list[dict[str, str]] = []
    for _sc, _posted, row in ranked[:lim]:
        out.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "dmm_item_id": str(row.get("id") or "").strip(),
            }
        )
    return out


def related_posts_section_html(related: list[dict[str, str]] | None) -> str:
    if not related_posts_enabled() or not related:
        return ""
    items: list[str] = []
    for row in related:
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        if not title or not is_http_url(url):
            continue
        items.append(
            "<li style=\"margin:0.4rem 0;\">"
            f'<a href="{html_module.escape(url, quote=True)}">'
            f"{html_module.escape(title)}</a></li>"
        )
    if not items:
        return ""
    return (
        '<section class="ld-related" style="margin:1.75rem 0;">'
        '<h2 style="margin:0 0 0.75rem;font-size:1.15em;">あわせて読みたい</h2>'
        '<ul style="margin:0;padding-left:1.25rem;">'
        + "".join(items)
        + "</ul></section>"
    )


def build_genre_hub_items(
    hub_rows: list[dict[str, str]],
    *,
    current_floor: str = "",
    current_label: str = "",
) -> list[dict[str, str]]:
    """ハブ表示用。url 空文字 = 現在地（非リンク）。"""
    cur_floor = str(current_floor or "").strip().lower()
    cur_label = str(current_label or "").strip()
    out: list[dict[str, str]] = []
    seen_labels: set[str] = set()
    for row in hub_rows:
        label = str(row.get("genre_label") or "").strip() or default_genre_label(
            row.get("floor")
        )
        base = normalize_public_base_url(str(row.get("public_base_url") or ""))
        if not label or not base or not is_http_url(base):
            continue
        if label in seen_labels:
            continue
        seen_labels.add(label)
        floor = str(row.get("floor") or "").strip().lower()
        is_current = bool(
            (cur_label and label == cur_label)
            or (cur_floor and floor and floor == cur_floor)
        )
        out.append({"label": label, "url": "" if is_current else base})
    return out


def genre_hub_section_html(hub_items: list[dict[str, str]] | None) -> str:
    if not genre_hub_enabled() or not hub_items:
        return ""
    # 他ジャンルへのリンクが1つも無いなら出さない（単独ブログ）
    if not any(str(x.get("url") or "").strip() for x in hub_items):
        return ""
    parts: list[str] = []
    for row in hub_items:
        label = str(row.get("label") or "").strip()
        url = str(row.get("url") or "").strip()
        if not label:
            continue
        if url and is_http_url(url):
            parts.append(
                f'<a href="{html_module.escape(url, quote=True)}">'
                f"{html_module.escape(label)}</a>"
            )
        else:
            parts.append(
                f'<span style="font-weight:600;">{html_module.escape(label)}</span>'
            )
    if len(parts) < 2:
        return ""
    sep = ' <span style="color:#999;">·</span> '
    return (
        '<nav class="ld-genre-hub" style="margin:1.75rem 0;" '
        'aria-label="ジャンルから探す">'
        '<h2 style="margin:0 0 0.75rem;font-size:1.15em;">ジャンルから探す</h2>'
        f'<p style="margin:0;line-height:1.8;">{sep.join(parts)}</p>'
        "</nav>"
    )
