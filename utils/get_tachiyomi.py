import os
import logging
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
# Supabaseから立ち読み画像を取得
# ---------------------
def capture_all_tachiyomi_pages_from_supabase(floor : str, content_id: str, bucket_name: str = "dmm-images2") -> list[str]:
    """
    bucket_name: Supabase Storageのバケット名
    object_prefix: 画像のパスの共通プレフィックス（例: 'tachiyomi/FRNfXRNVFW1RAQxa/'）
    """
    TEMP_DIR = os.path.join(os.getcwd(), "temp")
    os.makedirs(TEMP_DIR, exist_ok=True)

    try:
        content_path= f"{floor}/{content_id}/"
        # オブジェクトリストを取得
        objects = supabase.storage.from_(bucket_name).list(path=content_path)
        if not objects:
            logging.warning(f"Supabaseに対象画像が存在しません: {content_path}")
            return []

        # 画像URLを順番にダウンロード
        local_paths = []
        for obj in sorted(objects, key=lambda x: x["name"]):
            obj_name = obj["name"]
            logging.info(f"📥 取得中: {obj_name}")
            data = supabase.storage.from_(bucket_name).get_public_url(f"{content_path}{obj_name}")
            if not data:
                logging.warning(f"⚠ ダウンロード失敗: {obj_name}")
                continue
            local_path = os.path.join(TEMP_DIR, obj_name)
            with open(local_path, "wb") as f:
                f.write(data)
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
    prefix = "tachiyomi/FRNfXRNVFW1RAQxa/"
    images = capture_all_tachiyomi_pages_from_supabase(bucket, prefix)
    print(f"取得画像数: {len(images)}")
