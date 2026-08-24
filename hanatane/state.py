"""投稿済みネタの重複防止。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class PostState:
    posted_titles: list[str] = field(default_factory=list)
    posted_tip_indices: list[int] = field(default_factory=list)
    last_updated: str = ""

    def save(self, path: Path) -> None:
        self.last_updated = datetime.now(timezone.utc).isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "posted_titles": self.posted_titles,
                    "posted_tip_indices": self.posted_tip_indices,
                    "last_updated": self.last_updated,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> PostState:
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            posted_titles=list(data.get("posted_titles") or []),
            posted_tip_indices=list(data.get("posted_tip_indices") or []),
            last_updated=str(data.get("last_updated") or ""),
        )


def resolve_state_path() -> Path:
    raw = os.environ.get("HANATANE_STATE_PATH", "").strip()
    if raw:
        return Path(raw)
    from config.hanatane_settings import DEFAULT_STATE_PATH

    return Path(DEFAULT_STATE_PATH)


def pick_unposted_topic(
    topics: list,
    state: PostState,
    *,
    max_history: int,
) -> object | None:
    posted = set(state.posted_titles)
    for topic in topics:
        if topic.key not in posted:
            return topic
    return topics[0] if topics else None


def mark_topic_posted(state: PostState, title: str, *, max_history: int) -> None:
    key = title.strip()
    if key in state.posted_titles:
        state.posted_titles.remove(key)
    state.posted_titles.insert(0, key)
    del state.posted_titles[max_history:]


def pick_silence_tip_index(tip_count: int, state: PostState) -> int:
    if tip_count <= 0:
        return 0
    posted = set(state.posted_tip_indices)
    for i in range(tip_count):
        if i not in posted:
            return i
    return 0


def mark_tip_posted(state: PostState, index: int, *, max_history: int = 20) -> None:
    if index in state.posted_tip_indices:
        state.posted_tip_indices.remove(index)
    state.posted_tip_indices.insert(0, index)
    del state.posted_tip_indices[max_history:]
