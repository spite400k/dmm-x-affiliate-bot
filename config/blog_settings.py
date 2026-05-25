"""ブログ投稿ジョブ用のアカウント設定。

main_livedoor_atompub.py / main_fc2_blog.py / main_seesaa_blog.py が参照する。
ライブドアの portal リンク用に site（dmm / fanza）を持つ。
"""

import os

# 互換用（main_livedoor_atompub は mst_blog_accounts の blog_id から livedoor:{blog_id} を使う）
LIVEDOOR_BLOG_POST_KEY = (
    os.environ.get("LIVEDOOR_BLOG_POST_KEY", "livedoor:写真集のおすすめ").strip()
    or "livedoor:写真集のおすすめ"
)

BLOG_ACCOUNT_SETTINGS = {
    "1": {
        "enabled": True,
        "site": "dmm",
        "screen_name": "yuki23675786",
        "targets": [
            {"service": "ebook", "floor": "comic"},
            # {"service": "ebook", "floor": "novel"},
            # {"service": "ebook", "floor": "otherbooks"},
            {"service": "ebook", "floor": "photo"},
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
        "site": "fanza",
        "screen_name": "Sora36100",
        "targets": [
            # {"service": "doujin", "floor": "digital_doujin"},
            {"service": "digital", "floor": "videoc"},
            # {"service": "ebook", "floor": "comic"},
        ],
    },
    "4": {
        "enabled": False,
        "site": "fanza",
        "screen_name": "AdultSelectLab",
        "targets": [],
    },
    "5": {
        "enabled": False,
        "site": "fanza",
        "screen_name": "fanza_portal_1",
        "targets": [
            # {"service": "digital", "floor": "anime"},
            {"service": "digital", "floor": "videoc"},
            {"service": "ebook", "floor": "comic"},
        ],
    },
    "6": {
        "enabled": True,
        "site": "fanza",
        "screen_name": "Kai4708",
        "targets": [
            {"service": "doujin", "floor": "digital_doujin"},
            {"service": "ebook", "floor": "comic"},
        ],
    },
}
