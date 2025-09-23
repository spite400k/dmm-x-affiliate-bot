from supabase import create_client
import os
import logging

# ---------------------
# ログ設定
# ---------------------
# ログ用ディレクトリを作成（存在しなければ）
os.makedirs("logs", exist_ok=True)  

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("tweet.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ---------------------
# Supabase 設定
# ---------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------
# Supabase から動画を取得
# ---------------------
def get_video_from_supabase(floor:str , content_id: str, bucket_name: str = "dmm-images2") -> str:
    """
    bucket_name: Supabase Storage のバケット名
    object_path: バケット内の動画ファイルパス
    return: ローカルに保存した動画パス
    """

    try:

        content_path= f"{floor}/{content_id}/{content_id}_01.mp4"
        
        logger.info(f"Supabase から動画取得 → {bucket_name}/{content_path}")

        data = supabase.storage.from_(bucket_name).get_public_url(content_path)
        if not data:
            raise ValueError("Supabaseから動画を取得できません")

        # 保存先
        TEMP_DIR = os.path.join(os.getcwd(), "temp")
        os.makedirs(TEMP_DIR, exist_ok=True)
        filename = os.path.basename(content_id)
        local_path = os.path.join(TEMP_DIR, filename)

        with open(local_path, "wb") as f:
            f.write(data)

        logger.info(f"✅ 動画をローカル保存 → {local_path}")
        return local_path

    except Exception as e:
        logger.error(f"🔥 Supabase動画取得失敗 → {e}")
        return ""
