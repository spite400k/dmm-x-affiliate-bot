import os

# 互換用（main_livedoor_atompub は mst_blog_accounts の blog_id から livedoor:{blog_id} を使う）
LIVEDOOR_BLOG_POST_KEY = (
    os.environ.get("LIVEDOOR_BLOG_POST_KEY", "livedoor:写真集のおすすめ").strip()
    or "livedoor:写真集のおすすめ"
)

ACCOUNT_SETTINGS = {
    "1": {
        "enabled": False,
        "enabled_blog": True,
        "site":"dmm",
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
        "enabled_blog": False,
        "site":"fanza",
        "screen_name": "Ren47291",
        "targets": [
            # {"service": "digital", "floor": "anime"},   # ←コメントアウトしていたものも残せる
            {"service": "digital", "floor": "videoa"},   # 動画（AV）
            {"service": "digital", "floor": "videoc"},   # 動画（素人）
            {"service": "ebook", "floor": "comic"},    # コミック
            {"service": "doujin", "floor": "digital_doujin"},    # コミック
        ],	
    },
    "3": {
        "enabled": False,
        "enabled_blog": False,
        "screen_name": "Sora36100",
        "targets": [
            # {"service": "doujin", "floor": "digital_doujin"},  # 同人誌
            {"service": "digital", "floor": "videoc"},   # 動画（素人）
            # {"service": "ebook", "floor": "comic"},    # コミック
        ],
    },
    "4": {
        "enabled": False,
        "enabled_blog": False,
        "screen_name": "AdultSelectLab",
        "targets": [],  # 投稿ジャンルなし
    },
    "5": {
        "enabled": False,
        "enabled_blog": False,
        "screen_name": "fanza_portal_1",
        "targets": [
            # {"service": "digital", "floor": "anime"},   # ←コメントアウトしていたものも残せる
            {"service": "digital", "floor": "videoc"},   # 動画（素人）
            {"service": "ebook", "floor": "comic"},    # コミック
        ],  
    },
}
