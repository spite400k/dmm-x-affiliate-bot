import tweepy
import os

def get_clients(account: str):
    """アカウント名に応じて v1.1 / v2 のクライアントを返す"""

    api_key = os.getenv(f"API_KEY_{account}")
    api_secret = os.getenv(f"API_SECRET_KEY_{account}")
    access_token = os.getenv(f"ACCESS_TOKEN_{account}")
    access_secret = os.getenv(f"ACCESS_TOKEN_SECRET_{account}")
    bearer_token = os.getenv(f"BEARER_TOKEN_{account}")

    if not all([api_key, api_secret, access_token, access_secret, bearer_token]):
        raise ValueError(f"❌ {account} のTwitter認証情報が不足しています")

    # v1.1 (media_upload 用)
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api_v1 = tweepy.API(auth)

    # v2 (投稿用)
    client_v2 = tweepy.Client(
        bearer_token=bearer_token,
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )

    return api_v1, client_v2
