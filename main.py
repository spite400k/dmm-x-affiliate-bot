import logging
from db.post_repository import get_next_post, mark_post_as_posted
from twitter_api.tweet_service import post_full_thread
import os

# ---------------------
# ログ設定
# ---------------------
# ログ用ディレクトリを作成（存在しなければ）
os.makedirs("logs", exist_ok=True)  

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("tweet.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    # アカウントごとにジャンルを設定
    account_targets = [
        {"account": "3", "service": "doujin", "floor": "digital_doujin"},  # 同人誌
        # {"account": "2", "service": "digital", "floor": "anime"},          # アニメ
        {"account": "2", "service": "digital", "floor": "videoc"},         # 動画（素人）
    ]

    for target in account_targets:
        account = target["account"]
        service = target["service"]
        floor = target["floor"]

        post = get_next_post(service, floor)
        if not post:
            print(f"⚠ 投稿対象なし: {account} ({service}/{floor})")
            continue

        item_id = post['id']
        image_urls = post['sample_images']
        affiliate_url = post['affiliate_url']
        image_large_url = post["image_large_url"]
        comment = post['auto_comment']
        summary = post['auto_summary']
        point = post['auto_point']
        sample_movie_url = post.get("sample_movie_url")  # ★ 追加
        campaigns = post.get("campaign", [])

        # キャンペーン情報を本文に追加
        campaigns = post.get("campaign") or []  # None の場合は空リストにする

        # キャンペーン情報を本文に追加
        campaign_text = ""
        for c in campaigns:
            title = c.get("title")
            date_begin = c.get("date_begin")
            date_end = c.get("date_end")
            if title and date_begin and date_end:
                campaign_text += f"\n🎉 {title} ({date_begin[:10]}〜{date_end[:10]})"

        full_comment = (comment or "") + campaign_text

        # account を渡してどのアカウントで投稿するか指定
        post_full_thread(
            full_comment, image_urls, affiliate_url,
            image_large_url, point, summary,
            account=account,
            sample_movie_url=sample_movie_url  # ★ 追加引数
        )

        mark_post_as_posted(item_id)
        logger.info(f"✅ 投稿完了: {account} - {item_id}")


if __name__ == "__main__":
    main()
