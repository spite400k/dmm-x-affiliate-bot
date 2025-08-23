from utils.image import download_images
import time
import os
import time
import logging
import io
import requests
from twitter_api.twitter_client import get_clients

# ---------------------
# ログ設定
# ---------------------
# ログ用ディレクトリを作成（存在しなければ）
os.makedirs("logs", exist_ok=True)  

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
def upload_images_v1(api_v1, image_buffers: list[io.BytesIO]) -> list[str]:
    media_ids = []
    for buf in image_buffers:
        try:
            media = api_v1.media_upload(filename=buf.name, file=buf)
            media_ids.append(media.media_id_string)
            logger.info(f"✅ アップロード成功: {buf.name}")
        except Exception as e:
            logger.error(f"❌ アップロード失敗: {buf.name} → {e}")
    return media_ids



# ---------------------
# メディアアップロード（v1.1）ローカルダウンロード版
# ---------------------
def upload_images_v1_on_local(image_paths: list[str]) -> list[str]:
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
# 投稿処理（v2）+ リトライ処理あり
def post_tweet_v2(client_v2, text: str, media_ids: list[str] = [], reply_to: str = None, max_retries: int = 3, retry_wait: int = 10) -> str:
    logger.info(f"📤 投稿内容: {text[:60]}{'...' if len(text) > 60 else ''}")

    for attempt in range(1, max_retries + 1):
        try:
            response = client_v2.create_tweet(
                text=text,
                media_ids=media_ids if media_ids else None,
                in_reply_to_tweet_id=reply_to if reply_to else None
            )
            tweet_id = response.data["id"]
            logger.info(f"✅ 投稿成功 → tweet_id: {tweet_id}")
            return tweet_id

        except Exception as e:
            logger.warning(f"⚠️ 投稿失敗（{attempt}回目）→ {e}")
            if attempt < max_retries:
                logger.info(f"⏳ {retry_wait}秒後にリトライ...")
                time.sleep(retry_wait)
            else:
                logger.error(f"❌ 最大リトライ回数を超えました → 投稿中止")
                raise

def fetch_image_buffer_from_url(url: str) -> io.BytesIO:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    buffer = io.BytesIO(response.content)
    buffer.name = "cover.jpg"
    return buffer

def upload_video_v1(api_v1, video_path: str) -> str:
    """動画をアップロードして media_id を返す"""
    abs_path = os.path.abspath(video_path)
    if not os.path.exists(abs_path):
        logger.error(f"❌ 動画ファイルが存在しません: {abs_path}")
        return ""
    try:
        media = api_v1.media_upload(abs_path, media_category='tweet_video')
        logger.info(f"✅ 動画アップロード成功: {abs_path}")
        return media.media_id_string
    except Exception as e:
        logger.exception(f"❌ 動画アップロード失敗: {abs_path} → {e}")
        return ""

# ---------------------
# フルスレッド投稿
# ---------------------
def post_full_thread(comment: str, image_urls: list[str], affiliate_url: str,
                     image_large_url: str = "", 
                     point: str = "", summary: str = "", account: str = "1",
                     sample_movie_url: str = ""):

    logger.info(f"🚀 スレッド投稿開始: アカウント{account}")
    api_v1, client_v2 = get_clients(account)

    # 動画があれば先にアップロード
    if sample_movie_url:
        video_buffers = download_images([sample_movie_url])
        if video_buffers:
            video_path = os.path.join("temp", video_buffers[0].name)
            video_media_id = upload_video_v1(api_v1, video_path)
            if video_media_id:
                media_ids.append(video_media_id)

    # 1枚目画像
    media_ids = []
    if image_large_url:
        cover_buffer = fetch_image_buffer_from_url(image_large_url)
        media_ids.extend(upload_images_v1(api_v1, [cover_buffer]))



    # 1枚目投稿（画像＋動画）
    tweet_id = post_tweet_v2(client_v2, comment, media_ids)
    time.sleep(10)

    # 2枚目以降の画像
    remaining_buffers = download_images(image_urls)
    for i in range(0, len(remaining_buffers), 4):
        chunk = remaining_buffers[i:i+4]
        media_ids = upload_images_v1(api_v1, chunk)
        tweet_id = post_tweet_v2(client_v2, "", media_ids, reply_to=tweet_id)
        time.sleep(10)

    # 最終投稿
    post_tweet_v2(client_v2, f"続きを見る👇 {affiliate_url}", reply_to=tweet_id)

    logger.info(f"🏁 スレッド投稿完了: アカウント{account}")



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
