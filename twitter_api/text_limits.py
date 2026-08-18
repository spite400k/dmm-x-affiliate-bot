"""X（Twitter）の加重文字数。URL は t.co 換算。"""

from __future__ import annotations

import re

# 標準投稿の上限。日本語などは重み2。
TWEET_MAX_WEIGHTED = 280
TCO_URL_LENGTH = 23
_ELLIPSIS = "…"
_URL_RE = re.compile(r"https?://\S+")


def is_twitter_heavy_char(ch: str) -> bool:
    """X の加重カウントで重み2になりやすい文字（CJK・全角・絵文字など）。"""
    o = ord(ch)
    return (
        0x1100 <= o <= 0x11FF
        or 0x2E80 <= o <= 0x9FFF
        or 0x3000 <= o <= 0x303F
        or 0xAC00 <= o <= 0xD7AF
        or 0xF900 <= o <= 0xFAFF
        or 0xFF00 <= o <= 0xFFEF
        or 0x1F300 <= o <= 0x1FAFF
    )


def char_weight(ch: str) -> int:
    return 2 if is_twitter_heavy_char(ch) else 1


def twitter_weighted_length(text: str) -> int:
    """X 投稿向けの概算文字数（URL は t.co = 23 として加算）。"""
    urls = _URL_RE.findall(text or "")
    body = text or ""
    for u in urls:
        body = body.replace(u, "", 1)
    weight = sum(char_weight(ch) for ch in body)
    return weight + TCO_URL_LENGTH * len(urls)


def clip_text_weighted(
    text: str,
    max_weight: int,
    *,
    sentence_break: bool = True,
) -> str:
    """加重文字数が max_weight 以下になるよう末尾から切り詰める。

    URL を含む文字列には使わない（t.co 換算とずれ、URL が途中で切れる）。
    """
    text = (text or "").strip()
    if max_weight <= 0 or not text:
        return ""
    if twitter_weighted_length(text) <= max_weight:
        return text

    ellipsis_w = char_weight(_ELLIPSIS)
    use_ellipsis = max_weight >= ellipsis_w
    budget = max_weight - ellipsis_w if use_ellipsis else max_weight

    out: list[str] = []
    w = 0
    for ch in text:
        cw = char_weight(ch)
        if w + cw > budget:
            break
        out.append(ch)
        w += cw
    cut = "".join(out).rstrip(" \t\n\r、,")
    if not cut:
        return ""
    if sentence_break:
        for sep in ("。", "！", "？", "!", "?"):
            idx = cut.rfind(sep)
            if idx >= len(cut) // 2:
                return cut[: idx + 1]
    if use_ellipsis:
        return cut + _ELLIPSIS
    return cut
