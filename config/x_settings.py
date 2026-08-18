"""X（Twitter）投稿ジョブ用のアカウント設定。

main_x.py / main_x-buzz-affiliate.py / main_weekly_ranking.py が参照する。
"""

# schedule スロットでのランダム skip 率（環境変数 POST_SKIP_RATE で上書き可）
DEFAULT_POST_SKIP_RATE = 0.0

# 回復期の投稿モード割合（合計 1.0）
POST_MODE_WEIGHTS = {
    "casual": 0.4,
    "promo_parent": 0.3,
    "promo_reply": 0.3,
}

# promo_reply: 親投稿後のリプ待機秒数
REPLY_WAIT_SECONDS_RANGE = (180, 720)

X_ACCOUNT_SETTINGS = {
    "1": {
        "enabled": False,
        "site": "dmm",
        "screen_name": "yuki23675786",
        "targets": [
            {"service": "ebook", "floor": "comic"},
            {"service": "ebook", "floor": "novel"},
            # {"service": "ebook", "floor": "otherbooks"},
            # {"service": "ebook", "floor": "photo"},
        ],
    },
    "2": {
        "enabled": True,
        "site": "fanza",
        "screen_name": "Ren47291",
        # アカウントごとに floor 固定（複数ある場合は先頭のみ使用）
        "targets": [
            {"service": "digital", "floor": "videoa"},
        ],
    },
    "3": {
        "enabled": False,
        "screen_name": "Sora36100",
        "targets": [
            # {"service": "doujin", "floor": "digital_doujin"},
            {"service": "digital", "floor": "videoc"},
            # {"service": "ebook", "floor": "comic"},
        ],
    },
    "4": {
        "enabled": False,
        "screen_name": "AdultSelectLab",
        "targets": [],
    },
    "5": {
        "enabled": False,
        "screen_name": "fanza_portal_1",
        "targets": [
            # {"service": "digital", "floor": "anime"},
            {"service": "digital", "floor": "videoc"},
            {"service": "ebook", "floor": "comic"},
        ],
    },
}
