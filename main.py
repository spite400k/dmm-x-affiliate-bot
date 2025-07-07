from db.post_repository import get_next_post, mark_post_as_posted
from twitter_api.tweet_service import post_full_thread, test_post_text_only

def test():
    test_post_text_only()

def main():
    post = get_next_post()
    if not post:
        print("投稿対象がありません。")
        return

    post_id = post['id']
    comment = post['comment']
    image_urls = post['image_urls']
    affiliate_url = post['affiliate_url']

    post_full_thread(comment, image_urls, affiliate_url)

    mark_post_as_posted(post_id)
    print(f"投稿完了：{post_id}")

if __name__ == "__main__":
    # main()
    test_post_text_only()
