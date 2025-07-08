import os
import requests
import uuid
import logging

# ---------------------
# ヘッダー設定
# ---------------------
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
}

TEMP_DIR = os.path.join("data", "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

def download_images(urls: list[str]) -> list[str]:
    paths = []
    for url in urls:
        try:
            r = requests.get(url, headers=headers,timeout=10)
            r.raise_for_status()  # 4xx/5xx を例外に

            # 仮のファイル名
            filename = f"{uuid.uuid4().hex}.jpg"
            path = os.path.join(TEMP_DIR, filename)

            with open(path, "wb") as f:
                f.write(r.content)


            # 拡張子が間違っていたら修正
            correct_path = os.path.join(TEMP_DIR, f"{uuid.uuid4().hex}.{img_type}")
            os.rename(path, correct_path)
            logging.info(f"✅ 画像保存成功: {correct_path}")
            paths.append(correct_path)

        except Exception as e:
            logging.error(f"❌ 画像取得失敗: {url} → {e}")
    return paths
