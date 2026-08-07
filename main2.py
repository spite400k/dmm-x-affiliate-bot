# library
import os
from dotenv import load_dotenv
import tweepy

# .env ファイルを読み込む
load_dotenv()
# X Developer Portal: API Key / API Key Secret / Bearer / Access Token (+ Secret)
consumer_key = os.getenv("API_KEY_1") or os.getenv("CONSUMER_KEY_1")
consumer_secret = os.getenv("API_SECRET_KEY_1") or os.getenv("CONSUMER_SECRET_KEY_1")
bearer_token = os.getenv("BEARER_TOKEN_1")
access_token = os.getenv("ACCESS_TOKEN_1")
access_token_secret = os.getenv("ACCESS_TOKEN_SECRET_1")

# Client (テキスト投稿用)
client = tweepy.Client(bearer_token=bearer_token,
                        consumer_key=consumer_key,
                        consumer_secret=consumer_secret,
                        access_token=access_token,
                        access_token_secret=access_token_secret)

# OAuth認証
auth = tweepy.OAuth1UserHandler(consumer_key, consumer_secret, access_token, access_token_secret)
api = tweepy.API(auth)

# 画像をアップロード
media = api.media_upload("010029_01_img.jpg")  # アップロードしたい画像のパスを指定

# 画像付きツイートを投稿（改行を含める）
tweet_text = "2025/03/25 - Hello World\nThis is a multi-line tweet with an image.\n #Python #API #開発はじめ"
client.create_tweet(text=tweet_text, media_ids=[media.media_id])
