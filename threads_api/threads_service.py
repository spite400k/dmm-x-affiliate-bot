# tweet_service.py (Threads専用版)
import os
import logging
import requests
from twitter_api.twitter_client import get_clients
from utils.get_tachiyomi import capture_all_tachiyomi_pages_from_supabase
from utils.image import download_images
from datetime import datetime, timezone

# --------------------- ログ設定 ---------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/tweet.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --------------------- Threads Client ---------------------
class ThreadsClient:
    """Threads Graph API投稿用クライアント"""
    def __init__(self, access_token: str, user_id: str):
        self.access_token = access_token
        self.user_id = user_id
        self.base_url = f"https://graph.threads.net/v1.0/{user_id}/threads"

    def post_thread(self, text: str, image_url: str = None):
        payload = {"text": text}
        if image_url:
            payload["image_url"] = image_url
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        response = requests.post(self.base_url, json=payload, headers=headers)
        if response.status_code == 200:
            logger.info(f"✅ Threads投稿成功: {response.json()}")
            return response.json()
        else:
            logger.warning(f"⚠ Threads投稿失敗: {response.status_code} {response.text}")
            return None

# --------------------- 投稿本文作成 ---------------------
def build_post_text(comment: str, summary: str = "", point: str = "", campaigns: list | None = None, affiliate_url: str = "") -> str:
    parts = []
    if comment:
        parts.append(comment)

    if campaigns:
        now = datetime.now(timezone.utc)
        texts = []
        for c in campaigns:
            title = c.get("title")
            date_end = c.get("date_end")
            try:
                dt_end = datetime.strptime(date_end, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                days_left = (dt_end - now).days
                if days_left < 0:
                    status = "終了しました"
                elif days_left == 0:
                    status = "今日まで！"
                else:
                    status = f"あと{days_left}日！"
            except Exception:
                status = f"{date_end}"
            texts.append(f"🎉 {title} {status}")
        parts.append("\n".join(texts))

    return "\n\n".join(parts)

# --------------------- Threads投稿関数 ---------------------
def post_full_thread(
    comment: str,
    image_urls: list[str],
    affiliate_url: str,
    image_large_url: str = "",
    account: str = "1",
    campaigns: list | None = None,
    content_id: str = "",
    floor: str = "",
    item_id: str = "",
) -> tuple[bool, str]:

    logger.info(f"🚀 Threads投稿開始: アカウント{account}")
    _, _, threads_client = get_clients(account)

    if not threads_client:
        logger.warning("⚠ Threadsクライアント未設定のため投稿をスキップ")
        return False, "Threadsクライアント未設定"

    try:
        post_text = build_post_text(comment, campaigns=campaigns, affiliate_url=affiliate_url)

        # 画像は優先的に大きい方を使う
        first_image = image_large_url if image_large_url else (image_urls[0] if image_urls else None)
        threads_client.post_thread(text=post_text, image_url=first_image)

        logger.info("🏁 Threads投稿完了")
        return True, "投稿成功"

    except Exception as e:
        logger.error(f"🚨 Threads投稿中にエラー: {e}")
        return False, str(e)
