from twitter_api.twitter_client import api_v1, client_v2
from utils.image import download_images
import time
import os
import time
import logging

# ---------------------
# ログ設定
# ---------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("tweet.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ---------------------
# メディアアップロード（v1.1）
# ---------------------
def upload_images_v1(image_paths: list[str]) -> list[str]:
    media_ids = []
    for path in image_paths:
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            logger.error(f"❌ 画像ファイルが存在しません: {abs_path}")
            continue
        try:
            media = api_v1.media_upload(abs_path)
            media_ids.append(media.media_id_string)
            logger.info(f"✅ アップロード成功: {abs_path}")
        except Exception as e:
            logger.exception(f"❌ アップロード失敗: {abs_path} → {e}")
    return media_ids

# ---------------------
# 投稿処理（v2）
# ---------------------
def post_tweet_v2(text: str, media_ids: list[str] = [], reply_to: str = None) -> str:
    logger.info(f"📤 投稿内容: {text[:60]}{'...' if len(text) > 60 else ''}")
    try:
        response = client_v2.create_tweet(
            text=text,
            media_ids={"media_ids": media_ids} if media_ids else None,
            reply_settings={"in_reply_to_tweet_id": reply_to} if reply_to else None
        )
        tweet_id = response.data["id"]
        logger.info(f"✅ 投稿成功 → tweet_id: {tweet_id}")
        return tweet_id
    except Exception as e:
        logger.exception(f"❌ 投稿失敗 → {e}")
        raise

# ---------------------
# フルスレッド投稿
# ---------------------
def post_full_thread(comment: str, image_urls: list[str], affiliate_url: str):
    logger.info("🚀 スレッド投稿開始")
    image_paths = download_images(image_urls)
    first_images = image_paths[:4]
    media_ids = upload_images_v1(first_images)
    tweet_id = post_tweet_v2(comment, media_ids)
    time.sleep(10)

    remaining = image_paths[4:]
    for i in range(0, len(remaining), 4):
        chunk = remaining[i:i+4]
        media_ids = upload_images_v1(chunk)
        tweet_id = post_tweet_v2("", media_ids, reply_to=tweet_id)
        time.sleep(10)

    post_tweet_v2(f"続きを読む👉 {affiliate_url}", reply_to=tweet_id)
    logger.info("🏁 スレッド投稿完了")

# ---------------------
# テスト関数
# ---------------------
def test_post_v2_with_image():
    text = "✅テスト投稿：v2 API + 画像アップロード（v1.1）"
    image_urls = ["https://placekitten.com/800/600"]  # テスト画像

    image_paths = download_images(image_urls)
    media_ids = upload_images_v1(image_paths)
    tweet_id = post_tweet_v2(text, media_ids)

    logger.info(f"✅ 投稿成功: https://twitter.com/user/status/{tweet_id}")

def test_post_text_only():
    text = "✅ テキストのみのv2投稿テストです"
    try:
        response = client_v2.create_tweet(text=text)
        tweet_id = response.data["id"]
        logger.info(f"✅ テキスト投稿成功: https://twitter.com/user/status/{tweet_id}")
    except Exception as e:
        logger.exception(f"❌ テキスト投稿失敗 → {e}")
