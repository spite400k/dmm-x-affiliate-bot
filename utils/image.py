import os
import requests
import uuid
from PIL import Image
import logging

TEMP_DIR = "data/temp"
os.makedirs(TEMP_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO)

def download_images(urls: list[str]) -> list[str]:
    paths = []
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for url in urls:
        try:
            # 画像ダウンロード
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()

            # 一時保存（仮ファイル名）
            filename = f"{uuid.uuid4().hex}.jpg"
            path = os.path.join(TEMP_DIR, filename)
            with open(path, "wb") as f:
                f.write(r.content)

            # Pillow で形式確認＆再保存
            try:
                with Image.open(path) as img:
                    img_format = img.format.lower()  # e.g. "jpeg", "png"
                    correct_ext = {
                        "jpeg": "jpg",
                        "png": "png",
                        "gif": "gif",
                        "webp": "webp",
                        "bmp": "bmp"
                    }.get(img_format)

                    if not correct_ext:
                        logging.warning(f"❌ 未対応フォーマット: {url} → {img_format}")
                        os.remove(path)
                        continue

                    new_path = os.path.join(TEMP_DIR, f"{uuid.uuid4().hex}.{correct_ext}")
                    img.save(new_path)
                    os.remove(path)
                    logging.info(f"✅ 画像保存成功: {new_path}")
                    paths.append(new_path)
            except Exception as e:
                logging.error(f"❌ Pillowでの画像確認に失敗: {url} → {e}")
                os.remove(path)

        except Exception as e:
            logging.error(f"❌ 画像取得失敗: {url} → {e}")
    return paths
