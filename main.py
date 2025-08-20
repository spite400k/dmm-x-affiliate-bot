from db.post_repository import get_next_post, mark_post_as_posted
from twitter_api.tweet_service import post_full_thread, test_post_text_only, test_post_v2_with_image
import os

# ログ用ディレクトリを作成（存在しなければ）
os.makedirs("logs", exist_ok=True)  


def main():
    targets = [
        {"service": "doujin", "floor": "digital_doujin"}, # 同人誌
        # {"service": "digital", "floor": "videoc"}, # 動画 素人
        # {"service": "digital", "floor": "nikkatsu"}, # 写真
        # {"service": "digital", "floor": "videoa"}, # ビデオ
        # {"service": "digital", "floor": "anime"}, # アニメ
    ]

    post = get_next_post(targets[0]['service'], targets[0]['floor'])
    if not post:
        print("投稿対象がありません。")
        return

    item_id = post['id']
    image_urls = post['sample_images']
    affiliate_url = post['affiliate_url']
    image_large_url = post["image_large_url"]
    comment = post['auto_comment']  # カラム名が comment ならそのままでOK
    summary = post['auto_summary']  # カラム名が comment ならそのままでOK
    point = post['auto_point']  # カラム名が comment ならそのままでOK

    post_full_thread(comment, image_urls, affiliate_url, image_large_url, point, summary)

    mark_post_as_posted(item_id)
    print(f"✅ 投稿完了：{item_id}")

if __name__ == "__main__":
    main()