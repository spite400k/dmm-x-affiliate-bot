import tweepy
import os
from dotenv import load_dotenv

load_dotenv()
consumer_key=os.getenv("API_KEY")
consumer_secret=os.getenv("API_SECRET_KEY")
access_token=os.getenv("ACCESS_TOKEN")
access_token_secret=os.getenv("ACCESS_TOKEN_SECRET")
bearer_token=os.getenv("BEARER_TOKEN")

# v2 用クライアント（テキスト投稿など）
client_v2 = tweepy.Client(
    bearer_token=bearer_token,
    consumer_key=consumer_key,
    consumer_secret=consumer_secret,
    access_token=access_token,
    access_token_secret=access_token_secret
)

# v1.1 用クライアント（画像アップロード）
auth_v1 = tweepy.OAuth1UserHandler(
    consumer_key,
    consumer_secret,
    access_token,
    access_token_secret,
)
api_v1 = tweepy.API(auth_v1)
