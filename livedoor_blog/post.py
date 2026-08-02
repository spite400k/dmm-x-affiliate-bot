"""ライブドアブログ（livedoor.blogcms.jp）への記事投稿。

公式 Atom Publishing Protocol（推奨）と、提示サンプルに近い Playwright による
管理画面操作のいずれかを環境変数で選択できます。

AtomPub（既定）:
  LIVEDOOR_BLOG_ENABLED=1
  LIVEDOOR_POST_METHOD=atompub  （省略可）
  LIVEDOOR_ID=（livedoor ID）
  LIVEDOOR_BLOG_NAME=（AtomPub のブログ名。/atompub/ と /article の間。
    例: https://livedoor.blogcms.jp/atompub/staff/article なら staff）
  LIVEDOOR_ATOMPUB_PASSWORD=（管理画面 ブログ設定 > その他 > API Key の AtomPub用パスワード。
    ログインパスワードではない点に注意）
  LIVEDOOR_ATOMPUB_BASIC_USER=（任意。Basic 認証のユーザー名。省略時は LIVEDOOR_ID。
    401 のときは blog_id と同じ値を試す例あり）
  LIVEDOOR_ATOMPUB_COLLECTION_TMPL=（任意。POST 先 URL。{blog_name} を置換。
    省略時は https://livedoor.blogcms.jp/atompub/{blog_name}/article（記事コレクション）。
    レガシー等で末尾なしのみ有効な場合は …/atompub/{blog_name} を明示指定）

Playwright:
  LIVEDOOR_POST_METHOD=playwright
  LIVEDOOR_ID / LIVEDOOR_PASSWORD=（ログイン用）
  LIVEDOOR_NEW_ENTRY_URL=（例: https://livedoor.blogcms.jp/blog/ブログ名/article/edit）
  必要に応じ LIVEDOOR_TITLE_SELECTOR / LIVEDOOR_BODY_SELECTOR で CSS を上書き。

記事 HTML の体裁:
  LIVEDOOR_ARTICLE_STYLE=simple / popular いずれも本文は次の順:
    ① review_digest（筆者レビュー）→ 立ち読み（PR）→ ②パッケージ画像 → サンプル動画（FANZA・あり時）
    → ③サンプル画像 → ④ポータル（アフィリエイト）リンク
    → ⑤プレミアム宣伝（site/account 別・アフィリエイト URL があるときのみ独立セクション）。
  記事タイトルは Atom の <title> のみ（本文内では h1 を出さず重複を避ける）。
  build_livedoor_blog_html(item_row=…) に trn_dmm_items を渡すとサンプル画像を展開する。
  ai_review_row=… に dmm_ai_review_summaries を渡すと review_digest を筆者レビューに使う。
  account_id / portal_site を渡すと config.blog_settings.resolve_premium_promo で⑤を出し分ける。
"""

from __future__ import annotations

import html as html_module
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import requests

logger = logging.getLogger(__name__)

LIVEDOOR_LOGIN_URL = "https://livedoor.blogcms.jp/member/"
# 記事コレクション POST 先（公式: …/atompub/{blog_name}/article）。末尾なしは 400 Unknown endpoint になる
_DEFAULT_ATOMPUB_COLLECTION_TMPL = "https://livedoor.blogcms.jp/atompub/{blog_name}/article"
# Livedoor AtomPub: 空 title/content で 400。title は 86 文字以上で 400（実測上限 85）
_ATOMPUB_TITLE_MAX_CHARS = 85
_ATOMPUB_BODY_PLACEHOLDER = "<p>詳細は下記リンクからご確認ください。</p>"


def _fit_atompub_title(title: str) -> str:
    t = (title or "").strip()
    if not t or len(t) <= _ATOMPUB_TITLE_MAX_CHARS:
        return t
    return t[: _ATOMPUB_TITLE_MAX_CHARS - 1] + "…"


def _fit_catchy_title(hook: str, core: str, tail: str) -> str:
    """hook + core + tail を AtomPub 上限以内に収める。"""
    candidate = f"{hook}{core}{tail}"
    if len(candidate) <= _ATOMPUB_TITLE_MAX_CHARS:
        return candidate
    max_core = _ATOMPUB_TITLE_MAX_CHARS - len(hook) - len(tail)
    if max_core >= 1:
        short = core if len(core) <= max_core else core[: max_core - 1] + "…"
        fitted = f"{hook}{short}{tail}"
        if len(fitted) <= _ATOMPUB_TITLE_MAX_CHARS:
            return fitted
    alt_tail = "レビュー｜今すぐチェック"
    max_core = _ATOMPUB_TITLE_MAX_CHARS - len(hook) - len(alt_tail)
    short = core if len(core) <= max_core else core[: max_core - 1] + "…"
    return f"{hook}{short}{alt_tail}"


_DEFAULT_TITLE_SELECTORS = (
    'input[name="article[title]"]',
    'input[name="title"]',
    "#article_title",
    'input[type="text"]',
)
_DEFAULT_BODY_SELECTORS = (
    'textarea[name="article[body]"]',
    'textarea[name="body"]',
    "#article_body",
    "textarea.body",
)


def is_livedoor_blog_enabled() -> bool:
    return os.environ.get("LIVEDOOR_BLOG_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _post_method() -> str:
    return os.environ.get("LIVEDOOR_POST_METHOD", "atompub").strip().lower()


def livedoor_blog_ready() -> bool:
    if not is_livedoor_blog_enabled():
        return False
    if _post_method() == "playwright":
        return bool(
            os.environ.get("LIVEDOOR_ID", "").strip()
            and os.environ.get("LIVEDOOR_PASSWORD", "").strip()
            and os.environ.get("LIVEDOOR_NEW_ENTRY_URL", "").strip()
        )
    return bool(
        os.environ.get("LIVEDOOR_ID", "").strip()
        and os.environ.get("LIVEDOOR_ATOMPUB_PASSWORD", "").strip()
        and os.environ.get("LIVEDOOR_BLOG_NAME", "").strip()
    )


def _item_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_genres(genres: object) -> list[str]:
    if genres is None:
        return []
    if isinstance(genres, list):
        return [str(g).strip() for g in genres if str(g).strip()]
    s = str(genres).strip()
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


# DMM.com ebook の floor_code と日本語フロア名（編集トーン・表示用）
_EBOOK_FLOOR_LABEL_JA: dict[str, str] = {
    "comic": "コミック",
    "novel": "文芸・ラノベ",
    "otherbooks": "ビジネス・実用",
    "photo": "写真集",
}


def _ebook_editorial_tone(item: dict[str, Any]) -> str:
    """ebook 行の floor / カテゴリから編集トーンキーを返す。非 ebook は 'default'。"""
    if _item_str(item.get("service")).lower() != "ebook":
        return "default"
    fl = _item_str(item.get("floor")).lower()
    fn = _item_str(item.get("floor_name"))
    cat = _item_str(item.get("category_name"))
    for code, ja in _EBOOK_FLOOR_LABEL_JA.items():
        if fl == code or code in fl or fn == ja or ja in cat:
            return code
    if "コミック" in cat or "comic" in cat.lower():
        return "comic"
    if any(x in cat for x in ("文芸", "ラノベ", "小説")) or "novel" in cat.lower():
        return "novel"
    if any(x in cat for x in ("ビジネス", "実用", "資格", "語学")):
        return "otherbooks"
    if "写真" in cat or "グラビア" in cat or "photo" in cat.lower():
        return "photo"
    return "photo"


def _ebook_floor_clause(service: str, floor_raw: str, tone: str) -> str:
    """紹介文用: floor コードを日本語ラベルに置き換えつつ列挙。"""
    s = service.strip()
    f = floor_raw.strip()
    if not s or not f:
        return ""
    if s.lower() == "ebook" and tone in _EBOOK_FLOOR_LABEL_JA:
        ja = _EBOOK_FLOOR_LABEL_JA[tone]
        return f"{s}（{ja}）向けの配信コンテンツ"
    return f"{s} の {f} 向け配信コンテンツ"


def _price_line_genre_phrase(tone: str) -> str:
    """価格コメント用のジャンル帯表現。"""
    if tone == "comic":
        return "電子コミックとしては"
    if tone == "novel":
        return "文芸・ラノベの電子版としては"
    if tone == "otherbooks":
        return "ビジネス・実用の電子書籍としては"
    if tone == "photo":
        return "写真集としては"
    return "本作のカテゴリとしては"


def _format_price_yen(n: object) -> str:
    if n is None:
        return ""
    try:
        return f"¥{int(n):,}"
    except (TypeError, ValueError):
        return ""


def _price_int(n: object) -> int | None:
    if n is None:
        return None
    try:
        return int(n)
    except (TypeError, ValueError):
        return None


def _parse_price_value(n: object) -> int | None:
    """API の '500~' などを含む価格文字列を整数円に変換。"""
    s = _item_str(n)
    if not s:
        return None
    s = s.replace("~", "").replace(",", "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


# DMM API prices.deliveries.delivery[].type → 表示名（配信形式・画質）
_DELIVERY_TYPE_LABEL_JA: dict[str, str] = {
    "stream": "ストリーミング",
    "download": "ダウンロード",
    "hd": "HD（高画質）",
    "8k": "8K",
    "4k": "4K",
    "iosdl": "iOSダウンロード",
    "androiddl": "Androidダウンロード",
}
_DELIVERY_TYPE_SORT: dict[str, int] = {
    "stream": 10,
    "download": 20,
    "hd": 30,
    "4k": 40,
    "8k": 50,
    "iosdl": 60,
    "androiddl": 70,
}
_DOWNLOAD_TYPE_CODES = frozenset({"download", "iosdl", "androiddl"})
_4K_TYPE_CODES = frozenset({"4k", "8k"})


def _delivery_type_label(type_code: str) -> str:
    t = type_code.strip().lower()
    return _DELIVERY_TYPE_LABEL_JA.get(t, type_code or "—")


def _raw_prices_dict(item_row: dict[str, Any]) -> dict[str, Any] | None:
    raw = item_row.get("raw_json")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    prices = raw.get("prices")
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except json.JSONDecodeError:
            return None
    return prices if isinstance(prices, dict) else None


def _price_variants_raw_from_item(
    item_row: dict[str, Any],
) -> list[tuple[str, str, int, int | None]]:
    """(type_code, 表示ラベル, 販売価格, 定価) のリスト（type ごと）。"""
    variants: list[tuple[str, str, int, int | None]] = []
    prices = _raw_prices_dict(item_row)
    if prices:
        deliveries = prices.get("deliveries")
        if isinstance(deliveries, dict):
            dlist = deliveries.get("delivery")
            if isinstance(dlist, dict):
                dlist = [dlist]
            if isinstance(dlist, list):
                for d in dlist:
                    if not isinstance(d, dict):
                        continue
                    type_code = _item_str(d.get("type")).lower()
                    price_n = _parse_price_value(d.get("price"))
                    if price_n is None:
                        continue
                    list_n = _parse_price_value(d.get("list_price"))
                    variants.append(
                        (
                            type_code,
                            _delivery_type_label(type_code),
                            price_n,
                            list_n,
                        )
                    )
    if variants:
        seen: set[str] = set()
        unique: list[tuple[str, str, int, int | None]] = []
        for type_code, label, price_n, list_n in sorted(
            variants, key=lambda x: (_DELIVERY_TYPE_SORT.get(x[0], 99), x[2])
        ):
            if type_code in seen:
                continue
            seen.add(type_code)
            unique.append((type_code, label, price_n, list_n))
        return unique

    price_n = _parse_price_value(item_row.get("price"))
    list_n = _parse_price_value(item_row.get("list_price"))
    if price_n is None and prices:
        price_n = _parse_price_value(prices.get("price"))
    if list_n is None and prices:
        list_n = _parse_price_value(prices.get("list_price"))
    if price_n is None:
        return []
    delivery = _item_str(item_row.get("delivery"))
    label = delivery if delivery else "販売価格"
    return [("", label, price_n, list_n)]


def _plan_summary_text(
    type_codes: set[str], *, is_cheapest: bool, all_type_codes: set[str]
) -> str:
    """type の組み合わせからプラン内容の一文要約。"""
    has_dl = bool(type_codes & _DOWNLOAD_TYPE_CODES)
    has_stream = "stream" in type_codes
    has_4k = bool(type_codes & _4K_TYPE_CODES)
    has_hd = "hd" in type_codes
    catalog_has_hd = "hd" in all_type_codes or bool(all_type_codes & _4K_TYPE_CODES)

    if has_4k:
        q = "8K" if "8k" in type_codes else "4K"
        return (
            f"最高画質（{q}）で、保存もネット再生も両方できる全部入り。"
        )
    if has_hd and has_stream and not has_dl:
        if is_cheapest:
            return (
                "標準高画質（HD）だが、保存はできず"
                "ネット接続時のみ再生できる最安プラン。"
            )
        return "標準高画質（HD）で、保存もネット再生も両方できるプラン。"
    if has_hd and not has_stream and not has_dl:
        return "標準高画質（HD）で、保存もネット再生も両方できるプラン。"
    if has_hd:
        return "標準高画質（HD）で、保存もネット再生も両方できるプラン。"
    if has_stream and not has_dl:
        if is_cheapest and catalog_has_hd:
            return (
                "標準高画質（HD）だが、保存はできず"
                "ネット接続時のみ再生できる最安プラン。"
            )
        if is_cheapest:
            return (
                "保存はできずネット接続時のみ再生できる最安プラン。"
            )
        return "ネット接続時のみ再生できるストリーミングプラン。"
    if has_dl and has_stream:
        return "画質はそこそこで、保存もネット再生も両方できる節約プラン。"
    if has_dl:
        return "画質はそこそこで、保存もネット再生も両方できる節約プラン。"
    return ""


def _group_price_variants(
    raw: list[tuple[str, str, int, int | None]],
) -> list[tuple[str, int, int | None]]:
    """(プランまとめ文, 販売価格, 定価)。同一価格の type は1プランにまとめる。"""
    groups: dict[tuple[int, int | None], list[tuple[str, str]]] = {}
    for type_code, label, price_n, list_n in raw:
        groups.setdefault((price_n, list_n), []).append((type_code, label))
    if not groups:
        return []
    min_price = min(k[0] for k in groups)
    multi = len(groups) > 1
    all_codes: set[str] = set()
    for items in groups.values():
        all_codes.update(code for code, _ in items)
    out: list[tuple[str, int, int | None]] = []
    for (price_n, list_n), items in sorted(
        groups.items(), key=lambda x: x[0][0], reverse=True
    ):
        items.sort(key=lambda t: _DELIVERY_TYPE_SORT.get(t[0], 99))
        codes = {code for code, _ in items}
        is_cheapest = multi and price_n == min_price
        summary = _plan_summary_text(
            codes, is_cheapest=is_cheapest, all_type_codes=all_codes
        )
        if not summary:
            summary = " / ".join(lab for _, lab in items)
        plan_line = f"{_format_price_yen(price_n)}プラン：{summary}"
        out.append((plan_line, price_n, list_n))
    return out


def _price_variants_from_item(
    item_row: dict[str, Any],
) -> list[tuple[str, int, int | None]]:
    """(プランまとめ文, 販売価格, 定価)。"""
    return _group_price_variants(_price_variants_raw_from_item(item_row))


def _format_price_variant_line(
    label: str, price_n: int, list_n: int | None, *, esc: Any = html_module.escape
) -> str:
    price_s = esc(_format_price_yen(price_n))
    off_badge = ""
    if list_n is not None and list_n > price_n:
        list_s = esc(_format_price_yen(list_n))
        pct = round((1 - price_n / list_n) * 100)
        if pct > 0:
            off_badge = (
                f' <span style="font-size:0.82em;font-weight:bold;color:#fff;'
                f'background:#c62828;padding:0.1em 0.45em;border-radius:4px;">'
                f"{esc(f'{pct}%OFF')}</span>"
            )
        return (
            f"<strong style='color:#c62828;'>{price_s}</strong>"
            f" <s style='color:#666;font-size:0.92em;'>定価 {list_s}</s>{off_badge}"
        )
    return f"<strong style='color:#c62828;'>{price_s}</strong>"


_POINT_RETURN_KEYWORDS = (
    "ポイント還元",
    "ポイントアップ",
    "ボーナスポイント",
    "ポイント付与",
    "ポイントプレゼント",
    "ポイント最大",
    "ポイント10",
    "ポイント20",
    "ポイント30",
    "ポイント50",
)


def _campaign_deadline_label(date_end: object) -> str:
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


def _campaign_title(c: object) -> str:
    if isinstance(c, dict):
        return _item_str(c.get("title"))
    return ""


def _campaign_mentions_point_return(title: str) -> bool:
    t = title or ""
    return any(k in t for k in _POINT_RETURN_KEYWORDS)


def _price_promo_html(item_row: dict[str, Any] | None) -> str:
    """配信形式・画質ごとの価格表示（複数プランは表、1件はシンプル表示）。"""
    if not item_row:
        return ""
    variants = _price_variants_from_item(item_row)
    if not variants:
        return ""
    esc = html_module.escape
    if len(variants) == 1:
        _, price_n, list_n = variants[0]
        return (
            '<div class="ld-aff-price" style="margin:0 0 0.75rem;font-size:1.02em;line-height:1.5;">'
            f'<p style="margin:0 0 0.25rem;font-weight:bold;color:#333;">{esc("価格")}</p>'
            f'<p style="margin:0;">'
            f"{_format_price_variant_line('', price_n, list_n, esc=esc)}</p>"
            "</div>"
        )
    trs: list[str] = []
    for label, price_n, list_n in variants:
        trs.append(
            "<tr>"
            f'<td style="padding:0.45rem 0.5rem;border-bottom:1px solid #f0e0e0;'
            f'vertical-align:top;line-height:1.5;">{esc(label)}</td>'
            f'<td style="padding:0.45rem 0.5rem;border-bottom:1px solid #f0e0e0;'
            f'text-align:right;white-space:nowrap;vertical-align:top;">'
            f"{_format_price_variant_line(label, price_n, list_n, esc=esc)}</td>"
            "</tr>"
        )
    return (
        '<div class="ld-aff-price" style="margin:0 0 0.75rem;font-size:1.02em;line-height:1.55;">'
        f'<p style="margin:0 0 0.4rem;font-weight:bold;color:#333;">'
        f'{esc("価格（プランにより異なります）")}</p>'
        '<table class="ld-aff-price-table" style="width:100%;border-collapse:collapse;'
        'font-size:0.95em;">'
        "<thead><tr>"
        '<th scope="col" style="text-align:left;padding:0.4rem 0.5rem;'
        'border-bottom:2px solid #c62828;color:#b71c1c;">プラン</th>'
        '<th scope="col" style="text-align:right;padding:0.4rem 0.5rem;'
        'border-bottom:2px solid #c62828;color:#b71c1c;">価格</th>'
        "</tr></thead><tbody>"
        + "".join(trs)
        + "</tbody></table></div>"
    )


def _campaigns_promo_html(campaigns: list | None) -> str:
    """キャンペーン・ポイント還元のお得情報ブロック。"""
    if not campaigns:
        return ""
    esc = html_module.escape
    point_lines: list[str] = []
    deal_items: list[str] = []
    for c in campaigns:
        if not isinstance(c, dict):
            continue
        title = _campaign_title(c)
        if not title:
            continue
        status = _campaign_deadline_label(c.get("date_end"))
        status_html = (
            f' <span style="color:#c62828;font-weight:bold;">{esc(status)}</span>'
            if status
            else ""
        )
        li = (
            f'<li style="margin:0.35rem 0;padding:0.35rem 0 0.35rem 0.25rem;'
            f'border-bottom:1px dashed #f0c0c0;">'
            f"🎉 {esc(title)}{status_html}</li>"
        )
        if _campaign_mentions_point_return(title):
            point_lines.append(li)
        else:
            deal_items.append(li)
    if not point_lines and not deal_items:
        return ""
    parts: list[str] = []
    if point_lines:
        parts.append(
            '<div style="margin:0 0 0.75rem;padding:0.65rem 0.75rem;'
            'background:#fff8e1;border-left:4px solid #ff9800;border-radius:4px;">'
            '<p style="margin:0 0 0.35rem;font-weight:bold;color:#e65100;">'
            "💰 ポイント還元・ボーナス</p>"
            '<ul style="list-style:none;margin:0;padding:0;">'
            + "".join(point_lines)
            + "</ul></div>"
        )
    if deal_items:
        parts.append(
            '<div style="margin:0 0 0.75rem;padding:0.65rem 0.75rem;'
            'background:#fff5f5;border-left:4px solid #c62828;border-radius:4px;">'
            '<p style="margin:0 0 0.35rem;font-weight:bold;color:#b71c1c;">'
            "🔥 開催中のキャンペーン</p>"
            '<ul style="list-style:none;margin:0;padding:0;">'
            + "".join(deal_items)
            + "</ul></div>"
        )
    return "".join(parts)


def _cta_button_html(href: str, label: str, *, primary: bool = False) -> str:
    """目立つ CTA ボタン風リンク。"""
    u = html_module.escape(href.strip(), quote=True)
    t = html_module.escape(label)
    if primary:
        style = (
            "display:block;margin:0.65rem 0;padding:0.85rem 1rem;"
            "font-size:1.05em;font-weight:bold;text-align:center;text-decoration:none;"
            "color:#fff;background:linear-gradient(180deg,#e53935 0%,#c62828 100%);"
            "border-radius:8px;box-shadow:0 2px 6px rgba(198,40,40,0.35);"
        )
    else:
        style = (
            "display:block;margin:0.5rem 0;padding:0.65rem 1rem;"
            "font-size:0.95em;font-weight:bold;text-align:center;text-decoration:none;"
            "color:#c62828;background:#fff;border:2px solid #c62828;border-radius:8px;"
        )
    return f'<p style="margin:0;"><a href="{u}" rel="nofollow sponsored" style="{style}">{t}</a></p>'


def _review_sentence(item: dict[str, Any]) -> str:
    rc = item.get("review_count")
    ra = item.get("review_average")
    try:
        rcn = int(rc) if rc is not None else 0
    except (TypeError, ValueError):
        rcn = 0
    if rcn <= 0:
        return ""
    if ra is not None:
        try:
            rav = float(ra)
            return f"ユーザー評価の平均は {rav:.1f} 点で、レビューは {rcn} 件です。"
        except (TypeError, ValueError):
            pass
    return f"レビューが {rcn} 件寄せられています。"


def _sample_image_urls(item: dict[str, Any], *, limit: int = 6) -> list[str]:
    urls: list[str] = []
    raw = item.get("sample_images")
    if isinstance(raw, list):
        urls.extend(_item_str(u) for u in raw if _item_str(u))
    s = _item_str(item.get("sample_images_s"))
    if s:
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    urls.extend(_item_str(u) for u in parsed if _item_str(u))
            except json.JSONDecodeError:
                pass
        else:
            for part in s.replace("\n", ",").split(","):
                p = part.strip()
                if p:
                    urls.append(p)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:limit]


def _narrative_paragraphs_from_item(item: dict[str, Any], title: str) -> list[str]:
    """DB 列から読みやすい紹介文（プレーンテキスト）を数段落生成。"""
    paragraphs: list[str] = []
    t = title.strip()
    genres = _normalize_genres(item.get("genres"))
    cat = _item_str(item.get("category_name"))
    service = _item_str(item.get("service"))
    floor = _item_str(item.get("floor"))
    series = _item_str(item.get("series"))
    maker = _item_str(item.get("maker"))

    clauses: list[str] = []
    if cat:
        clauses.append(f"カテゴリは「{cat}」")
    if service and floor:
        tone = _ebook_editorial_tone(item)
        fc = _ebook_floor_clause(service, floor, tone)
        if fc:
            clauses.append(fc)
    if genres:
        gtxt = "、".join(genres[:6])
        if len(genres) > 6:
            gtxt += " など"
        clauses.append(f"ジャンル・タグには {gtxt} が付与されています")
    if clauses:
        body = "、".join(clauses)
        if t:
            paragraphs.append(f"『{t}』は、{body}。")
        else:
            paragraphs.append(f"{body}。")

    credits: list[str] = []
    for label, key in (
        ("出演", "actress"),
        ("監督", "director"),
        ("著者", "author"),
    ):
        v = _item_str(item.get(key))
        if v:
            credits.append(f"{label}は {v}")
    if maker:
        credits.append(f"レーベル・メーカーは {maker}")
    if series:
        credits.append(f"シリーズは「{series}」")
    if credits:
        paragraphs.append("。".join(credits) + "。")

    meta: list[str] = []
    rd = _item_str(item.get("release_date"))
    if rd:
        meta.append(f"発売・配信開始の表記は {rd}")
    price = _format_price_yen(item.get("price"))
    lp = _format_price_yen(item.get("list_price"))
    if price:
        if lp and lp != price:
            meta.append(f"価格は {price}（参考定価 {lp}）")
        else:
            meta.append(f"価格は {price}")
    vol = _item_str(item.get("volume"))
    if vol:
        meta.append(f"収録ボリュームの表記は {vol}")
    rv = _review_sentence(item)
    if rv:
        meta.append(rv.rstrip("。"))
    if meta:
        paragraphs.append("。".join(meta) + "。")

    return [p for p in paragraphs if p.strip()]


def _item_specs_rows_html(item: dict[str, Any]) -> str:
    """主要スペックを表形式（行は値があるものだけ）。"""
    esc = html_module.escape
    rows: list[tuple[str, str]] = []
    mapping: tuple[tuple[str, str], ...] = (
        ("content_id", "コンテンツID"),
        ("product_id", "プロダクトID"),
        ("category_name", "カテゴリ"),
        ("site", "サイト"),
        ("service", "サービス"),
        ("floor", "フロア"),
        ("delivery", "配信形態"),
        ("release_date", "発売・配信日"),
        ("stock", "在庫・販売状態"),
        ("jancode", "JANコード"),
        ("item_url", "作品ページURL"),
        ("sample_movie_url", "サンプル動画URL"),
    )
    for key, label in mapping:
        v = _item_str(item.get(key))
        if v:
            rows.append((label, v))
    genres = _normalize_genres(item.get("genres"))
    if genres:
        rows.append(("ジャンル", "、".join(genres)))
    variants = _price_variants_from_item(item)
    if variants:
        if len(variants) == 1:
            lab, pn, ln = variants[0]
            line = _format_price_yen(pn)
            if ln is not None and ln > pn:
                line += f"（定価 {_format_price_yen(ln)}）"
            if lab != "販売価格":
                line = f"{lab}：{line}"
        else:
            parts = []
            for lab, pn, ln in variants:
                seg = f"{lab} {_format_price_yen(pn)}"
                if ln is not None and ln > pn:
                    seg += f"（定価 {_format_price_yen(ln)}）"
                parts.append(seg)
            line = " / ".join(parts)
        rows.append(("価格", line))
    vol = _item_str(item.get("volume"))
    if vol:
        rows.append(("ボリューム", vol))
    for label, key in (
        ("出演", "actress"),
        ("監督", "director"),
        ("著者", "author"),
        ("メーカー", "maker"),
        ("シリーズ", "series"),
    ):
        v = _item_str(item.get(key))
        if v:
            rows.append((label, v))
    rv = _review_sentence(item)
    if rv:
        rows.append(("レビュー", rv.rstrip("。")))

    if not rows:
        return ""

    trs = []
    for lab, val in rows:
        trs.append(
            f"<tr><th scope='row'>{esc(lab)}</th><td>{esc(val)}</td></tr>"
        )
    return (
        '<table class="item-specs" style="border-collapse:collapse;width:100%;'
        'max-width:42rem;font-size:95%;">'
        "<tbody>"
        + "".join(trs)
        + "</tbody></table>"
    )


def _sample_gallery_html(item: dict[str, Any], title: str) -> str:
    urls = _sample_image_urls(item)
    if not urls:
        return ""
    esc = html_module.escape
    alt_base = esc(title)[:120] if title.strip() else "サンプル画像"
    figs = []
    for i, u in enumerate(urls):
        figs.append(
            f'<figure style="margin:0.5rem 0;">'
            f'<img src="{esc(u, quote=True)}" alt="{alt_base} サンプル {i + 1}" '
            f'loading="lazy" style="max-width:100%;height:auto;" /></figure>'
        )
    return (
        '<div class="sample-gallery" style="display:grid;gap:0.75rem;">'
        + "".join(figs)
        + "</div>"
    )


def _is_fanza_item_row(item_row: dict[str, Any]) -> bool:
    site = _item_str(item_row.get("site")).upper().replace(" ", "")
    return site == "FANZA" or site.startswith("FANZA")


def _sample_movie_url_from_item(item_row: dict[str, Any]) -> str:
    """FANZA サンプル動画（litevideo）URL。列 → raw_json.sampleMovieURL の順。"""
    u = _item_str(item_row.get("sample_movie_url"))
    if u:
        return u
    raw = item_row.get("raw_json")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return ""
    if not isinstance(raw, dict):
        return ""
    sm = raw.get("sampleMovieURL")
    if not isinstance(sm, dict):
        return ""
    for key in ("size_720_480", "size_644_414", "size_560_360", "size_476_306"):
        v = _item_str(sm.get(key))
        if v:
            return v
    for val in sm.values():
        if isinstance(val, str) and "litevideo" in val:
            s = val.strip()
            if s:
                return s
    return ""


def _sample_movie_section_html(
    item_row: dict[str, Any] | None, title: str
) -> str:
    """FANZA かつサンプル動画 URL があるとき、litevideo プレイヤーを埋め込む。"""
    if not item_row or not _is_fanza_item_row(item_row):
        return ""
    movie_url = _sample_movie_url_from_item(item_row)
    if not movie_url:
        return ""
    esc = html_module.escape
    src = esc(movie_url, quote=True)
    alt = esc(title)[:120] if title.strip() else "サンプル動画"
    return (
        '<div class="ld-sample-movie" style="margin:0.75rem 0;max-width:100%;">'
        '<div style="max-width:720px;margin:0 auto;">'
        f'<iframe src="{src}" width="100%" height="405" '
        f'title="{alt}（PR）" loading="lazy" '
        'style="border:0;display:block;max-width:100%;" '
        'allow="autoplay; encrypted-media" allowfullscreen></iframe>'
        "</div>"
        '<p style="margin:0.5rem 0 0;font-size:0.9em;">'
        f'<a href="{src}" rel="nofollow sponsored" target="_blank" '
        'referrerpolicy="no-referrer-when-downgrade">'
        "サンプル動画を別ウィンドウで見る（PR）</a></p>"
        "</div>"
    )


def _tachiyomi_link_html(item: dict[str, Any]) -> str:
    u = _item_str(item.get("tachiyomi_affiliate_url")) or _item_str(
        item.get("tachiyomi_url")
    )
    if not u:
        return ""
    esc = html_module.escape
    return (
        f'<li><a href="{esc(u, quote=True)}" rel="nofollow sponsored">'
        "立ち読みページ（PR）</a></li>"
    )


def _text_array_field(val: object) -> list[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    s = str(val).strip()
    return [s] if s else []


def _smallint_display(val: object) -> str | None:
    if val is None:
        return None
    try:
        return str(int(val))
    except (TypeError, ValueError):
        return None


def _avg_rating_display(val: object) -> str | None:
    if val is None:
        return None
    try:
        return f"{float(val):.2f}"
    except (TypeError, ValueError):
        return None


def _strip_okuri_brackets(title: str) -> str:
    """先頭の【…】を繰り返し除去（商品名の芯だけ取り出す）。"""
    t = title.strip()
    while True:
        m = re.match(r"^【[^】]+】\s*", t)
        if not m:
            break
        t = t[m.end() :].strip()
    return t


def _title_suggests_ebook_digital_bonus(title: str) -> bool:
    t = title
    return "電子版" in t and (
        "特典" in t or "限定" in t or "だけ" in t or "カット" in t
    )


def _credit_entry_name(entry: object) -> str:
    if entry is None:
        return ""
    if isinstance(entry, dict):
        n = entry.get("name")
        return str(n).strip() if n is not None else ""
    return str(entry).strip()


def _parse_credit_names(val: object) -> list[str]:
    if val is None:
        return []
    if isinstance(val, dict):
        n = _credit_entry_name(val)
        return [n] if n else []
    if isinstance(val, list):
        names = [_credit_entry_name(x) for x in val]
        return [n for n in names if n][:4]
    s = str(val).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            parsed = json.loads(s.replace("'", '"'))
        except json.JSONDecodeError:
            return [s]
        if isinstance(parsed, list):
            names = [_credit_entry_name(x) for x in parsed]
            return [n for n in names if n][:4]
        if isinstance(parsed, dict):
            n = _credit_entry_name(parsed)
            return [n] if n else []
    return [s]


def _primary_credit_label(item: dict[str, Any]) -> tuple[str, list[str]]:
    """（ラベル, 名前の配列）。出演があれば出演を優先。"""
    for label, key in (("出演", "actress"), ("著者", "author"), ("監督", "director")):
        names = _parse_credit_names(item.get(key))
        if names:
            return label, names
    return "", []


def blog_post_title_for_item(
    title: str,
    item: dict[str, Any] | None = None,
    ai_review_row: dict[str, Any] | None = None,
) -> str:
    """検索・SNS で指が止まりやすい短めのキャッチタイトル（必要なときだけ加工）。"""
    raw = os.environ.get("LIVEDOOR_CATCHY_TITLE", "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return title.strip()
    t = title.strip()
    core = _strip_okuri_brackets(t) or t
    bonus = _title_suggests_ebook_digital_bonus(t)
    digest = _item_str(ai_review_row.get("review_digest")) if ai_review_row else ""
    tone = _ebook_editorial_tone(item) if item else "default"
    mid = ""
    if tone == "photo" and ("王道" in digest or "王道" in core):
        mid = "王道グラビアの手応えを味わえる"
    if bonus and core:
        if tone == "novel":
            hook = "【電子版特典が熱い】"
        elif tone == "otherbooks":
            hook = "【電子版独占特典が熱い】"
        elif tone == "comic":
            hook = "【電子版限定描き下ろしが熱い】"
        else:
            hook = "【電子版限定カットが熱い】"
        tail = "レビュー！今すぐチェック"
        if mid:
            tail = f"レビュー！{mid}｜今すぐチェック"
        return _fit_catchy_title(hook, core, tail)
    if len(t) > 58:
        suffix = " レビュー｜チェック"
        if len(core) > 52:
            return _fit_atompub_title(f"{core[:52]}…{suffix}")
        return _fit_atompub_title(f"{core}{suffix}")
    return _fit_atompub_title(t)


def _trim_for_reader(
    text: str, *, max_chars: int = 320, multiline: bool = False
) -> str:
    s = text.strip()
    if not s:
        return ""
    if not multiline:
        # 長文の定型見出しが続く場合は先頭段落だけを採用
        first_para = s.split("\n\n", 1)[0].strip()
        s = first_para or s
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def _plain_text_paragraph_blocks(text: str) -> list[str]:
    """平文を句点または単一改行で複数段落に分割。"""
    t = text.strip()
    if not t:
        return []
    if "\n" in t or "\r" in t:
        t = t.replace("\r\n", "\n").replace("\r", "\n")
        lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
        if len(lines) > 1:
            return lines
        t = lines[0] if lines else t
    segments = [s.strip() for s in t.split("。") if s.strip()]
    if not segments:
        return [t]
    ends_period = t.rstrip().endswith("。")
    chunks: list[str] = []
    for i, seg in enumerate(segments):
        if i < len(segments) - 1:
            chunks.append(seg + "。")
        elif ends_period:
            chunks.append(seg + "。")
        else:
            chunks.append(seg)
    return chunks if len(chunks) > 1 else [t]


def _reader_voice_digest_to_blockquote_inner(quote: str, esc) -> str:
    """読者の声引用。blockquote 内は CMS が <br /> を落とすことがあるため改行は <p> の分割のみにする。"""
    q = quote.strip()
    if not q:
        return ""

    qn = q.replace("\r\n", "\n").replace("\r", "\n")
    lines_out: list[str] = []
    if "\n" in qn:
        for block in [b.strip() for b in qn.split("\n\n") if b.strip()]:
            for piece in _plain_text_paragraph_blocks(block):
                lines_out.append("<p>" + esc(piece) + "</p>")
    else:
        for piece in _plain_text_paragraph_blocks(qn):
            lines_out.append("<p>" + esc(piece) + "</p>")
    return "".join(lines_out)


def _ai_review_sections_html(row: dict[str, Any] | None) -> str:
    """dmm_ai_review_summaries 由来（レビュー要約・スコア・読者像・注意点）。"""
    if not row:
        return ""
    esc = html_module.escape
    digest = _item_str(row.get("review_digest"))
    summary_ai = _item_str(row.get("summary_text"))
    readers = _text_array_field(row.get("reader_types"))
    warnings = _text_array_field(row.get("warning_points"))
    score_rows: list[tuple[str, str]] = []
    for label, key in (
        ("総合満足度", "content_score"),
        ("感情移入", "emotion_score"),
        ("魅力・引きつけ", "attraction_score"),
        ("ジャンル傾向①", "genre_axis1_score"),
        ("ジャンル傾向②", "genre_axis2_score"),
    ):
        disp = _smallint_display(row.get(key))
        if disp is not None:
            score_rows.append((label, disp))
    rc_ai = row.get("review_count")
    ar_ai = row.get("avg_rating")
    meta_bits: list[str] = []
    try:
        if rc_ai is not None:
            meta_bits.append(f"参照レビュー件数 {int(rc_ai)} 件")
    except (TypeError, ValueError):
        pass
    ard = _avg_rating_display(ar_ai)
    if ard:
        meta_bits.append(f"平均評価 {ard} 点")

    if not (
        digest
        or summary_ai
        or score_rows
        or readers
        or warnings
        or meta_bits
    ):
        return ""

    parts: list[str] = []
    parts.append("<h2>レビュー要約・読者向け分析（AI）</h2>")
    if meta_bits:
        parts.append(
            "<p><small>"
            + esc("（" + "、".join(meta_bits) + "）")
            + "</small></p>"
        )
    if digest:
        parts.append("<h3>レビュー要旨</h3>")
        parts.append("<p>" + esc(digest).replace("\n", "<br />\n") + "</p>")
    if summary_ai:
        parts.append("<h3>あらすじ・内容の整理</h3>")
        parts.append("<p>" + esc(summary_ai).replace("\n", "<br />\n") + "</p>")
    if score_rows:
        parts.append("<h3>スコア指標（参考値）</h3>")
        trs = [
            f"<tr><th scope='row'>{esc(lab)}</th><td>{esc(val)}</td></tr>"
            for lab, val in score_rows
        ]
        parts.append(
            '<table class="ai-review-scores" style="border-collapse:collapse;'
            'width:100%;max-width:28rem;font-size:95%;"><tbody>'
            + "".join(trs)
            + "</tbody></table>"
        )
    if readers:
        parts.append("<h3>向いている読者像</h3>")
        parts.append("<ul>")
        for r in readers:
            parts.append(f"<li>{esc(r)}</li>")
        parts.append("</ul>")
    return "\n".join(parts)


def _item_rich_sections_html(item: dict[str, Any] | None, title: str) -> str:
    """trn_dmm_items 由来の追記ブロック（ナラティブ・スペック表・サンプル画像）。"""
    if not item:
        return ""
    esc = html_module.escape
    parts: list[str] = []
    paras = _narrative_paragraphs_from_item(item, title)
    if paras:
        parts.append("<h2>作品紹介</h2>")
        for p in paras:
            parts.append("<p>" + esc(p).replace("\n", "<br />\n") + "</p>")
    specs = _item_specs_rows_html(item)
    if specs:
        parts.append("<h2>作品データ・スペック</h2>")
        parts.append(specs)
    gallery = _sample_gallery_html(item, title)
    if gallery:
        parts.append(gallery)
    return "\n".join(parts)


def _merged_rich_sections_html(
    item_row: dict[str, Any] | None,
    ai_review_row: dict[str, Any] | None,
    title: str,
) -> str:
    """trn_dmm_items と dmm_ai_review_summaries を連結した追記ブロック。"""
    chunks = [
        _item_rich_sections_html(item_row, title),
        _ai_review_sections_html(ai_review_row),
    ]
    return "\n".join(c for c in chunks if c)


def _oshi_content_seed(item: dict[str, Any]) -> int:
    """作品ごとに安定したばらつき用の整数シード。"""
    key = (
        _item_str(item.get("content_id"))
        or _item_str(item.get("product_id"))
        or _item_str(item.get("title"))
        or "x"
    )
    h = 2166136261
    for c in key:
        h = (h ^ ord(c)) * 16777619
        h &= 0xFFFFFFFF
    return h % 997


def _editorial_oshi_points_fragments(
    item: dict[str, Any],
    genres: list[str],
    digest_raw: str,
    maker: str,
    name_phrase: str,
    rcn: int,
    rav: float | None,
) -> tuple[str, list[str]]:
    """推し欄: h2・1行リード・箇条書き（strong ラベル＋本文）。候補プール＋シードで順と件数を変える。"""
    esc = html_module.escape
    seed = _oshi_content_seed(item)
    digest = digest_raw or ""

    h2_options = (
        "ここが推しポイント！",
        "先に押さえたい見どころ",
        "制作のキモになるポイント",
        "手応えが伝わりやすいツボ",
    )
    h2_text = h2_options[seed % len(h2_options)]

    tone = _ebook_editorial_tone(item)

    if tone == "comic":
        density = (
            "コマ運びとページめくりのテンポが安定していて、冒頭から物語に入り込みやすい構成です。"
        )
        if digest and any(k in digest for k in ("テンポ", "読みやす", "コマ", "わかりやす")):
            density = (
                "コマ割りと流れの作りが読みやすさに効いており、"
                "手元の端末でも一気読みしやすいリズム感です。"
            )
        costume = (
            "作画の作り込みとキャラ芝居のバランスが良く、見開きや小ネタ回収まで楽しめる密度です。"
        )
        if genres:
            costume = (
                f"「{'・'.join(genres[:3])}」の雰囲気に沿った画風・演出で、"
                "世界観の統一感と見どころの振れ幅を両立しています。"
            )
        d_heads = ("読み味のテンポ", "コマ割りと誘導", "見開きの効き")
        c_heads = ("作画の作り込み", "キャラの立ち上がり", "画面情報の整理")
    elif tone == "novel":
        density = (
            "語りのトーンと文のリズムが整っていて、長めのセッションでも疲れにくい読み心地です。"
        )
        if digest and any(k in digest for k in ("緊迫", "サスペンス", "伏線", "どんでん", "展開")):
            density = (
                "展開の起伏と情報の出し方が計算されており、"
                "先が気になってページを進めたくなる構成です。"
            )
        costume = (
            "人物関係と情景描写の厚みがじわじわ効いて、読後に余韻が残りやすい作りです。"
        )
        if genres:
            costume = (
                f"「{'・'.join(genres[:3])}」の文脈に沿った世界の立ち上がりで、"
                "情景イメージを膨らませやすい描写が光ります。"
            )
        d_heads = ("文体とテンポ", "語りの引き込み", "情景の立ち上がり")
        c_heads = ("人物と関係性", "プロットの欠片", "世界観の作り")
    elif tone == "otherbooks":
        density = (
            "章立てと要点の整理が明瞭で、知りたい情報に素早く辿り着きやすい構成です。"
        )
        costume = (
            "図版・表・箇条書きなど、理解を助けるビジュアルが適度に挟まれた実用寄りの作りです。"
        )
        if genres:
            costume = (
                f"「{'・'.join(genres[:3])}」の実務文脈に沿った事例と解説で、"
                "そのまま応用しやすい知識の粒度高めです。"
            )
        d_heads = ("情報の密度と整理", "章構成のわかりやすさ", "実務への接続")
        c_heads = ("図表と補足", "すぐ使える示唆", "復習しやすい粒度")
    else:
        density = (
            "ロケーションのメリハリが効いていて、開放感と落ち着きの両方から魅力が立ち上がる構成です。"
        )
        if digest and ("オーストラリア" in digest or "茨城" in digest):
            density = (
                "南半球の開放的な風景と、原点の地のしっとりした空気感の対比が、"
                "多面的な魅力を一段と引き出しています。"
            )

        costume = (
            "王道のビキニから大人っぽいランジェリーまで、シーンごとの変化を楽しめる構成です。"
        )
        if digest and ("ヌーディ" in digest or "ヌード" in digest or "ランジェリー" in digest):
            costume = (
                "王道のビキニから大人っぽいランジェリー、さらに挑戦的なカットまで。"
                "「今、ここで見たい表情と衣装」が詰まった満足感が得られます。"
            )
        elif genres:
            costume = (
                f"「{'・'.join(genres[:3])}」の文脈に沿った衣装展開で、"
                "見どころの振れ幅を存分に楽しめます。"
            )
        d_heads = ("圧倒的な密度", "カットの濃さとテンポ", "構成のメリハリ")
        c_heads = ("衣装のバリエーション", "スタイリングの振れ幅", "ビジュアルの変化球")

    # (箇条書きラベル, 本文プレーン, 並べ替え用の種別キー)
    pool: list[tuple[str, str, int]] = []

    pool.append((d_heads[seed % 3], density, 10))

    pool.append((c_heads[(seed // 3) % 3], costume, 11))

    series = _item_str(item.get("series"))
    if series:
        pool.append(
            (
                "シリーズの文脈でも楽しめる点",
                f"シリーズ『{series}』の流れを感じつつ、本作だけの尖りと温度差もはっきり立っています。",
                12,
            )
        )

    if maker:
        if tone == "comic":
            pool.append(
                (
                    "レーベルらしい作画ライン",
                    f"{maker}作品で馴染みの画風・トーンの作りが、本作でも一貫して感じられます。",
                    13,
                )
            )
        elif tone == "novel":
            pool.append(
                (
                    "レーベル・シリーズの読み味",
                    f"{maker}ラインで培われた編集の型が、本作の語りの安定感にもつながっています。",
                    13,
                )
            )
        elif tone == "otherbooks":
            pool.append(
                (
                    "出版社ラインの信頼感",
                    f"{maker}の実用・ビジネス系で重ねてきた説明の丁寧さが、本作でもはっきり出ています。",
                    13,
                )
            )
        else:
            pool.append(
                (
                    "レーベルらしい撮り下ろし感",
                    f"{maker}作品にありがちな、色味と空気の作り込みが本作でも効いています。",
                    13,
                )
            )

    if name_phrase:
        if tone == "comic":
            pool.append(
                (
                    "キャラの魅せ方",
                    f"{name_phrase}の魅力がコマとセリフ回しで前面に出ており、"
                    "推しの延長線でも満足しやすいです。",
                    14,
                )
            )
        elif tone == "novel":
            pool.append(
                (
                    "著者・語りの魅せ方",
                    f"{name_phrase}ならではの文体と視点が効いており、"
                    "ファン目線でも新鮮味を拾いやすいです。",
                    14,
                )
            )
        elif tone == "otherbooks":
            pool.append(
                (
                    "著者の説明の切れ味",
                    f"{name_phrase}の説明スタイルが明快で、要点の抜け漏れを感じにくいです。",
                    14,
                )
            )
        else:
            pool.append(
                (
                    "キャストの魅せ方",
                    f"{name_phrase}の魅力が画面上で前面に出る画面設計になっており、"
                    "推しの延長線でも満足しやすいです。",
                    14,
                )
            )

    if rcn >= 5:
        rb = (
            f"投稿レビューは{rcn}件と厚みがあり、迷いがちな最後の一押しになる"
            "「第三者の声」として信頼できます。"
        )
        if rav is not None:
            rb = (
                f"投稿レビューは{rcn}件、平均 {rav:.1f} 点と数字の裏付けも厚いです。"
                "手応えの理由を短時間でも把握しやすいです。"
            )
        pool.append(("レビューが太い点も材料に", rb, 15))
    elif rcn >= 1:
        pool.append(
            (
                "レビューで拾える手触り",
                f"レビューはまだ{rcn}件ながら、購入前に雰囲気の芯を掴む手がかりになります。",
                16,
            )
        )

    vol = _item_str(item.get("volume"))
    if vol:
        pool.append(
            (
                "収録ボリュームの満足感",
                f"収録の表記は「{vol}」。一度にまとめて楽しめる密度感も含めて、"
                "買い切り型の魅力が出やすい構成です。",
                17,
            )
        )

    if _item_str(item.get("sample_movie_url")):
        pool.append(
            (
                "サンプルで先に触れられる体感",
                "サンプル映像があれば、静止画だけでは伝わりにくいテンポ感や空気感を先に確かめられます。",
                18,
            )
        )

    if digest and any(k in digest for k in ("表情", "微笑", "目線", "目元")):
        pool.append(
            (
                "表情・目線の刺さり",
                "表情の切り替わりや目線の置き方が、作品の温度を左右する要になっています。",
                19,
            )
        )

    if digest and any(k in digest for k in ("光", "照明", "彩度", "トーン", "色味")):
        pool.append(
            (
                "光と色の作り",
                "光の当て方や全体のトーンが一貫していて、シーンごとに「見せたい質感」が立ち上がりやすいです。",
                20,
            )
        )

    if digest and any(k in digest for k in ("屋外", "ビーチ", "プール", "海", "水着")):
        if tone in ("photo", "default"):
            pool.append(
                (
                    "ロケーションの開放感",
                    "ロケーションの空気感が写真の主役にもなりやすく、季節感や開放感を味わう楽しみ方に向きます。",
                    21,
                )
            )

    if tone == "comic":
        pool.append(
            (
                "コマ割りと読み味の要点",
                "コマの大小と流れの作りでテンポが出ており、短時間でも世界観に引き込まれやすい配置です。",
                22,
            )
        )

    want_n = 3 + (seed % 2)
    keyed: list[tuple[int, str, str, int]] = []
    for label, body, bk in pool:
        rank = ((seed * 31) ^ (bk * 17)) & 0x7FFFFFFF
        rank %= 10000
        keyed.append((rank, label, body, bk))
    keyed.sort(key=lambda x: x[0])

    seen_labels: set[str] = set()
    selected: list[tuple[str, str]] = []
    for _, label, body, _ in keyed:
        if label in seen_labels:
            continue
        seen_labels.add(label)
        selected.append((label, body))
        if len(selected) >= want_n:
            break

    lead_options = (
        "購入前に押さえたい観点を、見出しの階層を浅くして拾い読みしやすく整理しています。",
        "迷いやすいポイントを、ラベルと一文で並べています。",
    )
    lead = lead_options[(seed // 5) % len(lead_options)]

    iw = "\u3000"
    lines: list[str] = [
        '<p style="margin:0.6rem 0 0.75rem;line-height:1.75;font-size:96%;color:#333;">'
        + esc(lead)
        + "</p>",
        '<ul style="margin:0 0 1.1rem;padding-left:1.2rem;line-height:1.75;">',
    ]
    for label, body in selected:
        lines.append(
            f'<li style="margin:0.4rem 0;"><strong>{esc(label)}</strong>{iw}{esc(body)}</li>'
        )
    lines.append("</ul>")

    return h2_text, lines


def _editorial_article_sections_html(
    item: dict[str, Any] | None,
    canonical_title: str,
    ai_row: dict[str, Any] | None,
    affiliate_url: str,
    *,
    article_headline: str | None = None,
) -> str:
    """編集ブロック。冒頭の魅力のあと、推し（リード＋箇条書き）→ 読者の反応 → デジタル版の強み → おすすめ層の順。"""
    if not item:
        return ""
    esc = html_module.escape
    ct = canonical_title.strip()
    genres = _normalize_genres(item.get("genres"))
    maker = _item_str(item.get("maker"))
    price = _format_price_yen(item.get("price"))
    digest_raw = _item_str(ai_row.get("review_digest")) if ai_row else ""
    readers = _text_array_field(ai_row.get("reader_types")) if ai_row else []
    rc_item = item.get("review_count")
    ra_item = item.get("review_average")
    try:
        rcn = int(rc_item) if rc_item is not None else 0
    except (TypeError, ValueError):
        rcn = 0
    rav: float | None = None
    if ra_item is not None:
        try:
            rav = float(ra_item)
        except (TypeError, ValueError):
            rav = None
    label, names = _primary_credit_label(item)
    name_phrase = "、".join(names[:2]) if names else ""
    bonus = _title_suggests_ebook_digital_bonus(ct)
    ebook_tone = _ebook_editorial_tone(item)

    parts: list[str] = []

    # ■ 魅力の核（体験＋踏み込んだ理由）
    head = "作品の魅力"
    if name_phrase:
        head = f"{name_phrase}の集大成、作品の魅力"
    parts.append(f"<h2>{esc(head)}</h2>")
    intro_bits: list[str] = []
    if ebook_tone == "comic":
        intro_core = "コマの流れとテンポが心地よく、短い休憩でも読み進めたくなる描き込みが魅力です。"
    elif ebook_tone == "novel":
        intro_core = "語りのリズムと情景の重なりがじんわり効いて、読後に余韻が残りやすい構成が魅力です。"
    elif ebook_tone == "otherbooks":
        intro_core = "要点の整理と実務に繋がる示唆のバランスが良く、すぐ手元に置いておきたい実用性が魅力です。"
    else:
        intro_core = "画面を進めるたびに視線が釘付けになる密度の高さが魅力です。"
    if (
        article_headline is not None
        and article_headline.strip()
        and _norm_title_for_dedupe(ct) == _norm_title_for_dedupe(article_headline)
    ):
        intro_bits.append("本作は、" + intro_core)
    else:
        intro_bits.append(f"『{ct}』は、" + intro_core)
    if maker:
        if ebook_tone == "otherbooks":
            intro_bits.append(
                f"{maker}ならではの説明の型で、要点が頭に入りやすい構成が得られます。"
            )
        else:
            intro_bits.append(f"{maker}ならではの仕上がりで、世界観ごと没入できる体験が得られます。")
    elif genres:
        intro_bits.append(f"「{'・'.join(genres[:3])}」の空気感を存分に味わえます。")
    parts.append("<p>" + esc("".join(intro_bits)) + "</p>")
    if name_phrase:
        if ebook_tone == "comic":
            fan_line = (
                f"だから{name_phrase}ファンなら、試し読みで画風とテンポを確かめておく価値が大きい一冊です。"
            )
        elif ebook_tone == "novel":
            fan_line = (
                f"だから{name_phrase}の文体が好きな方なら、"
                "冒頭で相性を確かめておきたい一本です。"
            )
        elif ebook_tone == "otherbooks":
            fan_line = (
                f"だから{name_phrase}の説明スタイルが合う方なら、"
                "要点整理の相棒にしやすい一冊です。"
            )
        else:
            fan_line = (
                f"だから{name_phrase}ファンなら、気になった瞬間に公式ページを開いておく価値が大きい一冊です。"
            )
    else:
        fan_line = "だからジャンルが好きな方なら、一度は公式ページで中身を確かめておきたい作品です。"
    parts.append("<p>" + esc(fan_line) + "</p>")

    # ① 推しポイント（h2＋リード p＋ ul/li・strong ラベル。プール＋シードで順と件数を変える）
    oshi_h2, oshi_frags = _editorial_oshi_points_fragments(
        item, genres, digest_raw, maker, name_phrase, rcn, rav
    )
    parts.append(f"<h2>{esc(oshi_h2)}</h2>")
    parts.extend(oshi_frags)

    # ② 読者の反応（推しポイントの直後）
    if rcn > 0 or rav is not None or digest_raw or readers:
        parts.append("<h2>読者の反応と評価</h2>")
        react: list[str] = []
        if rav is not None:
            react.append(f"ユーザー評価は平均 {rav:.1f} 点と高く")
        if rcn > 0:
            react.append(f"レビューは {rcn} 件と厚みがあります")
        if react:
            praise = ""
            if digest_raw or rcn >= 5:
                if ebook_tone == "comic":
                    praise = (
                        "「作画の気迫がある」「テンポ良く読めた」"
                        "といった絶賛のニュアンスも目立ちます。"
                    )
                elif ebook_tone == "novel":
                    praise = (
                        "「引き込まれる展開」「文体が読みやすい」"
                        "といった満足の声も目立ちます。"
                    )
                elif ebook_tone == "otherbooks":
                    praise = (
                        "「実務ですぐ使えた」「要点が整理されている」"
                        "といった実用面での評価も目立ちます。"
                    )
                else:
                    praise = (
                        "「高密度な写真群に圧倒された」「王道の完成度が高い」"
                        "といった絶賛のニュアンスも目立ちます。"
                    )
            parts.append("<p>" + esc("、".join(react) + "。") + esc(praise) + "</p>")
        elif digest_raw:
            parts.append(
                "<p>"
                + esc("レビュー要約では、満足度の高い声が中心に集まっています。")
                + "</p>"
            )
        if digest_raw:
            quote = _trim_for_reader(digest_raw, max_chars=1220, multiline=True)
            parts.append("<p><strong>読者の声（抜粋）</strong></p>")
            inner = _reader_voice_digest_to_blockquote_inner(quote, esc)
            if inner:
                parts.append("<blockquote>" + inner + "</blockquote>")
        rc_ai = _smallint_display(ai_row.get("review_count")) if ai_row else None
        ar_ai = _avg_rating_display(ai_row.get("avg_rating")) if ai_row else None
        if rc_ai or ar_ai:
            bits = []
            if rc_ai:
                bits.append(f"本記事の要約では参照レビュー {rc_ai} 件")
            if ar_ai:
                bits.append(f"平均 {ar_ai} 点")
            parts.append("<p><small>" + esc("、".join(bits) + "。") + "</small></p>")

    # ③ デジタル版の強み（電子版の特権 → 価格 → 今すぐ読める → サンプル誘導）
    parts.append("<h3>電子版（DMM）ならではの特権</h3>")
    if bonus:
        if ebook_tone == "novel":
            bonus_body = (
                "紙版にはない「電子版だけの加筆・特典エピソード」などが付く場合があり、"
                "ファンならデジタルを選ぶ価値が出やすいです。"
            )
        elif ebook_tone == "otherbooks":
            bonus_body = (
                "紙版にはない「電子版だけの付録データ・リンク集」などが付く場合があり、"
                "調べ物のスピードが上がる点も魅力です。"
            )
        elif ebook_tone == "comic":
            bonus_body = (
                "紙版にはない「電子版だけの描き下ろし・特典ページ」が収録されている点が大きな武器です。"
                "ファンならこちらを選ばない手はありません。"
            )
        else:
            bonus_body = (
                "紙版にはない「電子版だけの特典カット」が収録されている点が最大の武器です。"
                "ファンならこちらを選ばない手はありません。"
            )
        parts.append("<p>" + esc(bonus_body) + "</p>")
    else:
        if ebook_tone == "comic":
            nobonus = (
                "デジタル配信なら、購入後すぐに端末で高解像度のまま読み始められます。"
                "拡大表示でコマやセリフの細部まで追いやすいのも利点です。"
            )
        elif ebook_tone == "novel":
            nobonus = (
                "デジタル配信なら、購入後すぐに端末で読み始められます。"
                "文字サイズや余白の調整で長時間の読書もしやすく、しおりや検索も活かせます。"
            )
        elif ebook_tone == "otherbooks":
            nobonus = (
                "デジタル配信なら、購入後すぐに端末で参照を始められます。"
                "検索やブックマークで必要箇所へ戻りやすく、業務・学習の横の相棒に向きます。"
            )
        else:
            nobonus = (
                "デジタル配信なら、購入後すぐに手元の端末で高画質のまま楽しめます。"
                "拡大しながら質感や表情の細部まで味わえるのも大きな利点です。"
            )
        parts.append("<p>" + esc(nobonus) + "</p>")
    if price:
        genre_phrase = (
            _price_line_genre_phrase(ebook_tone)
            if _item_str(item.get("service")).lower() == "ebook"
            else _price_line_genre_phrase("default")
        )
        parts.append(
            "<p>"
            + esc(
                f"価格は {price} と{genre_phrase}標準的ながら、"
                "上記の体験価値を考えると納得感が出やすい帯です。"
            )
            + "</p>"
        )

    parts.append("<h2>デジタル版なら「今すぐ読める」</h2>")
    if ebook_tone in ("comic", "novel", "otherbooks"):
        now_read = (
            "DMMの電子版なら、購入後は待ち時間ほぼゼロで、数十秒以内にスマホやタブレットで読み始められます。"
            "「今この気分で読みたい」にそのまま応えられるスピード感が、デジタルならではのベネフィットです。"
        )
    else:
        now_read = (
            "DMMの電子版なら、購入後は待ち時間ほぼゼロで、数十秒以内にスマホやタブレットで読み始められます。"
            "「今この気分で見たい」にそのまま応えられるスピード感が、デジタルならではのベネフィットです。"
        )
    parts.append("<p>" + esc(now_read) + "</p>")
    sample_href = _item_str(affiliate_url) or _item_str(item.get("item_url"))
    if sample_href:
        uq = esc(sample_href, quote=True)
        if ebook_tone == "novel":
            sample_tail = (
                "で、無料で試し読みできる範囲をチェックしてみてください。"
                "文体やテンポの相性を、短時間で判断しやすくなります。"
            )
        elif ebook_tone == "comic":
            sample_tail = (
                "で、無料で読めるサンプル範囲をチェックしてみてください。"
                "画風とコマ運びの相性を、短時間で判断しやすくなります。"
            )
        elif ebook_tone == "otherbooks":
            sample_tail = (
                "で、無料で見られるサンプル範囲をチェックしてみてください。"
                "章立てと説明のトーンが自分に合うか、すぐに判断しやすくなります。"
            )
        else:
            sample_tail = (
                "で、無料で見られるサンプル画像をチェックしてみてください。"
                "中身のトーンが自分に合うか、一瞬で判断しやすくなります。"
            )
        parts.append(
            "<p>まずは"
            f'<a href="{uq}" rel="nofollow sponsored">'
            + esc("公式の作品ページ")
            + "</a>"
            + esc(sample_tail)
            + "</p>"
        )

    # こんな人におすすめ
    if readers:
        parts.append("<h2>こんな人におすすめ</h2>")
        parts.append("<ul>")
        for r in readers[:5]:
            extra = ""
            rl = r.strip()
            if "写真集" in rl or "ファン" in rl:
                extra = (
                    "これまでの歩みを振り返りつつ、最新の輝きを手元に残したい方。"
                )
            elif "コミック" in rl or "マンガ" in rl:
                extra = "画風とテンポの両方を試し読みで確かめたい方。"
            elif "小説" in rl or "文芸" in rl or "ラノベ" in rl:
                extra = "文体の相性を冒頭で確かめ、長めの読書にも備えたい方。"
            elif "ビジネス" in rl or "実用" in rl or "資格" in rl:
                extra = "業務や学習の参照として、必要箇所へすぐ戻りたい方。"
            elif "新規" in rl or "初心者" in rl:
                extra = "入り口として負担が少なく、世界観を一気に味わえる方。"
            elif "画質" in rl or "高画質" in rl:
                if ebook_tone in ("comic", "novel", "otherbooks"):
                    extra = "画面の解像度や文字の鮮明さまで気にして選びたい方。"
                else:
                    extra = "拡大表示で質感や表情の細部までじっくり見比べたい方。"
            else:
                extra = "本作のテンションと相性が良さそうな方。"
            parts.append(
                "<li><strong>" + esc(rl) + "</strong>：" + esc(extra) + "</li>"
            )
        parts.append("</ul>")
    elif name_phrase:
        parts.append("<h2>こんな人におすすめ</h2>")
        parts.append(
            "<ul><li><strong>"
            + esc(f"{name_phrase}ファン")
            + "</strong>："
            + esc("最新作の熱量を逃さずチェックしたい方。")
            + "</li></ul>"
        )

    return "\n".join(parts)


def _article_style(article_style: str | None) -> str:
    raw = (
        article_style
        if article_style is not None
        else os.environ.get("LIVEDOOR_ARTICLE_STYLE", "simple")
    ).strip().lower()
    return raw if raw in ("simple", "popular") else "simple"


def _digest_raw_from_ai_row(ai_review_row: dict[str, Any] | None) -> str:
    return _item_str(ai_review_row.get("review_digest")) if ai_review_row else ""


def _digest_author_review_html(digest_raw: str) -> str:
    """review_digest（ユーザレビューまとめ）をそのまま筆者レビューとして出力。"""
    text = (digest_raw or "").strip()
    if not text:
        return ""
    esc = html_module.escape
    qn = text.replace("\r\n", "\n").replace("\r", "\n")
    paras: list[str] = []
    if "\n" in qn:
        for block in [b.strip() for b in qn.split("\n\n") if b.strip()]:
            for piece in _plain_text_paragraph_blocks(block):
                paras.append(piece)
    else:
        paras = _plain_text_paragraph_blocks(qn)
    return "\n".join(f"<p>{esc(p)}</p>" for p in paras)


def _tachiyomi_section_html(item_row: dict[str, Any] | None) -> str:
    """筆者レビュー直後用の立ち読み CTA。"""
    if not item_row:
        return ""
    href = _item_str(item_row.get("tachiyomi_affiliate_url")) or _item_str(
        item_row.get("tachiyomi_url")
    )
    if not href:
        return ""
    return (
        '<div class="ld-tachiyomi-cta" style="margin:1.25rem 0 1.5rem;">'
        + _cta_button_html(href, "立ち読み・チラ見はこちら（PR）", primary=False)
        + "</div>"
    )


def _package_image_section_html(
    title: str,
    *,
    image_large_url: str = "",
    image_small_url: str = "",
    item_row: dict[str, Any] | None = None,
) -> str:
    """商品パッケージ画像（image_large_url 優先、無ければ image_small_url）。"""
    pkg = ""
    if item_row:
        pkg = _item_str(item_row.get("image_large_url")) or _item_str(
            item_row.get("image_small_url")
        )
    if not pkg:
        pkg = image_large_url.strip() or image_small_url.strip()
    if not pkg:
        return ""
    esc = html_module.escape
    alt = esc(title)[:120] if title.strip() else "パッケージ画像"
    u = esc(pkg, quote=True)
    return (
        f'<figure style="margin:0.5rem 0;">'
        f'<img src="{u}" alt="{alt}" loading="lazy" '
        'style="max-width:100%;height:auto;" /></figure>'
    )


def _sample_images_section_html(
    item_row: dict[str, Any] | None,
    title: str,
) -> str:
    """商品サンプル画像（sample_images のみ）。"""
    if not item_row:
        return ""
    gallery = _sample_gallery_html(item_row, title)
    if not gallery:
        return ""
    return gallery


def _affiliate_cta_section_html(
    portal_url: str,
    *,
    affiliate_url: str = "",
    item_row: dict[str, Any] | None = None,
    campaigns: list | None = None,
) -> str:
    """アフィリエイト誘導（価格・キャンペーン・目立つ CTA ボタン）。"""
    buy_href = _item_str(affiliate_url)
    if not buy_href and item_row:
        buy_href = _item_str(item_row.get("affiliate_url")) or _item_str(
            item_row.get("item_url")
        )
    portal_href = portal_url.strip()

    buttons: list[str] = []
    if portal_href:
        buttons.append(
            _cta_button_html(
                portal_href,
                "▶ ポータルで作品詳細・関連作・ランキングを見る（PR）",
                primary=True,
            )
        )
    if buy_href and buy_href != portal_href:
        buttons.append(
            _cta_button_html(
                buy_href, "公式サイトで購入・詳細はこちら（PR）", primary=False
            )
        )
    elif buy_href and not portal_href:
        buttons.append(
            _cta_button_html(
                buy_href, "▶ 公式ページで詳細・購入はこちら（PR）", primary=True
            )
        )
    if not buttons:
        return ""

    inner: list[str] = []
    price_block = _price_promo_html(item_row)
    if price_block:
        inner.append(price_block)
    promo = _campaigns_promo_html(campaigns)
    if promo:
        inner.append(promo)
    inner.extend(buttons)
    inner.append(
        '<p style="margin:0.75rem 0 0;font-size:0.8em;color:#666;">'
        "※価格・キャンペーン内容は変更・終了する場合があります。最新情報は各ボタン先でご確認ください。"
        "</p>"
    )
    box = (
        '<div class="ld-aff-cta" style="margin:1.75rem 0;padding:1.25rem 1rem;'
        'border:2px solid #c62828;border-radius:10px;background:linear-gradient(180deg,#fffafa 0%,#fff5f5 100%);">'
        '<h2 style="margin:0 0 1rem;padding:0;font-size:1.2em;color:#b71c1c;text-align:center;">'
        "🛒 ポータルでチェック・お得情報はこちら（PR）</h2>"
        + "".join(inner)
        + "</div>"
    )
    return box


def _premium_promo_section_html(
    *,
    account_id: str | None = None,
    portal_site: str | None = None,
) -> str:
    """作品 CTA とは別枠のプレミアム宣伝（アフィリエイト URL があるときのみ）。"""
    from config.blog_settings import resolve_premium_promo

    promo = resolve_premium_promo(account_id=account_id, site=portal_site)
    if not promo:
        return ""

    href = (promo.get("affiliate_url") or "").strip()
    if not href:
        return ""

    heading = (promo.get("heading") or "プレミアムのご案内（PR）").strip()
    blurb = (promo.get("blurb") or "").strip()
    cta_label = (
        promo.get("cta_label") or "▶ プレミアムの詳細・お申し込みはこちら（PR）"
    ).strip()

    inner: list[str] = []
    if blurb:
        inner.append(
            '<p style="margin:0 0 1rem;line-height:1.7;color:#333;">'
            f"{html_module.escape(blurb)}"
            "</p>"
        )
    inner.append(_cta_button_html(href, cta_label, primary=True))
    inner.append(
        '<p style="margin:0.75rem 0 0;font-size:0.8em;color:#666;">'
        "※本枠は広告・アフィリエイト（PR）です。料金・特典は変更される場合があります。"
        "</p>"
    )
    return (
        '<div class="ld-premium-promo" style="margin:1.75rem 0;padding:1.25rem 1rem;'
        'border:2px solid #1565c0;border-radius:10px;'
        'background:linear-gradient(180deg,#f5f9ff 0%,#eef5ff 100%);">'
        '<h2 style="margin:0 0 1rem;padding:0;font-size:1.2em;color:#0d47a1;text-align:center;">'
        f"{html_module.escape(heading)}</h2>"
        + "".join(inner)
        + "</div>"
    )


def _review_fallback_text(
    title: str,
    *,
    comment: str = "",
    summary: str = "",
    point: str = "",
) -> str:
    """digest が無いとき、auto_comment / summary / point から筆者レビュー相当を組み立てる。"""
    chunks: list[str] = []
    for text in (comment, summary, point):
        t = (text or "").strip()
        if t and _norm_title_for_dedupe(t) != _norm_title_for_dedupe(title):
            chunks.append(t)
    return "\n\n".join(chunks)


def _build_digest_sample_affiliate_body(
    *,
    title: str,
    twitter_text: str,
    affiliate_url: str,
    portal_url: str,
    image_large_url: str,
    image_small_url: str = "",
    item_row: dict[str, Any] | None,
    ai_review_row: dict[str, Any] | None,
    review_fallback: str = "",
    campaigns: list | None = None,
    account_id: str | None = None,
    portal_site: str | None = None,
) -> str:
    """本文コア: ①筆者レビュー → 立ち読み → ②パッケージ → サンプル動画(FANZA) → ③画像 → ④CTA → ⑤プレミアム。"""
    if campaigns is None and item_row:
        raw_c = item_row.get("campaign")
        campaigns = raw_c if isinstance(raw_c, list) else []
    parts: list[str] = []
    digest_raw = _digest_raw_from_ai_row(ai_review_row) or (review_fallback or "").strip()
    author = _digest_author_review_html(digest_raw)
    if author:
        parts.append(author)
    else:
        for block in _twitter_blocks_without_title_echo(twitter_text, title):
            inner = html_module.escape(block).replace("\n", "<br />\n")
            parts.append(f"<p>{inner}</p>")
    tachiyomi = _tachiyomi_section_html(item_row)
    if tachiyomi:
        parts.append(tachiyomi)
    package = _package_image_section_html(
        title,
        image_large_url=image_large_url,
        image_small_url=image_small_url,
        item_row=item_row,
    )
    if package:
        parts.append(package)
    sample_movie = _sample_movie_section_html(item_row, title)
    if sample_movie:
        parts.append(sample_movie)
    sample = _sample_images_section_html(item_row, title)
    if sample:
        parts.append(sample)
    affiliate = _affiliate_cta_section_html(
        portal_url,
        affiliate_url=affiliate_url,
        item_row=item_row,
        campaigns=campaigns,
    )
    if affiliate:
        parts.append(affiliate)
    premium = _premium_promo_section_html(
        account_id=account_id,
        portal_site=portal_site,
    )
    if premium:
        parts.append(premium)
    return "\n".join(parts)


def _norm_title_for_dedupe(s: str) -> str:
    """全角半角差・連続空白のゆらぎを吸収してタイトル同定に使う。"""
    t = unicodedata.normalize("NFKC", (s or "").strip())
    return " ".join(t.split())


def _twitter_blocks_without_title_echo(twitter_text: str, headline: str) -> list[str]:
    """記事タイトル欄と同じ文言のブロックは本文から省く（Atom の title と二重にならない）。"""
    h = _norm_title_for_dedupe(headline)
    if not h:
        return [b.strip() for b in twitter_text.split("\n\n") if b.strip()]
    out: list[str] = []
    for b in twitter_text.split("\n\n"):
        p = b.strip()
        if not p:
            continue
        if _norm_title_for_dedupe(p) == h:
            continue
        out.append(p)
    return out


def _build_simple_livedoor_html(
    *,
    title: str,
    twitter_text: str,
    affiliate_url: str,
    portal_url: str,
    image_large_url: str,
    image_small_url: str = "",
    item_row: dict[str, Any] | None,
    ai_review_row: dict[str, Any] | None,
    campaigns: list | None = None,
    account_id: str | None = None,
    portal_site: str | None = None,
) -> str:
    # タイトルは Atom <title> で既に表示されるため本文では繰り返さない
    return _build_digest_sample_affiliate_body(
        title=title,
        twitter_text=twitter_text,
        affiliate_url=affiliate_url,
        portal_url=portal_url,
        image_large_url=image_large_url,
        image_small_url=image_small_url,
        item_row=item_row,
        ai_review_row=ai_review_row,
        campaigns=campaigns,
        account_id=account_id,
        portal_site=portal_site,
    )


def _build_popular_livedoor_html(
    *,
    title: str,
    twitter_text: str,
    affiliate_url: str,
    portal_url: str,
    image_large_url: str,
    image_small_url: str = "",
    summary: str,
    point: str,
    comment: str,
    item_row: dict[str, Any] | None,
    ai_review_row: dict[str, Any] | None,
    campaigns: list | None = None,
    account_id: str | None = None,
    portal_site: str | None = None,
) -> str:
    """digest_raw 筆者レビュー → パッケージ画像 → サンプル画像 → アフィリエイト（PR 注記付き）。"""
    body = _build_digest_sample_affiliate_body(
        title=title,
        twitter_text=twitter_text,
        affiliate_url=affiliate_url,
        portal_url=portal_url,
        image_large_url=image_large_url,
        image_small_url=image_small_url,
        item_row=item_row,
        ai_review_row=ai_review_row,
        review_fallback=_review_fallback_text(
            title, comment=comment, summary=summary, point=point
        ),
        campaigns=campaigns,
        account_id=account_id,
        portal_site=portal_site,
    )
    return "\n".join(
        [
            '<article class="ld-aff-post">',
            body,
            "<p><small>※本記事には広告・アフィリエイト（PR）リンクが含まれる場合があります。"
            "</small></p>",
            "</article>",
        ]
    )


def build_livedoor_blog_html(
    *,
    title: str,
    twitter_text: str,
    affiliate_url: str,
    portal_url: str,
    image_large_url: str = "",
    image_small_url: str = "",
    summary: str = "",
    point: str = "",
    comment: str = "",
    campaigns: list | None = None,
    article_style: str | None = None,
    item_row: dict[str, Any] | None = None,
    ai_review_row: dict[str, Any] | None = None,
    account_id: str | None = None,
    portal_site: str | None = None,
) -> str:
    """item_row / ai_review_row に DB 行を渡すと、作品スペックと AI レビュー要約を本文に展開する。"""
    style = _article_style(article_style)
    if style == "popular":
        return _build_popular_livedoor_html(
            title=title,
            twitter_text=twitter_text,
            affiliate_url=affiliate_url,
            portal_url=portal_url,
            image_large_url=image_large_url,
            image_small_url=image_small_url,
            summary=summary,
            point=point,
            comment=comment,
            item_row=item_row,
            ai_review_row=ai_review_row,
            campaigns=campaigns,
            account_id=account_id,
            portal_site=portal_site,
        )
    return _build_simple_livedoor_html(
        title=title,
        twitter_text=twitter_text,
        affiliate_url=affiliate_url,
        portal_url=portal_url,
        image_large_url=image_large_url,
        image_small_url=image_small_url,
        item_row=item_row,
        ai_review_row=ai_review_row,
        campaigns=campaigns,
        account_id=account_id,
        portal_site=portal_site,
    )


def _atompub_collection_post_url(blog_name: str) -> str:
    tpl = os.environ.get(
        "LIVEDOOR_ATOMPUB_COLLECTION_TMPL", _DEFAULT_ATOMPUB_COLLECTION_TMPL
    ).strip()
    return tpl.format(blog_name=blog_name)


def _prepare_atompub_title(title: str, *, fallback: str = "") -> str:
    t = _fit_atompub_title(title)
    if t:
        return t
    fb = (fallback or "").strip()
    if fb:
        logger.warning("AtomPub タイトルが空のためフォールバックを使用: %s", fb[:80])
        return _fit_atompub_title(fb)
    logger.warning("AtomPub タイトルが空のため既定タイトルを使用します")
    return "おすすめ作品レビュー"


def _prepare_atompub_body_html(body_html: str) -> str:
    if (body_html or "").strip():
        return body_html
    logger.warning("AtomPub 本文が空のためプレースホルダー HTML を付与します")
    return _ATOMPUB_BODY_PLACEHOLDER


def _build_atom_entry_xml(title: str, body_html: str, draft: bool) -> bytes:
    t = xml_escape(title)
    body_safe = body_html.replace("]]>", "]]]]><![CDATA[>")
    draft_xml = ""
    if draft:
        draft_xml = "<app:control><app:draft>yes</app:draft></app:control>"
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:app="http://www.w3.org/2007/app">
<title>{t}</title>
<content type="html"><![CDATA[{body_safe}]]></content>
{draft_xml}
</entry>
"""
    return xml.encode("utf-8")


def _post_atompub(
    title: str, body_html: str, *, title_fallback: str = ""
) -> None:
    blog_name = os.environ["LIVEDOOR_BLOG_NAME"].strip()
    livedoor_id = os.environ["LIVEDOOR_ID"].strip()
    basic_user = os.environ.get("LIVEDOOR_ATOMPUB_BASIC_USER", "").strip() or livedoor_id
    api_key = os.environ["LIVEDOOR_ATOMPUB_PASSWORD"].strip()
    draft = os.environ.get("LIVEDOOR_ATOMPUB_DRAFT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    safe_title = _prepare_atompub_title(title, fallback=title_fallback)
    safe_body = _prepare_atompub_body_html(body_html)
    url = _atompub_collection_post_url(blog_name)
    payload = _build_atom_entry_xml(safe_title, safe_body, draft=draft)
    headers = {"Content-Type": "application/atom+xml;type=entry"}
    logger.info("Livedoor AtomPub 投稿: %s", url)
    r = requests.post(
        url,
        data=payload,
        headers=headers,
        auth=(basic_user, api_key),
        timeout=120,
    )
    if not r.ok:
        logger.error("Livedoor AtomPub 応答: %s %s", r.status_code, r.text[:2000])
        if r.status_code == 401:
            logger.error(
                "AtomPub 401: パスワードは「ブログ設定 > その他 > API Key」の "
                "AtomPub用パスワード（ログイン用パスワードではない）か確認してください。"
                "ユーザー名は公式ではライブドアIDです。401 が続く場合は "
                "LIVEDOOR_ATOMPUB_BASIC_USER に blog_id（例: %s）を設定して試してください。",
                blog_name,
            )
        elif r.status_code == 400:
            logger.error(
                "AtomPub 400: 送信 title=%r（%d 文字）body=%d 文字。"
                " 空タイトル・空本文・タイトル超過（%d 文字上限）・XML 不正が典型原因です。"
                " title_fallback=%r",
                safe_title[:80],
                len(safe_title),
                len(safe_body),
                _ATOMPUB_TITLE_MAX_CHARS,
                (title_fallback or "")[:80],
            )
    r.raise_for_status()


def _fill_first_visible(
    page, selectors: tuple[str, ...], value: str, *, is_html: bool
) -> bool:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.count() == 0:
                continue
            loc.wait_for(state="visible", timeout=8000)
            loc.fill(value)
            return True
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    if is_html:
        frames = page.locator("iframe")
        n = frames.count()
        for i in range(n):
            frame = frames.nth(i).content_frame()
            if frame is None:
                continue
            for body_sel in ("#tinymce", "body[contenteditable='true']"):
                t = frame.locator(body_sel).first
                try:
                    if t.count() == 0:
                        continue
                    t.wait_for(state="visible", timeout=5000)
                    t.evaluate(
                        "(el, html) => { el.innerHTML = html; }",
                        value,
                    )
                    return True
                except Exception:
                    continue
    return False


def _post_playwright(title: str, body_html: str) -> None:
    from playwright.sync_api import sync_playwright

    user = os.environ["LIVEDOOR_ID"].strip()
    password = os.environ["LIVEDOOR_PASSWORD"].strip()
    entry_url = os.environ["LIVEDOOR_NEW_ENTRY_URL"].strip()
    headless = os.environ.get("LIVEDOOR_PLAYWRIGHT_HEADLESS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    title_sel = os.environ.get("LIVEDOOR_TITLE_SELECTOR", "").strip()
    body_sel = os.environ.get("LIVEDOOR_BODY_SELECTOR", "").strip()
    title_chain = (title_sel,) if title_sel else _DEFAULT_TITLE_SELECTORS
    body_chain = (body_sel,) if body_sel else _DEFAULT_BODY_SELECTORS

    logger.info("Livedoor Playwright ログイン: %s", LIVEDOOR_LOGIN_URL)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(LIVEDOOR_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            page.fill("#livedoor_id", user)
            page.fill("#password", password)
            page.click("#submit")
            page.wait_for_load_state("networkidle", timeout=120000)

            page.goto(entry_url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(2500)

            if not _fill_first_visible(page, title_chain, title, is_html=False):
                raise RuntimeError(
                    "タイトル欄が見つかりません。"
                    "LIVEDOOR_TITLE_SELECTOR で CSS セレクタを指定してください。"
                )
            if not _fill_first_visible(page, body_chain, body_html, is_html=True):
                raise RuntimeError(
                    "本文欄が見つかりません。"
                    "LIVEDOOR_BODY_SELECTOR で textarea 等を指定するか、"
                    "リッチテキストの iframe 構造を確認してください。"
                )

            clicked = False
            for label in ("公開する", "投稿する", "公開", "投稿", "下書き保存"):
                btn = page.get_by_role("button", name=label, exact=True)
                if btn.count() > 0:
                    try:
                        btn.first.click(timeout=8000)
                        clicked = True
                        break
                    except Exception:
                        continue
            if not clicked:
                sub = page.locator(
                    'input[type="submit"], button[type="submit"]'
                ).first
                if sub.count():
                    sub.click(timeout=8000)
                    clicked = True
            if not clicked:
                raise RuntimeError("投稿ボタンが見つかりません。")

            page.wait_for_load_state("networkidle", timeout=120000)
            logger.info("Livedoor Playwright 投稿フロー完了: %s", title)
        finally:
            browser.close()


def post_to_livedoor_blog(
    title: str, body_html: str, *, title_fallback: str = ""
) -> None:
    if not is_livedoor_blog_enabled():
        return
    method = _post_method()
    if method == "playwright":
        _post_playwright(title, body_html)
        return
    if method != "atompub":
        raise ValueError(
            f"不明な LIVEDOOR_POST_METHOD: {method!r}（atompub または playwright）"
        )
    _post_atompub(title, body_html, title_fallback=title_fallback)
