from utils.image import download_images
import time
import os
import time
import logging
import io
import requests
import mimetypes
from datetime import datetime, timezone
from twitter_api.twitter_client import get_clients
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

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

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# ---------------------
# キャンペーン整形
# ---------------------
def format_campaigns(campaigns: list | None) -> str:
    if not campaigns:
        return ""
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
    return "\n".join(texts)

# ---------------------
# 投稿本文作成
# ---------------------
def build_post_text(comment: str, summary: str, point: str, campaigns: list | None, affiliate_url: str) -> str:
    parts = []
    if comment:
        parts.append(comment)
    if summary:
        parts.append(f"概要: {summary}")
    if point:
        parts.append(f"注目ポイント: {point}")

    campaign_text = format_campaigns(campaigns)
    if campaign_text:
        parts.append(campaign_text)

    # affiliate URL は必ず最後に
    if affiliate_url:
        parts.append(affiliate_url)

    return "\n\n".join(parts)

# ---------------------
# DMM動画ページからMP4取得
# ---------------------
def resolve_mp4_url(page_url: str) -> str | None:
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(page_url, headers=headers)
    res.raise_for_status()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(res.text, "html.parser")
    source = soup.find("source")
    return source["src"] if source and source.get("src") else None

# ---------------------
# 動画ダウンロード
# ---------------------
def download_video(mp4_url: str, filename: str) -> str:
    filepath = os.path.join(TEMP_DIR, filename)
    res = requests.get(mp4_url, stream=True)
    res.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in res.iter_content(chunk_size=8192):
            f.write(chunk)
    return filepath

# ---------------------
# ファイル削除
# ---------------------
def cleanup_file(filepath: str):
    try:
        os.remove(filepath)
        logger.info(f"🧹 削除完了: {filepath}")
    except FileNotFoundError:
        pass


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

# ---------------------
# 画像URL → BytesIO
# ---------------------
def fetch_image_buffer_from_url(url: str) -> io.BytesIO:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    buffer = io.BytesIO(response.content)
    buffer.name = "cover.jpg"
    return buffer

# ---------------------
# 動画アップロード（v1.1）
# ---------------------
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
# iframe URL から MP4 URL を取得
# ---------------------
def get_mp4_url_from_iframe(iframe_url: str) -> str:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get(iframe_url)
        time.sleep(5)  # JS のレンダリング待ち

        # iframe に切り替え
        iframe = driver.find_element(By.TAG_NAME, "iframe")
        driver.switch_to.frame(iframe)
        time.sleep(2)  # iframe 内の読み込み待ち

        # <video> を取得
        video_element = driver.find_element(By.TAG_NAME, "video")
        mp4_url = video_element.get_attribute("src")
        return mp4_url
    finally:
        driver.quit()

# ---------------------
# フルスレッド投稿
# ---------------------
def post_full_thread(comment: str, image_urls: list[str], affiliate_url: str,
                     image_large_url: str = "", 
                     point: str = "", summary: str = "", account: str = "1",
                     sample_movie_url: str = "", campaigns: list | None = None):

    logger.info(f"🚀 スレッド投稿開始: アカウント{account}")
    api_v1, client_v2 = get_clients(account)

    # 本文作成
    post_text = build_post_text(comment, summary, point, campaigns, affiliate_url)

    media_ids = []

   # 動画があれば先にアップロード
    if sample_movie_url:
        try:
            # HTMLページURLならMP4を抽出
            if sample_movie_url.endswith(".html") or "litevideo" in sample_movie_url:
                mp4_url = get_mp4_url_from_iframe(sample_movie_url)
                if mp4_url:
                    sample_movie_url = mp4_url
        except Exception as e:
            print(f"[警告] MP4抽出に失敗しました: {e}")
            # エラーが発生しても sample_movie_url は元のまま後続処理に進む


    # 大きいカバー画像があればアップロード
    if image_large_url:
        try:
            cover_buffer = fetch_image_buffer_from_url(image_large_url)
            media_ids.extend(upload_images_v1(api_v1, [cover_buffer]))
        except Exception as e:
            logger.warning(f"⚠ カバー画像アップロード失敗 → {e}")

    # 1枚目投稿（動画＋カバー画像）
    tweet_id = post_tweet_v2(client_v2, post_text, media_ids)
    time.sleep(10)

    # 残り画像アップロード
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

