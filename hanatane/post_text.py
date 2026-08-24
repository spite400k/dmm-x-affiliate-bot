"""@hanatane_app 向け投稿文案の組み立て。"""

from __future__ import annotations

import re

from hanatane.discover import DiscoverTopic, short_title

WEB_URL = "https://hanatane.onecoin-photo.net/discover"


def _normalize_question(hint: str, *, fallback: str) -> str:
    text = re.sub(r"\s+", " ", (hint or "").strip())
    if not text:
        return fallback
    if text.endswith("？") or text.endswith("?"):
        return text
    return text + "？"


def build_news_card_post(topic: DiscoverTopic) -> tuple[str, str]:
    """時事ネタカード(A): 親投稿 + スレッド返信。"""
    headline = short_title(topic.title)
    question = _normalize_question(
        topic.hint,
        fallback=f"「{headline}」、どう思う？",
    )

    parent = "\n".join(
        [
            f"【今日のネタ】{headline}",
            "",
            "投げかけ:",
            f"「{question}」",
            "",
            "深掘り: 自分の答えを先に言ってから振る。",
        ]
    )

    thread_lines = [
        "深掘りヒント:",
        "・答えが来たら「なんでそう思う？」で伸ばす",
        "・自分の体験を1文だけ先に出す",
    ]
    if topic.source_url:
        thread_lines.append(f"背景: {topic.source_url}")
    thread_lines.append(f"お題ストック: {WEB_URL}")

    return parent, "\n".join(thread_lines)


def build_silence_tip_post(tip: str) -> tuple[str, str]:
    """沈黙Tips(D): 親 + スレッド。"""
    parent = tip.strip()
    thread = (
        "同文の「沈黙対策 #n」連投はやめて、"
        "毎回違うTipsだけ出しています。\n\n"
        f"お題が欲しいとき: {WEB_URL}"
    )
    return parent, thread


def build_demo_post(*, caption: str | None = None) -> tuple[str, str]:
    """短尺デモ(C)用キャプション。"""
    parent = caption or (
        "詰まったときの「次のお題」出し方（20秒）\n\n"
        "読むためじゃなく、リスナーに振るためのカード。"
    )
    thread = (
        "使い方のコツ:\n"
        "お題を出したら、すぐ自分で答えきらない。\n"
        "「みんななら？」を残す。"
    )
    return parent, thread
