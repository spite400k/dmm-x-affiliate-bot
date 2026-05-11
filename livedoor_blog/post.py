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
  LIVEDOOR_ARTICLE_STYLE=simple（既定）…従来のフラットな段落。
  LIVEDOOR_ARTICLE_STYLE=popular …リード・h2 見出し・ヒーロー画像・末尾の
    購入案内リストなど、読みやすい長文記事風（人気ブログの一般的な構成を参考）。
  build_livedoor_blog_html(item_row=…) に trn_dmm_items 相当の dict を渡すと、
    ジャンル・出演・価格・スペック表・サンプル画像・立ち読みリンクなどを本文に展開する。
  ai_review_row=… に dmm_ai_review_summaries 相当を渡すと、レビュー要旨・AIスコア・読者像・注意点を追記する。
"""

from __future__ import annotations

import html as html_module
import json
import logging
import os
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import requests

logger = logging.getLogger(__name__)

LIVEDOOR_LOGIN_URL = "https://livedoor.blogcms.jp/member/"
# 記事コレクション POST 先（公式: …/atompub/{blog_name}/article）。末尾なしは 400 Unknown endpoint になる
_DEFAULT_ATOMPUB_COLLECTION_TMPL = "https://livedoor.blogcms.jp/atompub/{blog_name}/article"

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


def _format_price_yen(n: object) -> str:
    if n is None:
        return ""
    try:
        return f"¥{int(n):,}"
    except (TypeError, ValueError):
        return ""


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
        clauses.append(f"{service} の {floor} 向け配信コンテンツ")
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
    price = _format_price_yen(item.get("price"))
    lp = _format_price_yen(item.get("list_price"))
    if price:
        rows.append(("価格", f"{price}" + (f"（定価 {lp}）" if lp and lp != price else "")))
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
        parts.append("<h2>サンプル画像</h2>")
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


def _article_style(article_style: str | None) -> str:
    raw = (
        article_style
        if article_style is not None
        else os.environ.get("LIVEDOOR_ARTICLE_STYLE", "simple")
    ).strip().lower()
    return raw if raw in ("simple", "popular") else "simple"


def _build_simple_livedoor_html(
    *,
    title: str,
    twitter_text: str,
    affiliate_url: str,
    portal_url: str,
    image_large_url: str,
    item_row: dict[str, Any] | None,
    ai_review_row: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    parts.append(f"<h1>{html_module.escape(title)}</h1>")
    if image_large_url.strip():
        u = html_module.escape(image_large_url.strip(), quote=True)
        parts.append(f'<p><img src="{u}" alt="" loading="lazy" /></p>')
    for block in twitter_text.split("\n\n"):
        p = block.strip()
        if not p:
            continue
        inner = html_module.escape(p).replace("\n", "<br />\n")
        parts.append(f"<p>{inner}</p>")
    rich = _merged_rich_sections_html(item_row, ai_review_row, title)
    if rich:
        parts.append(rich)
    if portal_url.strip():
        u = html_module.escape(portal_url.strip(), quote=True)
        parts.append(
            f'<p><a href="{u}" rel="nofollow sponsored">ポータルで詳細を見る（PR）</a></p>'
        )
    if affiliate_url.strip():
        u = html_module.escape(affiliate_url.strip(), quote=True)
        parts.append(
            f'<p><a href="{u}" rel="nofollow sponsored">公式サイト・購入はこちら（PR）</a></p>'
        )
    tu = _item_str(item_row.get("tachiyomi_affiliate_url")) if item_row else ""
    if not tu and item_row:
        tu = _item_str(item_row.get("tachiyomi_url"))
    if tu:
        u = html_module.escape(tu, quote=True)
        parts.append(
            f'<p><a href="{u}" rel="nofollow sponsored">立ち読みはこちら（PR）</a></p>'
        )
    return "\n".join(parts)


def _build_popular_livedoor_html(
    *,
    title: str,
    twitter_text: str,
    affiliate_url: str,
    portal_url: str,
    image_large_url: str,
    summary: str,
    point: str,
    comment: str,
    item_row: dict[str, Any] | None,
    ai_review_row: dict[str, Any] | None,
) -> str:
    """長文レビュー風＋末尾に公式誘導ブロック（PR）。"""
    esc = html_module.escape
    blocks = [b.strip() for b in twitter_text.split("\n\n") if b.strip()]
    parts: list[str] = []
    parts.append('<article class="ld-aff-post">')
    parts.append(f"<h1>{esc(title)}</h1>")
    if image_large_url.strip():
        u = esc(image_large_url.strip(), quote=True)
        parts.append(
            f'<figure class="hero"><img src="{u}" alt="{esc(title)}" loading="lazy" /></figure>'
        )
    lead = (comment or "").strip()
    if lead:
        inner = esc(lead).replace("\n", "<br />\n")
        parts.append(
            '<p class="lead" style="font-size:105%;line-height:1.75;">'
            f"<strong>{inner}</strong></p>"
        )
    if summary.strip():
        parts.append("<h2>概要・あらすじ</h2>")
        parts.append("<p>" + esc(summary.strip()).replace("\n", "<br />\n") + "</p>")
    if point.strip():
        parts.append("<h2>注目ポイント・推しどころ</h2>")
        parts.append("<p>" + esc(point.strip()).replace("\n", "<br />\n") + "</p>")
    rich = _merged_rich_sections_html(item_row, ai_review_row, title)
    if rich:
        parts.append(rich)
    seen: set[str] = {title.strip()}
    if lead:
        seen.add(lead)
    if summary.strip():
        seen.add(summary.strip())
    if point.strip():
        seen.add(point.strip())
    if item_row:
        for np in _narrative_paragraphs_from_item(item_row, title):
            seen.add(np)
    if ai_review_row:
        ad = _item_str(ai_review_row.get("review_digest"))
        if ad:
            seen.add(ad)
        ast = _item_str(ai_review_row.get("summary_text"))
        if ast:
            seen.add(ast)
    extra = [b for b in blocks if b not in seen]
    if extra:
        parts.append("<h2>作品紹介・お得情報</h2>")
        for b in extra:
            parts.append("<p>" + esc(b).replace("\n", "<br />\n") + "</p>")
    tachi_li = _tachiyomi_link_html(item_row) if item_row else ""
    if portal_url.strip() or affiliate_url.strip() or tachi_li:
        parts.append("<h2>詳細・購入のご案内（PR）</h2>")
        parts.append("<ul>")
        if portal_url.strip():
            u = esc(portal_url.strip(), quote=True)
            parts.append(
                f'<li><a href="{u}" rel="nofollow sponsored">'
                "ポータルで内容チェック・関連作品を見る</a></li>"
            )
        if affiliate_url.strip():
            u = esc(affiliate_url.strip(), quote=True)
            parts.append(
                f'<li><a href="{u}" rel="nofollow sponsored">'
                "公式ページの詳細・購入はこちら</a></li>"
            )
        if tachi_li:
            parts.append(tachi_li)
        parts.append("</ul>")
    parts.append(
        "<p><small>※本記事には広告・アフィリエイト（PR）リンクが含まれる場合があります。"
        "</small></p>"
    )
    parts.append("</article>")
    return "\n".join(parts)


def build_livedoor_blog_html(
    *,
    title: str,
    twitter_text: str,
    affiliate_url: str,
    portal_url: str,
    image_large_url: str = "",
    summary: str = "",
    point: str = "",
    comment: str = "",
    article_style: str | None = None,
    item_row: dict[str, Any] | None = None,
    ai_review_row: dict[str, Any] | None = None,
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
            summary=summary,
            point=point,
            comment=comment,
            item_row=item_row,
            ai_review_row=ai_review_row,
        )
    return _build_simple_livedoor_html(
        title=title,
        twitter_text=twitter_text,
        affiliate_url=affiliate_url,
        portal_url=portal_url,
        image_large_url=image_large_url,
        item_row=item_row,
        ai_review_row=ai_review_row,
    )


def _atompub_collection_post_url(blog_name: str) -> str:
    tpl = os.environ.get(
        "LIVEDOOR_ATOMPUB_COLLECTION_TMPL", _DEFAULT_ATOMPUB_COLLECTION_TMPL
    ).strip()
    return tpl.format(blog_name=blog_name)


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


def _post_atompub(title: str, body_html: str) -> None:
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
    url = _atompub_collection_post_url(blog_name)
    payload = _build_atom_entry_xml(title, body_html, draft=draft)
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


def post_to_livedoor_blog(title: str, body_html: str) -> None:
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
    _post_atompub(title, body_html)
