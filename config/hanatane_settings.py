"""@hanatane_app X 投稿ジョブ用設定。

改善案 docs/hanatane_x_growth_plan.md §3 に基づく。
"""

from __future__ import annotations

# Twitter API 認証: API_KEY_{account} 形式（例: API_KEY_HANATANE）
X_ACCOUNT_ID = "HANATANE"
SCREEN_NAME = "hanatane_app"

DISCOVER_URL = "https://hanatane.onecoin-photo.net/discover"
WEB_URL = "https://hanatane.onecoin-photo.net/discover"

# 投稿済みネタの状態ファイル（GHA では cache で永続化）
DEFAULT_STATE_PATH = "state/hanatane_posted.json"

# 同じタイトルを再投稿しない保持件数
MAX_POSTED_HISTORY = 200

# スレッド返信までの待機秒数
THREAD_WAIT_SECONDS = 15

# 沈黙Tips（旧・沈黙対策 #n 同文の置き換え）
SILENCE_TIPS: list[str] = [
    "コメントを振ったあと、すぐ自分で埋めない。\n\n10秒空けるだけで、返りが来る確率が上がることが多い。",
    "保険ネタは5個いらない。\n\n「二択」と「自分の失敗談」の2個あるだけで、肩の力が抜ける。",
    "お題を出したら、すぐ自分で答えきらない。\n\n「みんななら？」を残すと、コメントの入口になる。",
    "沈黙そのものより、「次の一文がない」のが怖い。\n\n一文あるだけで、配信の呼吸が変わることがある。",
]

# 曜日(JST) → 投稿モード
# news_card: 時事ネタカード(A) / silence_tip: 沈黙Tips(D) / demo: 短尺デモ(C) / skip: 投稿しない
WEEKDAY_MODES: dict[int, str] = {
    0: "news_card",  # 月
    1: "news_card",  # 火
    2: "demo",  # 水（動画未設定時は news_card にフォールバック）
    3: "news_card",  # 木
    4: "silence_tip",  # 金
    5: "skip",  # 土（人間味は手動）
    6: "skip",  # 日
}
