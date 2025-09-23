import logging
from config.settings import ACCOUNT_SETTINGS
from db.post_repository import get_next_post, mark_post_as_posted
from twitter_api.tweet_service import post_full_thread
import os

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

def main():

    # アカウント設定をループ
    for account_id, config in ACCOUNT_SETTINGS.items():
        if not config["enabled"]:
            logger.info(f"⚠️ {config['screen_name']} は実施フラグOFFのためスキップします")
            continue

        # 投稿ジャンルごとにループ
        for target in config.get("targets", []):
            service = target["service"]
            floor = target["floor"]

            post = get_next_post(service, floor)
            if not post:
                logger.warning(f"⚠ 投稿対象なし: {config['screen_name']} ({service}/{floor})")
                continue

            item_id = post['id']
            content_id = post['content_id']
            floor = post['floor']
            service = post['service']
            image_urls = post['sample_images']
            affiliate_url = post['affiliate_url']
            image_large_url = post["image_large_url"]
            comment = post['auto_comment']
            summary = post['auto_summary']
            point = post['auto_point']
            sample_movie_url = post["sample_movie_url"]  # ★ 追加
            campaigns = post["campaign"] or []
            tachiyomi_url = post["tachiyomi_url"]  # 立ち読みURL

            # キャンペーン情報を本文に追加
            campaign_text = ""
            for c in campaigns:
                title = c.get("title")
                date_begin = c.get("date_begin")
                date_end = c.get("date_end")
                if title and date_begin and date_end:
                    campaign_text += f"\n🎉 {title} ({date_begin[:10]}〜{date_end[:10]})"

            logger.info(f"タイトル: {post['id']}-{post['title']}")
            full_comment = (comment or "") + campaign_text

            # account_id を渡してどのアカウントで投稿するか指定
            result = post_full_thread(
                full_comment, image_urls, affiliate_url,
                image_large_url, point, summary,
                account=account_id,
                sample_movie_url=sample_movie_url,  # ★ 追加引数
                tachiyomi_url=tachiyomi_url,  # ★ 追加引数
                screen_name=config['screen_name'],
                content_id=content_id,
                floor=floor,
            )
            if not result[0]:
                logger.error(f"投稿しません: {config['screen_name']} - {result[1]}")
                continue

            # 投稿成功したらDBの投稿済みにマーク
            mark_post_as_posted(item_id)
            logger.info(f"✅ 投稿完了: {config['screen_name']} - {item_id}")
if __name__ == "__main__":
    main()
