"""X（Twitter）投稿ジョブ用のアカウント設定。

main_x.py / main_x-buzz-affiliate.py / main_weekly_ranking.py が参照する。
"""

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
        "targets": [
            # {"service": "digital", "floor": "anime"},
            {"service": "digital", "floor": "videoa"},
            {"service": "digital", "floor": "videoc"},
            {"service": "ebook", "floor": "comic"},
            {"service": "doujin", "floor": "digital_doujin"},
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
