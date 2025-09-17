import requests
import tweepy
from utils.get_sample_movie import get_sample_movie
from utils.image import download_images
import time
import os
import time
import logging
import io
from datetime import datetime, timezone
from twitter_api.twitter_client import get_clients
from utils.get_tachiyomi import capture_all_tachiyomi_pages


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
    # if summary:
    #     parts.append(f"概要: {summary}")
    # if point:
    #     parts.append(f"注目ポイント: {point}")

    campaign_text = format_campaigns(campaigns)
    if campaign_text:
        parts.append(campaign_text)

    # affiliate URL は必ず最後に
    # if affiliate_url:
    #     parts.append(affiliate_url) #2025のXだと最初にリンクはないほうがいい

    return "\n\n".join(parts)


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
def upload_images_v1_on_local(api_v1, image_paths: list[str]) -> list[str]:
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
# def post_tweet_v2(client_v2, text: str, media_ids: list[str] = [], reply_to: str = None, max_retries: int = 3, retry_wait: int = 60) -> str:
#     logger.info(f"📤 投稿内容: {text[:60]}{'...' if len(text) > 60 else ''}")

#     for attempt in range(1, max_retries + 1):
#         try:
#             response = client_v2.create_tweet(
#                 text=text,
#                 media_ids=media_ids if media_ids else None,
#                 in_reply_to_tweet_id=reply_to if reply_to else None
#             )
#             tweet_id = response.data["id"]
#             logger.info(f"✅ 投稿成功 → tweet_id: {tweet_id}")
#             return tweet_id

#         except Exception as e:
#             logger.warning(f"⚠️ 投稿失敗（{attempt}回目）→ {e}")
#             if attempt < max_retries:
#                 logger.info(f"⏳ {retry_wait}秒後にリトライ...")
#                 time.sleep(retry_wait)
#             else:
#                 logger.error(f"❌ 最大リトライ回数を超えました → 投稿中止")
#                 raise

# ---------------------
# 投稿処理（v2）+ レート制限対応 + リトライ処理あり
# ---------------------
def safe_post_tweet(client, text, media_ids=None, reply_to: str =None, max_retries=5):
    """
    Twitterに安全に投稿する。レート制限が来たら待機してリトライ。
    """
    for attempt in range(max_retries):
        try:
            response = client.create_tweet(
                text=text,
                media_ids=media_ids if media_ids else None,
                in_reply_to_tweet_id=reply_to if reply_to else None
            )
            logger.info(f"✅ 投稿成功: {response.data}")
            return response

        except tweepy.errors.TooManyRequests as e:
            # レート制限 → ヘッダーから再試行時刻を計算
            reset_time = int(e.response.headers.get("x-rate-limit-reset", time.time() + 60))
            wait_time = max(reset_time - int(time.time()), 60)  # 最低60秒
            logger.warning(f"⚠️ レート制限 → {wait_time}秒待機 (attempt {attempt+1}/{max_retries})")
            time.sleep(wait_time)

        except Exception as e:
            logger.error(f"❌ 投稿失敗 (attempt {attempt+1}/{max_retries}): {e}", exc_info=True)
            time.sleep(10)

    logger.error("❌ 最大リトライ回数を超えました → 投稿中止")
    return None


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
# ファイル削除
# ---------------------
def cleanup_file(filepath: str):
    try:
        os.remove(filepath)
        logger.info(f"🧹 削除完了: {filepath}")
    except FileNotFoundError:
        pass

# ---------------------
# フルスレッド投稿
# ---------------------
def post_full_thread(comment: str, image_urls: list[str], affiliate_url: str,
                     image_large_url: str = "", 
                     point: str = "", summary: str = "", account: str = "1",
                     sample_movie_url: str = "", 
                     tachiyomi_url: str = "", 
                     campaigns: list | None = None,
                     screen_name: str = "",
                     ) -> tuple[bool, str]:

    logger.info(f"🚀 スレッド投稿開始: アカウント{account} {screen_name}")

    api_v1, client_v2 = get_clients(account)
    # logger.info(f"✅ Twitter APIクライアント取得成功")
    # 本文作成
    post_text = build_post_text(comment, summary, point, campaigns, affiliate_url)

    media_ids = []


    if tachiyomi_url:
        # 立ち読み画像があれば取得＆アップロード
        # 立ち読みURLが存在する場合のみ処理
        tachiyomi_image_paths = []
        try:
            logging.info("立ち読みデータ取得 URL=%s", tachiyomi_url)
            # 立ち読みキャプチャ（画像ファイルのリスト）
            tachiyomi_image_paths = capture_all_tachiyomi_pages(tachiyomi_url)
            # PNGファイルだけ対象
            tachiyomi_image_paths = [p for p in tachiyomi_image_paths if p.lower().endswith(".png")]
            if not tachiyomi_image_paths:
                raise Exception("立ち読み画像が取得できません")
            
            media_ids = []

            # 最初の4枚をアップロード
            first_chunk = tachiyomi_image_paths[:4]
            if first_chunk:
                media_ids = upload_images_v1_on_local(api_v1, first_chunk)

            # 1投稿目（最初の4枚）
            tweet_id = safe_post_tweet(client_v2, post_text, media_ids)
            logger.info("DEBUG tweet_id:", tweet_id, type(tweet_id))
            time.sleep(10)

            # 残りの画像を4枚ずつアップロードしてスレッド化
            remaining_paths = tachiyomi_image_paths[4:]

            for i in range(0, len(remaining_paths), 4):
                chunk = remaining_paths[i:i+4]
                chunk_media_ids = upload_images_v1_on_local(api_v1, chunk)

                tweet_id = safe_post_tweet(client_v2, "", chunk_media_ids, reply_to=tweet_id)
                logger.info("DEBUG tweet_id:", tweet_id, type(tweet_id))
                time.sleep(10)

            # logger.info(f"✅ 立ち読みデータ アップロード完了: {tweet_id}")
            logger.info(f"✅ 立ち読みデータ アップロード完了: ")

        except Exception as e:
            logger.error(f"⚠ 立ち読みデータ アップロード失敗 → {e}")
        finally:
            # 一時ファイルのクリーンアップ
            for path in tachiyomi_image_paths:
                cleanup_file(path)

    elif sample_movie_url:
        # サンプル動画があればアップロード
        try:
            logger.info(f"サンプル動画URL → {sample_movie_url}")
            video_path = get_sample_movie(sample_movie_url)
            video_media_id = upload_video_v1(api_v1, video_path)
            if video_media_id:
                media_ids.append(video_media_id)
            time.sleep(10)  # 動画アップロード後に少し待つ
            logger.info(f"✅ サンプル動画アップロード完了: {video_media_id}")
            
            tweet_id = safe_post_tweet(client_v2, post_text, media_ids)
            time.sleep(10)  # ポスト後に少し待つ
        except Exception as e:
            logger.error(f"⚠ サンプル動画アップロード失敗 → {e}")
        finally:
            # 一時ファイルのクリーンアップ
            cleanup_file(video_path)
    else:
        # それ以外の場合、サンプル画像をアップロード
        # 大きいカバー画像があればアップロード
        if image_large_url:
            try:
                cover_buffer = fetch_image_buffer_from_url(image_large_url)
                media_id = upload_images_v1(api_v1, [cover_buffer])
                media_ids.extend(media_id)
            except Exception as e:
                logger.error(f"⚠ カバー画像アップロード失敗 → {e}")

        # 1枚目投稿（動画＋カバー画像）
        tweet_id = safe_post_tweet(client_v2, post_text, media_ids)
        time.sleep(10)

        # 残り画像アップロード
        remaining_buffers = download_images(image_urls)
        for i in range(0, len(remaining_buffers), 4):
            chunk = remaining_buffers[i:i+4]
            # media_ids = upload_images_v1(api_v1, chunk)
            # tweet_id = safe_post_tweet(client_v2, "", media_ids, reply_to=tweet_id)
            time.sleep(10)

    # 最終投稿
    safe_post_tweet(client_v2, f"続きを見る👇 {affiliate_url}", reply_to=tweet_id)

    logger.info(f"🏁 スレッド投稿完了: アカウント{account} {screen_name}")
    return True, "投稿成功"


