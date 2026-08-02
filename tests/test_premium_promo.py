"""プレミアム宣伝フッター（site/account 出し分け）のユニットテスト。"""

from __future__ import annotations

import os

import pytest

from config.blog_settings import resolve_premium_promo
from livedoor_blog.post import build_livedoor_blog_html, _premium_promo_section_html


@pytest.fixture(autouse=True)
def _clear_premium_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key in (
            "DMM_PREMIUM_AFFILIATE_URL",
            "FANZA_PREMIUM_AFFILIATE_URL",
        ) or key.startswith("PREMIUM_AFFILIATE_URL_"):
            monkeypatch.delenv(key, raising=False)


def test_resolve_premium_promo_uses_default_url() -> None:
    dmm = resolve_premium_promo(account_id="1", site="dmm")
    assert dmm is not None
    assert dmm["affiliate_url"] == "https://www.dmmportal.jp/dmm-premium"

    fanza = resolve_premium_promo(account_id="2", site="fanza")
    assert fanza is not None
    assert fanza["affiliate_url"] == "https://www.fanzaportal.com/dmm-premium"


def test_resolve_premium_promo_by_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DMM_PREMIUM_AFFILIATE_URL", "https://example.com/dmm-premium")
    monkeypatch.setenv("FANZA_PREMIUM_AFFILIATE_URL", "https://example.com/fanza-premium")

    dmm = resolve_premium_promo(account_id="1", site="dmm")
    assert dmm is not None
    assert dmm["affiliate_url"] == "https://example.com/dmm-premium"
    assert "DMMプレミアム" in dmm["heading"]

    fanza = resolve_premium_promo(account_id="2", site="fanza")
    assert fanza is not None
    assert fanza["affiliate_url"] == "https://example.com/fanza-premium"
    assert "DMMプレミアム" in fanza["heading"]

    mesugaki = resolve_premium_promo(account_id="6", site="fanza")
    assert mesugaki is not None
    assert mesugaki["affiliate_url"] == "https://example.com/fanza-premium"


def test_resolve_premium_promo_account_url_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FANZA_PREMIUM_AFFILIATE_URL", "https://example.com/fanza-default")
    monkeypatch.setenv("PREMIUM_AFFILIATE_URL_6", "https://example.com/mesugaki")

    promo = resolve_premium_promo(account_id="6", site="fanza")
    assert promo is not None
    assert promo["affiliate_url"] == "https://example.com/mesugaki"


def test_premium_section_in_blog_html(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DMM_PREMIUM_AFFILIATE_URL", "https://example.com/dmm-premium")

    html = build_livedoor_blog_html(
        title="テスト作品",
        twitter_text="本文",
        affiliate_url="https://example.com/item",
        portal_url="https://dmmportal.jp/ebook/comic/cid",
        account_id="1",
        portal_site="dmm",
        article_style="simple",
    )
    assert 'class="ld-premium-promo"' in html
    assert "https://example.com/dmm-premium" in html
    assert "DMMプレミアム" in html
    # 作品 CTA の後に独立セクション
    assert html.index("ld-aff-cta") < html.index("ld-premium-promo")


def test_premium_section_absent_when_account_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import blog_settings

    cfg = dict(blog_settings.BLOG_ACCOUNT_SETTINGS["1"])
    cfg["premium_promo_enabled"] = False
    monkeypatch.setitem(blog_settings.BLOG_ACCOUNT_SETTINGS, "1", cfg)
    assert _premium_promo_section_html(account_id="1", portal_site="dmm") == ""
