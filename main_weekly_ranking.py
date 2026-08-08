"""
FANZA videoa 週間ランキングを X と Livedoor ブログへ投稿する。

WEEKLY_RANKING_SEQUENCE の第2要素が X_ACCOUNT_SETTINGS のアカウントID。
有効アカウントに紐づく URL のみ処理する（現状は account 2 = videoa のみ）。

環境変数:
  DRY_RUN=1 … 投稿せず本文のみログ
  WEEKLY_RANKING_POST_X=0 … X 投稿をスキップ
  WEEKLY_RANKING_POST_LIVEDOOR=0 … Livedoor 投稿をスキップ
"""

from __future__ import annotations

import html as html_module
import json
import logging
import os
import re
import time

from dotenv import load_dotenv

load_dotenv()

from config.x_settings import X_ACCOUNT_SETTINGS
from db.blog_repository import (
    apply_livedoor_env_from_config,
    list_enabled_livedoor_blog_configs,
)
from livedoor_blog.post import post_to_livedoor_blog
from twitter_api.safe_post import safe_post_tweet
from twitter_api.twitter_client import get_clients
from utils.logger import setup_logger
from utils.portal_ranking import (
    RankingPage,
    content_id_from_portal_url,
    fetch_weekly_ranking,
)

setup_logger("main_weekly_ranking.log")
logger = logging.getLogger(__name__)

# 案A: FANZA videoa のみ（account 2）。他ジャンルはコメントアウトで復旧可。
WEEKLY_RANKING_SEQUENCE: list[tuple[str, str]] = [
    ("https://www.fanzaportal.com/ranking/videoa/weekly", "2"),
    # ("https://www.fanzaportal.com/ranking/videoc/weekly", "2"),
    # ("https://www.fanzaportal.com/ranking/comic/weekly", "2"),
    # ("https://www.fanzaportal.com/ranking/digital_doujin/weekly", "2"),
    # ("https://www.dmmportal.jp/ranking/ebook/comic/weekly", "1"),
    # ("https://www.dmmportal.jp/ranking/ebook/novel/weekly", "1"),
    # ("https://www.dmmportal.jp/ranking/ebook/otherbooks/weekly", "1"),
    # ("https://www.dmmportal.jp/ranking/ebook/photo/weekly", "1"),
]

TOP_RANKS_IN_TWEET = 3
TOP_RANKS_IN_BLOG = 3
# 女優名がないときのフォールバック題名（X 加重）
MAX_TITLE_WEIGHTED_TWEET = 22
MAX_TITLE_CHARS = 72
SLEEP_SECONDS_BETWEEN_POSTS = 15
# X は日本語などを重み2で数える。Python len ではなく加重長で制限する。
TWEET_WEIGHTED_SOFT_LIMIT = 270
_TCO_URL_LENGTH = 23


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def _is_twitter_heavy_char(ch: str) -> bool:
    """X の加重カウントで重み2になりやすい文字（CJK・全角・絵文字など）。"""
    o = ord(ch)
    return (
        0x1100 <= o <= 0x11FF
        or 0x2E80 <= o <= 0x9FFF
        or 0x3000 <= o <= 0x303F
        or 0xAC00 <= o <= 0xD7AF
        or 0xF900 <= o <= 0xFAFF
        or 0xFF00 <= o <= 0xFFEF
        or 0x1F300 <= o <= 0x1FAFF
    )


def twitter_weighted_length(text: str) -> int:
    """X 投稿向けの概算文字数（URL は t.co = 23 として加算）。"""
    urls = re.findall(r"https?://\S+", text or "")
    body = text or ""
    for u in urls:
        body = body.replace(u, "", 1)
    weight = 0
    for ch in body:
        weight += 2 if _is_twitter_heavy_char(ch) else 1
    return weight + _TCO_URL_LENGTH * len(urls)


def _portal_label(url: str) -> str:
    if "fanzaportal.com" in url:
        if "/videoa/" in url:
            return "FANZA Portal 動画(AV) 週間ランキング"
        return "FANZA Portal 週間ランキング"
    if "dmmportal.jp" in url:
        return "DMMポータル 週間ランキング"
    return "週間ランキング"


def _clip_title(title: str, *, max_chars: int = MAX_TITLE_CHARS) -> str:
    t = title.strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _clip_title_weighted(title: str, *, max_weight: int = MAX_TITLE_WEIGHTED_TWEET) -> str:
    """タイトルを X 加重文字数で切り詰める。"""
    t = title.strip()
    if twitter_weighted_length(t) <= max_weight:
        return t
    out: list[str] = []
    w = 0
    ellipsis_w = 2  # …
    for ch in t:
        cw = 2 if _is_twitter_heavy_char(ch) else 1
        if w + cw + ellipsis_w > max_weight:
            break
        out.append(ch)
        w += cw
    return "".join(out) + "…"


def _parse_actress_names(val: object) -> list[str]:
    """trn_dmm_items.actress（JSON配列/文字列）から名前を取り出す。"""
    if val is None:
        return []
    if isinstance(val, list):
        names: list[str] = []
        for x in val:
            if isinstance(x, dict):
                n = str(x.get("name") or "").strip()
            else:
                n = str(x).strip()
            if n:
                names.append(n)
        return names[:3]
    s = str(val).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            parsed = json.loads(s.replace("'", '"'))
        except json.JSONDecodeError:
            return [s]
        return _parse_actress_names(parsed)
    return [s]


def _rank_label(item) -> str:
    """順位行の表示名（女優名優先、なければタイトル短縮）。"""
    actress = (getattr(item, "actress", None) or "").strip()
    if actress:
        return actress
    return _clip_title_weighted(getattr(item, "title", "") or "（タイトル不明）")


def enrich_ranking_actresses(account_id: str, page: RankingPage) -> None:
    """Supabase の actress を content_id で埋める（破壊的）。"""
    from db.supabase_client import init_supabase

    ids = []
    for it in page.items:
        cid = (it.content_id or content_id_from_portal_url(it.url)).strip()
        it.content_id = cid
        if cid:
            ids.append(cid)
    if not ids:
        return
    try:
        supabase = init_supabase(account_id)
        res = (
            supabase.table("trn_dmm_items")
            .select("content_id, actress")
            .in_("content_id", ids)
            .execute()
        )
    except Exception:
        logger.exception("actress 取得失敗 account=%s", account_id)
        return
    by_id: dict[str, str] = {}
    for row in res.data or []:
        cid = str(row.get("content_id") or "").strip()
        names = _parse_actress_names(row.get("actress"))
        if cid and names:
            by_id[cid] = " / ".join(names)
    for it in page.items:
        if it.content_id and it.content_id in by_id:
            it.actress = by_id[it.content_id]


def _extract_week_label(headline: str) -> str:
    """見出しから週ラベルを抜く（例: 2026年32週目 / 8月2週）。"""
    h = (headline or "").strip()
    if not h:
        return ""
    head = h.split("｜", 1)[0].strip()
    m = re.search(r"(\d{4}年\d{1,2}週目)", head)
    if m:
        return m.group(1)
    m = re.search(r"(\d{1,2}月\d{1,2}週)", head)
    if m:
        return m.group(1)
    if "週目" in head and len(head) <= 24:
        return head
    return ""


def build_ranking_tweet(url: str, page: RankingPage) -> str:
    """X 加重文字数 280 以内に収まる週間ランキングツイートを組む（TOP3・女優名）。"""
    week = _extract_week_label(page.headline or "")
    header = "📊 FANZA動画 週間ランキング"
    if week:
        header = f"{header}（{week}）"

    def _compose(n: int) -> str:
        lines: list[str] = [header, ""]
        for it in page.items[:n]:
            lines.append(f"{it.rank}位 {_rank_label(it)}")
        lines.append("")
        lines.append(url)
        return "\n".join(lines)

    max_n = min(TOP_RANKS_IN_TWEET, len(page.items))
    text = _compose(max_n)
    if twitter_weighted_length(text) <= TWEET_WEIGHTED_SOFT_LIMIT:
        return text
    for n in range(max_n - 1, -1, -1):
        text = _compose(n)
        if twitter_weighted_length(text) <= TWEET_WEIGHTED_SOFT_LIMIT:
            return text
    return text


def build_ranking_blog_title(url: str, page: RankingPage) -> str:
    """スマホ新着向けに短い記事タイトル。"""
    if "/videoa/" in url:
        base = "FANZA動画｜今週の週間ランキング"
    elif "fanzaportal.com" in url:
        base = "FANZA｜今週の週間ランキング"
    else:
        base = "今週の週間ランキング"
    week = _extract_week_label(page.headline or "")
    if week:
        return f"{base}（{week}）"
    return base


def build_ranking_blog_html(url: str, page: RankingPage) -> str:
    esc = html_module.escape
    label = _portal_label(url)
    parts: list[str] = [
        f"<p>{esc(label)} TOP{TOP_RANKS_IN_BLOG}（女優名）をまとめました。"
        "気になる作品はポータルからチェック。</p>",
    ]
    if page.headline:
        parts.append(f"<p><strong>{esc(page.headline)}</strong></p>")
    if page.updated:
        parts.append(f"<p>{esc(page.updated)}</p>")

    parts.append("<ol>")
    for it in page.items[:TOP_RANKS_IN_BLOG]:
        name = (it.actress or "").strip() or "（女優情報なし）"
        title = esc(it.title)
        name_esc = esc(name)
        if it.url:
            href = esc(it.url, quote=True)
            parts.append(
                f'<li value="{it.rank}">'
                f"<strong>{name_esc}</strong><br>"
                f'<a href="{href}" rel="noopener noreferrer">{title}</a>'
                f"</li>"
            )
        else:
            parts.append(
                f'<li value="{it.rank}"><strong>{name_esc}</strong><br>{title}</li>'
            )
    parts.append("</ol>")

    ranking_href = esc(url, quote=True)
    parts.append(
        f'<p><a href="{ranking_href}" rel="noopener noreferrer">'
        f"ランキングページを見る</a></p>"
    )
    return "\n".join(parts)


def log_ranking_post_content(
    logger: logging.Logger,
    *,
    url: str,
    account_id: str,
    screen_name: str,
    page: RankingPage,
    tweet_text: str,
    blog_title: str,
    blog_html: str,
    dry_run: bool,
) -> None:
    """運用前確認用に、取得結果と投稿本文をログへ詳細出力する。"""
    py_len = len(tweet_text)
    weighted = twitter_weighted_length(tweet_text)
    logger.info("---------- 週間ランキング 投稿内容ログ ----------")
    logger.info(
        "meta url=%s account_id=%s screen_name=%s dry_run=%s parsed_items=%s "
        "tweet_py_len=%s tweet_weighted=%s blog_title=%r",
        url,
        account_id,
        screen_name,
        dry_run,
        len(page.items),
        py_len,
        weighted,
        blog_title,
    )
    logger.info("parsed_headline=%s", page.headline)
    logger.info("parsed_updated=%s", page.updated)
    titles_preview = " | ".join(f"{it.rank}:{it.title[:40]}" for it in page.items[:12])
    if len(page.items) > 12:
        titles_preview += " | ..."
    logger.info("parsed_titles_preview=%s", titles_preview)
    logger.info(
        "tweet_body (開始)\n%s\ntweet_body (終了) py_len=%s weighted=%s",
        tweet_text,
        py_len,
        weighted,
    )
    logger.info(
        "blog_html (開始)\n%s\nblog_html (終了) chars=%s",
        blog_html[:2000],
        len(blog_html),
    )
    logger.info("---------- 以上 ----------")


def _pick_livedoor_config(account_id: str) -> dict[str, str] | None:
    """videoa 行を優先、なければ先頭。"""
    rows = list_enabled_livedoor_blog_configs(account_id)
    if not rows:
        return None
    for row in rows:
        if str(row.get("floor") or "").strip().lower() == "videoa":
            return row
    return rows[0]


def _post_to_x(account_id: str, text: str) -> bool:
    try:
        _, client_v2 = get_clients(account_id)
    except Exception as e:
        logger.error("Twitter クライアント取得失敗 account=%s: %s", account_id, e)
        return False
    tweet_id = safe_post_tweet(client_v2, text)
    if tweet_id:
        logger.info(
            "✅ X 投稿完了 account=%s tweet_id=%s chars=%s",
            account_id,
            tweet_id,
            len(text),
        )
        return True
    logger.warning("⚠ X 投稿失敗 account=%s", account_id)
    return False


def _post_to_livedoor(account_id: str, title: str, body_html: str) -> bool:
    cfg = _pick_livedoor_config(account_id)
    if not cfg:
        logger.warning(
            "Livedoor 設定なし（mst_blog_accounts）account=%s → スキップ",
            account_id,
        )
        return False
    apply_livedoor_env_from_config(cfg)
    os.environ["LIVEDOOR_BLOG_ENABLED"] = "1"
    os.environ["LIVEDOOR_POST_METHOD"] = "atompub"
    try:
        post_to_livedoor_blog(title, body_html, title_fallback="週間ランキング")
    except Exception:
        logger.exception(
            "Livedoor 投稿失敗 account=%s blog_id=%s",
            account_id,
            cfg.get("blog_id"),
        )
        return False
    logger.info(
        "✅ Livedoor 投稿完了 account=%s blog_id=%s title=%r",
        account_id,
        cfg.get("blog_id"),
        title,
    )
    return True


def main() -> None:
    dry = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")
    post_x = _env_flag("WEEKLY_RANKING_POST_X", True)
    post_blog = _env_flag("WEEKLY_RANKING_POST_LIVEDOOR", True)

    for account_id, config in X_ACCOUNT_SETTINGS.items():
        if not config.get("enabled"):
            logger.info(
                "⚠️ %s は実施フラグOFFのためスキップします",
                config.get("screen_name", account_id),
            )
            continue

        matches = [(u, a) for u, a in WEEKLY_RANKING_SEQUENCE if a == account_id]
        if not matches:
            logger.info(
                "⚠️ %s は週間ランキングの対象URLが定義されていません",
                config.get("screen_name", account_id),
            )
            continue

        for url, _ in matches:
            try:
                page = fetch_weekly_ranking(url)
            except Exception as e:
                logger.exception("取得失敗: %s (%s)", url, e)
                continue

            if not page:
                continue

            enrich_ranking_actresses(account_id, page)
            tweet_text = build_ranking_tweet(url, page)
            blog_title = build_ranking_blog_title(url, page)
            blog_html = build_ranking_blog_html(url, page)
            screen = config.get("screen_name", account_id)
            log_ranking_post_content(
                logger,
                url=url,
                account_id=account_id,
                screen_name=screen,
                page=page,
                tweet_text=tweet_text,
                blog_title=blog_title,
                blog_html=blog_html,
                dry_run=dry,
            )

            if dry:
                logger.info("DRY_RUN のため投稿スキップ")
                time.sleep(1)
                continue

            if post_x:
                _post_to_x(account_id, tweet_text)
            else:
                logger.info("WEEKLY_RANKING_POST_X=0 のため X スキップ")

            if post_blog:
                _post_to_livedoor(account_id, blog_title, blog_html)
            else:
                logger.info("WEEKLY_RANKING_POST_LIVEDOOR=0 のため Livedoor スキップ")

            time.sleep(SLEEP_SECONDS_BETWEEN_POSTS)


if __name__ == "__main__":
    main()
