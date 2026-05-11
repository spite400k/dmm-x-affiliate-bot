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
"""

from __future__ import annotations

import html as html_module
import logging
import os
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
    seen: set[str] = {title.strip()}
    if lead:
        seen.add(lead)
    if summary.strip():
        seen.add(summary.strip())
    if point.strip():
        seen.add(point.strip())
    extra = [b for b in blocks if b not in seen]
    if extra:
        parts.append("<h2>作品紹介・お得情報</h2>")
        for b in extra:
            parts.append("<p>" + esc(b).replace("\n", "<br />\n") + "</p>")
    if portal_url.strip() or affiliate_url.strip():
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
) -> str:
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
        )
    return _build_simple_livedoor_html(
        title=title,
        twitter_text=twitter_text,
        affiliate_url=affiliate_url,
        portal_url=portal_url,
        image_large_url=image_large_url,
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
