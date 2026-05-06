import os
import tweepy
from dotenv import load_dotenv
# 環境変数から認証情報を取得
load_dotenv()
# ------------------------------
# 1. 認証情報（OAuth1.0a ユーザーコンテキスト）
# ------------------------------
CONSUMER_KEY = os.getenv("CONSUMER_KEY_2")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET_KEY_2")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN_2")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET_2")
if not all([CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
    raise ValueError(f"❌ 認証情報が不足しています,CONSUMER_KEY={CONSUMER_KEY}, CONSUMER_SECRET={CONSUMER_SECRET}, ACCESS_TOKEN={ACCESS_TOKEN}, ACCESS_TOKEN_SECRET={ACCESS_TOKEN_SECRET}")

auth = tweepy.OAuth1UserHandler(
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)
api = tweepy.API(auth)

# ------------------------------
# 2. 動画アップロード
# ------------------------------
VIDEO_PATH = "C:\\Users\\kazuk\\Videos\\tv-off01\\tv-off01.mp4"  # アップロードする動画ファイルのパス

try:
    # ここで動画をアップロードすると media_id が返る
    media = api.media_upload(filename=VIDEO_PATH, chunked=True)
    media_id = media.media_id_string
    print(f"[INFO] 動画アップロード完了 media_id={media_id}")
except Exception as e:
    print(f"[ERROR] 動画アップロード失敗: {e}")
    media_id = None

# ------------------------------
# 3. ツイート作成
# ------------------------------
if media_id:
    try:
        tweet = api.update_status(
            status="テスト用動画投稿です。",
            media_ids=[media_id]
        )
    except tweepy.errors.Forbidden as e:
        print(f"[ERROR] 投稿禁止: {e}")
    except tweepy.errors.TweepyException as e:
        print(f"[ERROR] 投稿失敗: {e}")

