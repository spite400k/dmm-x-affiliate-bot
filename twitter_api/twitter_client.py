import logging
import tweepy
import os
from dotenv import load_dotenv

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



def get_clients(account: str):
    logger.info(f"🔑 Twitter APIクライアントを取得中: アカウント{account}")
    """アカウント名に応じて v1.1 / v2 のクライアントを返す"""

    # 環境変数から認証情報を取得
    load_dotenv()
    
    api_key = os.getenv(f"API_KEY_{account}")
    api_secret = os.getenv(f"API_SECRET_KEY_{account}")
    access_token = os.getenv(f"ACCESS_TOKEN_{account}")
    access_secret = os.getenv(f"ACCESS_TOKEN_SECRET_{account}")
    bearer_token = os.getenv(f"BEARER_TOKEN_{account}")

    if not all([api_key, api_secret, access_token, access_secret, bearer_token]):
        raise ValueError(
            f"❌ {account} のTwitter認証情報が不足しています, \
            api_key={api_key}, \
            api_secret={api_secret}, \
            access_token={access_token}, \
            access_secret={access_secret}, \
            bearer_token={bearer_token}")

    # v1.1 (media_upload 用)
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api_v1 = tweepy.API(auth)

    # logger.info(f"✅ Twitter API v1.1 クライアント取得成功: アカウント{account}")
    # v2 (投稿用)
    client_v2 = tweepy.Client(
        bearer_token=bearer_token,
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )
    # logger.info(f"✅ Twitter API v2 クライアント取得成功: アカウント{account}")
    return api_v1, client_v2
