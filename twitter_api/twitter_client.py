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


def _env_secret(name: str) -> str | None:
    """環境変数を読み、前後空白・Windows の CRLF 由来の \\r を除去する。"""
    v = os.getenv(name)
    if v is None:
        return None
    return v.strip().strip("\r")


def get_clients(account: str):
    logger.info(f"🔑 Twitter APIクライアントを取得中: アカウント{account}")
    """アカウント名に応じて v1.1 / v2 のクライアントを返す"""

    # X Developer Portal 表記に合わせる: API Key / API Key Secret
    # （旧名 CONSUMER_* は後方互換のためフォールバック）
    load_dotenv()

    consumer_key = _env_secret(f"API_KEY_{account}") or _env_secret(
        f"CONSUMER_KEY_{account}"
    )
    consumer_secret = _env_secret(f"API_SECRET_KEY_{account}") or _env_secret(
        f"CONSUMER_SECRET_KEY_{account}"
    )
    access_token = _env_secret(f"ACCESS_TOKEN_{account}")
    access_token_secret = _env_secret(f"ACCESS_TOKEN_SECRET_{account}")
    bearer_token = _env_secret(f"BEARER_TOKEN_{account}")

    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        raise ValueError(
            f"❌ {account} のTwitter認証情報が不足しています, \
            consumer_key={'set' if consumer_key else None}, \
            consumer_secret={'set' if consumer_secret else None}, \
            access_token={'set' if access_token else None}, \
            access_token_secret={'set' if access_token_secret else None}, \
            bearer_token={'set' if bearer_token else None}"
        )

    # v1.1 (media_upload 用)
    auth = tweepy.OAuth1UserHandler(
        consumer_key, consumer_secret, access_token, access_token_secret
    )
    api_v1 = tweepy.API(auth)

    # logger.info(f"✅ Twitter API v1.1 クライアント取得成功: アカウント{account}")
    # v2（create_tweet は OAuth 1.0a ユーザー文脈。ベアラーは任意）
    client_kw: dict = {
        "consumer_key": consumer_key,
        "consumer_secret": consumer_secret,
        "access_token": access_token,
        "access_token_secret": access_token_secret,
    }
    if bearer_token:
        client_kw["bearer_token"] = bearer_token
    client_v2 = tweepy.Client(**client_kw)
    # logger.info(f"✅ Twitter API v2 クライアント取得成功: アカウント{account}")
    return api_v1, client_v2
