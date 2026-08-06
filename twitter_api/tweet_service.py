# tweet_service.py
import json
import os
import logging
import io
import time
import random
import requests
from twitter_api.safe_post import safe_post_tweet
from twitter_api.twitter_client import get_clients
from datetime import datetime, timezone
from config.x_settings import REPLY_WAIT_SECONDS_RANGE


# ---------------------
# ログ設定
# ---------------------
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


# ---------------------
# キャンペーン整形
# ---------------------
def campaign_deadline_label(date_end: object) -> str:
    """キャンペーン終了日時の表示ラベル（プレーンテキスト）。"""
    if not date_end:
        return ""
    try:
        dt_end = datetime.strptime(str(date_end), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        days_left = (dt_end - datetime.now(timezone.utc)).days
        if days_left < 0:
            return "終了しました"
        if days_left == 0:
            return "今日まで！"
        return f"あと{days_left}日！"
    except Exception:
        return str(date_end)


def format_campaigns(campaigns: list | None) -> str:
    if not campaigns:
        return ""
    texts = []
    for c in campaigns:
        title = c.get("title")
        status = campaign_deadline_label(c.get("date_end"))
        texts.append(f"🎉 {title} {status}".strip())
    return "\n".join(texts)


# ---------------------
# 投稿本文作成
# ---------------------
def build_post_text(comment: str, summary: str, point: str, campaigns: list | None, affiliate_url: str) -> str:
    parts = []
    if comment:
        parts.append(comment)
    if summary:
        parts.append(f"概要: {summary}")
    if point:
        parts.append(f"注目ポイント: {point}")

    campaign_text = format_campaigns(campaigns)
    if campaign_text:
        parts.append(campaign_text)

    return "\n\n".join(parts)


def build_portal_url(
    site: str,
    content_id: str,
    floor: str = "",
    service: str = "",
) -> str:
    if site == "dmm":
        return f"https://dmmportal.jp/{service}/{floor}/{content_id}"
    return f"https://fanzaportal.com/{floor}/{content_id}"


def pick_hashtag_block(
    site: str,
    actresses: list | None = None,
    authors: list | None = None,
    *,
    rng: random.Random | None = None,
) -> str:
    """定型ハッシュタグの連投を避けるため、バリエーションから抽選。"""
    r = rng or random
    if site == "dmm":
        names = normalize(authors)
        selected = r.sample(names, k=min(2, len(names))) if names else []
        author_tags = " ".join(f"#{n}" for n in selected)
        choices = [
            "",
            "#マンガ",
            author_tags,
            f"#マンガ {author_tags}".strip(),
        ]
    else:
        names = normalize(actresses)
        selected = r.sample(names, k=min(1, len(names))) if names else []
        actress_tags = " ".join(f"#{n}" for n in selected)
        choices = [
            "",
            "#FANZA",
            actress_tags,
            f"#FANZA {actress_tags}".strip(),
            "#FANZA #無料",
        ]
    block = r.choice(choices).strip()
    return block


_CTA_PARENT = [
    "気になった人はこちら【PR】",
    "詳細はこちら【PR】",
    "チェックするならここ【PR】",
    "紹介ページはこちら【PR】",
]

_CTA_REPLY_TEASE = [
    "詳細はリプで【PR】",
    "リンクはリプに置いたよ【PR】",
    "続きはリプ見てね【PR】",
    "気になる人はリプへ【PR】",
]

_REPLY_TEXTS = [
    "紹介した作品はここから【PR】\n{portal}",
    "こちらから読めます【PR】\n{portal}",
    "リンク置いとくね【PR】\n{portal}",
    "詳細ページはここ【PR】👇\n{portal}",
]


def pick_parent_cta(link_placement: str, *, rng: random.Random | None = None) -> str:
    r = rng or random
    if link_placement == "parent":
        return r.choice(_CTA_PARENT)
    if link_placement == "reply":
        return r.choice(_CTA_REPLY_TEASE)
    return ""


def pick_reply_text(portal: str, *, rng: random.Random | None = None) -> str:
    r = rng or random
    return r.choice(_REPLY_TEXTS).format(portal=portal)


def assemble_parent_post_text(
    body: str,
    hashtag_block: str,
    cta: str,
    *,
    portal: str = "",
    link_placement: str = "reply",
) -> str:
    """親ツイート本文を組み立てる（純粋関数・テスト用）。"""
    parts = [body.strip()] if body and body.strip() else []
    if hashtag_block:
        parts.append(hashtag_block)
    if cta:
        parts.append(cta)
    if link_placement == "parent" and portal:
        parts.append(portal)
    return "\n\n".join(parts).strip()


def should_post_reply(link_placement: str, tweet_id: int | str | None) -> bool:
    """親成功かつ reply モードのときだけリプする。"""
    return link_placement == "reply" and tweet_id is not None and str(tweet_id).isdigit()


# ---------------------
# メディアアップロード（v1.1）
# ---------------------
def upload_images_v1(api_v1, image_buffers: list[io.BytesIO]) -> list[str]:
    media_ids = []
    for buf in image_buffers:
        try:
            media = api_v1.media_upload(filename=buf.name, file=buf)
            media_ids.append(media.media_id_string)
            logger.info(f"✅ アップロード成功: {buf.name}")
        except Exception as e:
            logger.error(f"❌ アップロード失敗: {buf.name} → {e}")
    return media_ids


def upload_images_v1_on_local(api_v1, image_paths: list[str]) -> list[str]:
    media_ids = []
    for path in image_paths:
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            logger.error(f"❌ 画像ファイルが存在しません: {abs_path}")
            continue
        try:
            media = api_v1.media_upload(abs_path)
            media_ids.append(media.media_id_string)
            logger.info(f"✅ アップロード成功: {abs_path}")
        except Exception as e:
            logger.exception(f"❌ アップロード失敗: {abs_path} → {e}")
    return media_ids


def upload_video_v1(api_v1, video_path: str) -> str:
    """動画をアップロードして media_id を返す"""
    abs_path = os.path.abspath(video_path)
    if not os.path.exists(abs_path):
        logger.error(f"❌ 動画ファイルが存在しません: {abs_path}")
        return ""
    try:
        media = api_v1.media_upload(abs_path, media_category='tweet_video')
        logger.info(f"✅ 動画アップロード成功: {abs_path}")
        return media.media_id_string
    except Exception as e:
        logger.exception(f"❌ 動画アップロード失敗: {abs_path} → {e}")
        return ""


def fetch_image_buffer_from_url(url: str) -> io.BytesIO:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    buffer = io.BytesIO(response.content)
    buffer.name = "cover.jpg"
    return buffer


def cleanup_file(filepath: str):
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    except FileNotFoundError:
        pass


def normalize(actresses):
    if actresses is None:
        return []

    if isinstance(actresses, str):
        actresses = actresses.strip()
        if actresses.startswith("[") and actresses.endswith("]"):
            try:
                actresses = json.loads(actresses)
            except Exception:
                actresses = [actresses]
        else:
            actresses = [actresses]

    if not isinstance(actresses, list):
        actresses = [actresses]

    names = []
    for a in actresses:
        if isinstance(a, dict):
            names.append(a.get("name"))
        else:
            names.append(str(a))

    names = [n for n in names if n and n.strip()]
    return names


def post_casual_twitter(
    text: str,
    account: str = "1",
    screen_name: str = "",
) -> tuple[bool, str]:
    """雑談テキストのみ投稿（メディア・URLなし）。"""
    logger.info("💬 雑談投稿開始: アカウント%s %s", account, screen_name)
    _, client_v2 = get_clients(account)
    body = (text or "").strip()
    if not body:
        return False, "雑談本文が空"
    try:
        tweet_id = safe_post_tweet(client_v2, body)
        if not tweet_id:
            return False, "雑談投稿に失敗"
        logger.info("✅ 雑談投稿完了 tweet_id=%s", tweet_id)
        return True, "投稿成功"
    except Exception as e:
        logger.error("🚨 雑談投稿エラー: %s", e)
        return False, str(e)


def post_full_twitter(
    comment: str,
    title: str,
    image_urls: list[str],
    affiliate_url: str,
    image_large_url: str = "",
    image_small_url: str = "",
    point: str = "",
    summary: str = "",
    account: str = "1",
    sample_movie_url: str = "",
    tachiyomi_url: str = "",
    campaigns: list | None = None,
    screen_name: str = "",
    content_id: str = "",
    site: str = "",
    floor: str = "",
    item_id: str = "",
    service: str = "",
    authors: list | None = None,
    actresses: list | None = None,
    link_placement: str = "reply",
) -> tuple[bool, str]:
    """作品紹介投稿。

    link_placement:
      - "parent": 親にポータルURL。リプなし
      - "reply": 親はURLなし。成功時のみ遅延リプでURL
    """
    logger.info(
        "🚀 スレッド投稿開始: アカウント%s %s link_placement=%s",
        account,
        screen_name,
        link_placement,
    )
    api_v1, client_v2 = get_clients(account)
    tweet_id = None
    portal = build_portal_url(site, content_id, floor=floor, service=service)

    try:
        body = build_post_text(comment, summary, point, campaigns, affiliate_url)
        hashtag_block = pick_hashtag_block(site, actresses=actresses, authors=authors)
        cta = pick_parent_cta(link_placement)
        post_text = assemble_parent_post_text(
            body,
            hashtag_block,
            cta,
            portal=portal,
            link_placement=link_placement,
        )

        media_ids = []
        if image_large_url:
            try:
                buf = fetch_image_buffer_from_url(image_large_url)
                media_ids = upload_images_v1(api_v1, [buf])
            except Exception as e:
                logger.error(f"⚠ カバー画像アップロード失敗: {e}")
        elif image_small_url:
            try:
                buf = fetch_image_buffer_from_url(image_small_url)
                media_ids = upload_images_v1(api_v1, [buf])
            except Exception as e:
                logger.error(f"⚠ カバー画像アップロード失敗: {e}")

        logger.info(f"🚨 ポスト: {post_text}")
        tweet_id = safe_post_tweet(client_v2, post_text, media_ids)
        if tweet_id:
            tweet_id = int(tweet_id)
        else:
            raise RuntimeError("❌ 最初の画像投稿に失敗")

        if should_post_reply(link_placement, tweet_id):
            wait_lo, wait_hi = REPLY_WAIT_SECONDS_RANGE
            wait_time = random.uniform(wait_lo, wait_hi)
            logger.info("⏳ リプ待機 %.0f 秒", wait_time)
            time.sleep(wait_time)
            reply_text = pick_reply_text(portal)
            final_id = safe_post_tweet(client_v2, reply_text, reply_to=tweet_id)
            logger.info(f"🏁 アーカイブ固定ポスト完了 final_tweet_id={final_id}")

        return True, "投稿成功"

    except Exception as e:
        logger.error(f"🚨 投稿中にエラー: {e}")
        return False, str(e)

    finally:
        if tachiyomi_url:
            for path in locals().get("tachiyomi_image_paths", []):
                cleanup_file(path)
        if sample_movie_url:
            cleanup_file(locals().get("video_path", ""))
