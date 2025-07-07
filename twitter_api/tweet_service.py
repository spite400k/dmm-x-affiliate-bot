from twitter.twitter_client import api
from utils.image import download_images
import time

def post_tweet(text: str, image_paths: list[str] = [], reply_to: str = None):
    media_ids = []
    for path in image_paths:
        media = api.media_upload(path)
        media_ids.append(media.media_id_string)

    tweet = api.update_status(
        status=text,
        media_ids=media_ids,
        in_reply_to_status_id=reply_to
    )
    return tweet.id

def post_full_thread(comment: str, image_urls: list[str], affiliate_url: str):
    # 画像をダウンロード
    image_paths = download_images(image_urls)

    # 1回目：コメント＋最初の4枚
    first_images = image_paths[:4]
    tweet_id = post_tweet(comment, first_images)
    time.sleep(10)

    # 2回目以降：残りの画像を4枚ずつスレッドで投稿
    remaining = image_paths[4:]
    for i in range(0, len(remaining), 4):
        tweet_id = post_tweet("", remaining[i:i+4], tweet_id)
        time.sleep(10)

    # 最後にアフィリエイトリンクを投稿
    post_tweet(f"続きを読む👉 {affiliate_url}", reply_to=tweet_id)
