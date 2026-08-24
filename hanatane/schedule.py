"""曜日ベースの投稿モード決定。"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from config.hanatane_settings import WEEKDAY_MODES

JST = ZoneInfo("Asia/Tokyo")


def resolve_mode_for_today(*, now: datetime | None = None) -> str:
    """JST 曜日から投稿モードを返す。HANATANE_FORCE_MODE で上書き可。"""
    forced = os.environ.get("HANATANE_FORCE_MODE", "").strip()
    if forced:
        return forced

    dt = now or datetime.now(JST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    else:
        dt = dt.astimezone(JST)

    return WEEKDAY_MODES.get(dt.weekday(), "skip")
