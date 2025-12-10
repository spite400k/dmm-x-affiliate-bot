ACCOUNT_SETTINGS = {
    "1": {
        "enabled": False,
        "site":"dmm",
        "screen_name": "yuki23675786",
        "targets": [
            {"service": "ebook", "floor": "comic"},   
            {"service": "ebook", "floor": "novel"},   
            {"service": "ebook", "floor": "otherbooks"}, 
            # {"service": "ebook", "floor": "photo"},   
        ],	
    },
    "2": {
        "enabled": True,
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
        "screen_name": "Sora36100",
        "targets": [
            # {"service": "doujin", "floor": "digital_doujin"},  # 同人誌
            {"service": "digital", "floor": "videoc"},   # 動画（素人）
            # {"service": "ebook", "floor": "comic"},    # コミック
        ],
    },
    "4": {
        "enabled": False,
        "screen_name": "AdultSelectLab",
        "targets": [],  # 投稿ジャンルなし
    },
    "5": {
        "enabled": False,
        "screen_name": "fanza_portal_1",
        "targets": [
            # {"service": "digital", "floor": "anime"},   # ←コメントアウトしていたものも残せる
            {"service": "digital", "floor": "videoc"},   # 動画（素人）
            {"service": "ebook", "floor": "comic"},    # コミック
        ],  
    },
}
