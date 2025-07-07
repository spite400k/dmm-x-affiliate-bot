from twitter_api.twitter_client import api_v1, client_v2
from utils.image import download_images
import time

def upload_images_v1(image_paths: list[str]) -> list[str]:
    media_ids = []
    for path in image_paths:
        media = api_v1.media_upload("010029_01_img.jpg")
        media_ids.append(media.media_id_string)
    return media_ids

def post_tweet_v2(text: str, media_ids: list[str] = [], reply_to: str = None) -> str:
    response = client_v2.create_tweet(
        text=text,
        media={"media_ids": media_ids} if media_ids else None,
        reply={"in_reply_to_tweet_id": reply_to} if reply_to else None
    )
    return response.data["id"]

def post_full_thread(comment: str, image_urls: list[str], affiliate_url: str):
    image_paths = download_images(image_urls)
    first_images = image_paths[:4]
    media_ids = upload_images_v1(first_images)
    tweet_id = post_tweet_v2(comment, media_ids)
    time.sleep(10)

    remaining = image_paths[4:]
    for i in range(0, len(remaining), 4):
        chunk = remaining[i:i+4]
        media_ids = upload_images_v1(chunk)
        tweet_id = post_tweet_v2("", media_ids, reply_to=tweet_id)
        time.sleep(10)

    post_tweet_v2(f"続きを読む👉 {affiliate_url}", reply_to=tweet_id)

def test_post_v2_with_image():
    text = "✅テスト投稿：v2 API + 画像アップロード（v1.1）"
    image_urls = ["https://placekitten.com/800/600"]  # テスト用猫画像

    from utils.image import download_images
    image_paths = download_images(image_urls)

    media_ids = upload_images_v1(image_paths)
    tweet_id = post_tweet_v2(text, media_ids)

    print(f"✅ 投稿成功: https://twitter.com/user/status/{tweet_id}")

def test_post_text_only():
    from twitter_api.twitter_client import client_v2
    response = client_v2.create_tweet(text="✅ テキストのみのv2投稿テストです")
    print("投稿成功:", response.data["id"])