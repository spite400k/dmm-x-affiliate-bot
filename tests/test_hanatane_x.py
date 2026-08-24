"""@hanatane_app X 投稿ロジックのテスト。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config.hanatane_settings import WEEKDAY_MODES
from hanatane.discover import DiscoverTopic, parse_discover_topics, short_title
from hanatane.post_text import build_news_card_post, build_silence_tip_post
from hanatane.schedule import resolve_mode_for_today
from hanatane.state import PostState, pick_silence_tip_index, pick_unposted_topic

SAMPLE_HTML = """
<ul>
  <li>
    <span>ゲーム</span>
    <h2>新作ゲーム「HoloCozy」を知ってる？</h2>
    <p>説明文</p>
    <p>話題のヒント</p>
    <p>デスクトップ常駐型ゲーム「HoloCozy」に、いざ遊びに行くなら、あなたはどんな部屋を作りたい？</p>
    <a href="https://www.moguravr.com/holocozy/">元記事を読む</a>
  </li>
</ul>
"""


def test_parse_discover_topics() -> None:
    topics = parse_discover_topics(SAMPLE_HTML)
    assert len(topics) == 1
    assert topics[0].title == "新作ゲーム「HoloCozy」を知ってる？"
    assert "部屋を作りたい" in topics[0].hint
    assert topics[0].category == "ゲーム"
    assert topics[0].source_url.endswith("/holocozy/")


def test_short_title() -> None:
    assert short_title("短い") == "短い"
    long = "あ" * 40
    assert len(short_title(long)) <= 28


def test_build_news_card_post() -> None:
    topic = DiscoverTopic(
        title="HoloCozy、部屋どう作る？",
        hint="どんな部屋を作りたい？",
        category="ゲーム",
        source_url="https://example.com",
    )
    parent, thread = build_news_card_post(topic)
    assert "【今日のネタ】" in parent
    assert "投げかけ:" in parent
    assert "どんな部屋を作りたい？" in parent
    assert "深掘りヒント:" in thread
    assert "example.com" in thread


def test_build_silence_tip_post() -> None:
    parent, thread = build_silence_tip_post("10秒待つ。")
    assert "10秒待つ。" in parent
    assert "沈黙対策 #n" in thread


def test_pick_unposted_topic() -> None:
    topics = [
        DiscoverTopic("A", "", "", ""),
        DiscoverTopic("B", "", "", ""),
    ]
    state = PostState(posted_titles=["A"])
    picked = pick_unposted_topic(topics, state, max_history=10)
    assert picked is not None
    assert picked.key == "B"


def test_pick_silence_tip_index_rotates() -> None:
    state = PostState(posted_tip_indices=[0, 1])
    assert pick_silence_tip_index(4, state) == 2


def test_resolve_mode_for_today_monday(monkeypatch) -> None:
    monkeypatch.delenv("HANATANE_FORCE_MODE", raising=False)
    monday = datetime(2026, 8, 24, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert resolve_mode_for_today(now=monday) == WEEKDAY_MODES[0]


def test_resolve_mode_force(monkeypatch) -> None:
    monkeypatch.setenv("HANATANE_FORCE_MODE", "news_card")
    assert resolve_mode_for_today(now=datetime(2026, 8, 23, tzinfo=ZoneInfo("Asia/Tokyo"))) == "news_card"
