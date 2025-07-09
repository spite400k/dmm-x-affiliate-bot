from db.post_repository import get_next_post, mark_post_as_posted
from twitter_api.tweet_service import post_full_thread, test_post_text_only, test_post_v2_with_image
import os

# ログ用ディレクトリを作成（存在しなければ）
os.makedirs("logs", exist_ok=True)  


def main():
    post = get_next_post()
    if not post:
        print("投稿対象がありません。")
        return

    item_id = post['id']
    image_urls = post['sample_images']
    affiliate_url = post['affiliate_url']
    comment = post['auto_comment']  # カラム名が comment ならそのままでOK
    summary = post['auto_summary']  # カラム名が comment ならそのままでOK
    point = post['auto_point']  # カラム名が comment ならそのままでOK

    post_full_thread(comment, image_urls, affiliate_url, point, summary)

    mark_post_as_posted(item_id)
    print(f"✅ 投稿完了：{item_id}")

if __name__ == "__main__":
    main()