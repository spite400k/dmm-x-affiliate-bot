import logging
import random
import time
from config.settings import ACCOUNT_SETTINGS
from db.post_repository import get_next_post, mark_post_as_posted
# from threads_api.threads_service import post_full_thread
from twitter_api.tweet_service import post_full_twitter
import os

# ---------------------
# ログ設定
# ---------------------
os.makedirs("logs", exist_ok=True)  

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/tweet.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ---------------------
# キャンペーン整形関数
# ---------------------
from datetime import datetime, timezone

def format_campaigns(campaigns: list | None) -> str:
    if not campaigns:
        return ""
    now = datetime.now(timezone.utc)
    texts = []
    for c in campaigns:
        title = c.get("title")
        date_end = c.get("date_end")
        try:
            dt_end = datetime.strptime(date_end, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            days_left = (dt_end - now).days
            if days_left < 0:
                status = "終了しました"
            elif days_left == 0:
                status = "今日まで！"
            else:
                status = f"あと{days_left}日！"
        except Exception:
            status = f"{date_end}"
        texts.append(f"🎉 {title} {status}")
    return "\n".join(texts)

# ---------------------
# 投稿本文生成（Twitter用）
# ---------------------
def build_twitter_text(title, comment, summary, point, campaigns, affiliate_url):
    parts = []
    parts.append(title) 
    if comment:
        parts.append(comment)
    # if summary:
    #     parts.append(f"概要: {summary}")
    # if point:
    #     parts.append(f"注目ポイント: {point}")
    campaign_text = format_campaigns(campaigns)
    if campaign_text:
        parts.append(campaign_text)
    # if affiliate_url:
    #     parts.append(affiliate_url)  # Twitterは最後にリンク
    return "\n\n".join(parts)

# ---------------------
# 投稿本文生成（Threads用）
# ---------------------
def build_threads_text(comment, campaigns):
    parts = []
    if comment:
        parts.append(comment)
    campaign_text = format_campaigns(campaigns)
    if campaign_text:
        parts.append(campaign_text)
    return "\n\n".join(parts)

# ---------------------
# メイン処理
# ---------------------
def main():

    # アカウント設定をループ
    for account_id, config in ACCOUNT_SETTINGS.items():
        if not config["enabled"]:
            logger.info(f"⚠️ {config['screen_name']} は実施フラグOFFのためスキップします")
            continue

        site = config["site"]

        targets = config.get("targets", [])

        if targets:
            target = random.choice(targets)  # ← ランダムで1件
            
            service = target["service"]
            floor = target["floor"]

            post = get_next_post(service, floor, account_id)
            if not post:
                logger.warning(f"⚠ 投稿対象なし: {config['screen_name']} ({service}/{floor})")
                continue

            item_id = post['id']
            content_id = post['content_id']
            floor = post['floor']
            service = post['service']
            image_urls = post['sample_images']
            affiliate_url = post['affiliate_url']
            image_large_url = post.get("image_large_url", "")
            comment = post.get('auto_comment', "")
            summary = post.get('auto_summary', "")
            point = post.get('auto_point', "")
            sample_movie_url = post.get("sample_movie_url")
            campaigns = post.get("campaign") or []
            tachiyomi_url = post.get("tachiyomi_url")
            authors = post.get("author", [])
            actresses = post.get("actress", [])

            logger.info(f"タイトル: {post['id']}-{post['title']}")

            # Twitter本文
            twitter_text = build_twitter_text(post['title'],comment, summary, point, campaigns, affiliate_url)
            # Threads本文
            threads_text = build_threads_text(comment, campaigns)

            # -----------------------------
            # Twitter投稿（失敗しても続行）
            # -----------------------------
            try:
                # -----------------------------
                # Twitter投稿
                # -----------------------------
                try:
                    twitter_result = post_full_twitter(
                        comment=twitter_text,
                        title=post['title'],
                        image_urls=image_urls,
                        affiliate_url=affiliate_url,
                        image_large_url=image_large_url,
                        account=account_id,
                        campaigns=campaigns,
                        content_id=content_id,
                        floor=floor,
                        item_id=item_id,
                        service=service,
                        sample_movie_url=sample_movie_url,
                        tachiyomi_url=tachiyomi_url,
                        screen_name=config['screen_name'],
                        site=site,
                        authors=authors,
                        actresses=actresses,
                    )
                    if not twitter_result[0]:
                        logger.warning(f"⚠ Twitter投稿失敗: {config['screen_name']} - {twitter_result[1]}")
                    else:
                        logger.info(f"✅ Twitter投稿完了: {config['screen_name']} - {item_id}")
                except Exception as e:
                    logger.error(f"🚨 Twitter投稿例外: {e}")

                # -----------------------------
                # Threads投稿
                # -----------------------------
                # try:
                #     threads_result = post_full_thread(
                #         comment=threads_text,
                #         image_urls=image_urls,
                #         affiliate_url=affiliate_url,
                #         image_large_url=image_large_url,
                #         account=account_id,
                #         campaigns=campaigns,
                #         content_id=content_id,
                #         floor=floor,
                #         item_id=item_id,
                #         service=service,
                #     )
                #     if not threads_result[0]:
                #         logger.warning(f"⚠ Threads投稿失敗: {config['screen_name']} - {threads_result[1]}")
                #     else:
                #         logger.info(f"✅ Threads投稿完了: {config['screen_name']} - {item_id}")
                # except Exception as e:
                #     logger.error(f"🚨 Threads投稿例外: {e}")

            finally:
                # -----------------------------
                # 失敗しても投稿済み扱いにする
                # -----------------------------
                try:
                    mark_post_as_posted(item_id, account_id)
                    logger.info(f"🏁 投稿済みマーク完了（エラー含む）: {config['screen_name']} - {item_id}")
                except Exception as e:
                    logger.error(f"🚨 投稿済みマーク失敗: {e}")

                # 投稿間隔
                time.sleep(10)

if __name__ == "__main__":
    main()
