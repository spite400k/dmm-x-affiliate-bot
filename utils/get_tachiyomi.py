import os
import logging
import requests
from supabase import create_client

# ---------------------
# ログ設定
# ---------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ---------------------
# Supabase 設定
# ---------------------
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------
# Supabaseから立ち読み画像を取得（public URL経由）
# ---------------------
def capture_all_tachiyomi_pages_from_supabase(floor: str, content_id: str, bucket_name: str = "dmm-images2") -> list[str]:
    """
    bucket_name: Supabase Storageのバケット名
    floor, content_id: パス指定用
    return: ダウンロードしたローカルパスのリスト
    """
    TEMP_DIR = os.path.join(os.getcwd(), "temp")
    os.makedirs(TEMP_DIR, exist_ok=True)

    try:
        content_path = f"{floor}/{content_id}/"

        # オブジェクトリストを取得
        objects = supabase.storage.from_(bucket_name).list(path=content_path)
        if not objects:
            logging.warning(f"Supabaseに対象画像が存在しません: {content_path}")
            return []

        local_paths = []
        for obj in sorted(objects, key=lambda x: x["name"]):
            obj_name = obj["name"]
            logging.info(f"📥 取得中: {obj_name}")

            # 公開URLを取得
            public_url = supabase.storage.from_(bucket_name).get_public_url(f"{content_path}{obj_name}")
            if not public_url:
                logging.warning(f"⚠ 公開URL取得失敗: {obj_name}")
                continue

            # 公開URLからダウンロード
            resp = requests.get(public_url, stream=True)
            if resp.status_code != 200:
                logging.warning(f"⚠ ダウンロード失敗: {obj_name} ({resp.status_code})")
                continue

            # 保存
            local_path = os.path.join(TEMP_DIR, obj_name)
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            local_paths.append(local_path)
            logging.info(f"✅ 保存完了: {local_path}")

        return local_paths

    except Exception as e:
        logging.error(f"🔥 Supabase立ち読み取得失敗: {e}")
        return []


# ---------------------
# テスト
# ---------------------
if __name__ == "__main__":
    bucket = "dmm-tachiyomi"
    floor = "tachiyomi"
    content_id = "FRNfXRNVFW1RAQxa"
    images = capture_all_tachiyomi_pages_from_supabase(floor, content_id, bucket)
    print(f"取得画像数: {len(images)}")
