import tweepy
import os
from dotenv import load_dotenv

load_dotenv()

# v2 用クライアント（テキスト投稿など）
client_v2 = tweepy.Client(
    consumer_key=os.getenv("API_KEY"),
    consumer_secret=os.getenv("API_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_SECRET"),
    bearer_token=os.getenv("BEARER_TOKEN")
)

# v1.1 用クライアント（画像アップロード）
auth_v1 = tweepy.OAuth1UserHandler(
    os.getenv("API_KEY"),
    os.getenv("API_SECRET"),
    os.getenv("ACCESS_TOKEN"),
    os.getenv("ACCESS_SECRET")
)
api_v1 = tweepy.API(auth_v1)
