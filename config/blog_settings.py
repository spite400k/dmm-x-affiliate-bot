"""ブログ投稿ジョブ用のアカウント設定。

main_livedoor_atompub.py / main_fc2_blog.py / main_seesaa_blog.py が参照する。
ライブドアの portal リンク用に site（dmm / fanza）を持つ。

プレミアム宣伝（記事末尾の独立セクション）:
  site 別の見出し・文言は PREMIUM_PROMO_BY_SITE。
  アフィリエイト URL は環境変数（必須。空ならセクション自体を出さない）:
    DMM_PREMIUM_AFFILIATE_URL / FANZA_PREMIUM_AFFILIATE_URL
  アカウント単位の上書き（任意）:
    PREMIUM_AFFILIATE_URL_{account}  … URL のみ差し替え
    BLOG_ACCOUNT_SETTINGS[account]["premium_promo_enabled"]=False で抑止
    BLOG_ACCOUNT_SETTINGS[account]["premium_promo_site"] で文言側の site を上書き
"""

from __future__ import annotations

import os
from typing import Any

# 互換用（main_livedoor_atompub は mst_blog_accounts の blog_id から livedoor:{blog_id} を使う）
LIVEDOOR_BLOG_POST_KEY = (
    os.environ.get("LIVEDOOR_BLOG_POST_KEY", "livedoor:写真集のおすすめ").strip()
    or "livedoor:写真集のおすすめ"
)

BLOG_ACCOUNT_SETTINGS = {
    "1": {
        "enabled": True,
        "site": "dmm",
        "screen_name": "yuki23675786",
        "targets": [
            {"service": "ebook", "floor": "comic"},
            # {"service": "ebook", "floor": "novel"},
            # {"service": "ebook", "floor": "otherbooks"},
            {"service": "ebook", "floor": "photo"},
        ],
    },
    "2": {
        "enabled": True,
        "site": "fanza",
        "screen_name": "Ren47291",
        "targets": [
            # {"service": "digital", "floor": "anime"},
            {"service": "digital", "floor": "videoa"},
            {"service": "digital", "floor": "videoc"},
            {"service": "ebook", "floor": "comic"},
            {"service": "doujin", "floor": "digital_doujin"},
        ],
    },
    "3": {
        "enabled": False,
        "site": "fanza",
        "screen_name": "Sora36100",
        "targets": [
            # {"service": "doujin", "floor": "digital_doujin"},
            {"service": "digital", "floor": "videoc"},
            # {"service": "ebook", "floor": "comic"},
        ],
    },
    "4": {
        "enabled": False,
        "site": "fanza",
        "screen_name": "AdultSelectLab",
        "targets": [],
    },
    "5": {
        "enabled": False,
        "site": "fanza",
        "screen_name": "fanza_portal_1",
        "targets": [
            # {"service": "digital", "floor": "anime"},
            {"service": "digital", "floor": "videoc"},
            {"service": "ebook", "floor": "comic"},
        ],
    },
    "6": {
        "enabled": True,
        "site": "fanza",
        "screen_name": "Kai4708",
        "targets": [
            {"service": "doujin", "floor": "digital_doujin"},
            {"service": "ebook", "floor": "comic"},
        ],
    },
}

# site（dmm / fanza）ごとのプレミアム宣伝。URL は環境変数 → default_url の順。
PREMIUM_PROMO_BY_SITE: dict[str, dict[str, Any]] = {
    "dmm": {
        "enabled": True,
        "heading": "DMMプレミアムのご案内（PR）",
        "blurb": (
            "月額で動画・読み放題・ポイント特典など、DMMのサービスをまとめてお得に楽しめる"
            "「DMMプレミアム」。初回はポイント付与でお試しもしやすいプランです。"
        ),
        "cta_label": "▶ DMMプレミアムの詳細・お申し込みはこちら（PR）",
        "affiliate_url_env": "DMM_PREMIUM_AFFILIATE_URL",
        "default_url": "https://www.dmmportal.jp/dmm-premium",
    },
    "fanza": {
        "enabled": True,
        "heading": "DMMプレミアムのご案内（PR）",
        "blurb": (
            "月額で動画・読み放題・ポイント特典など、DMM / FANZA の対象サービスを"
            "まとめてお得に楽しめる「DMMプレミアム」。初回はポイント付与でお試しもしやすいプランです。"
        ),
        "cta_label": "▶ DMMプレミアムの詳細・お申し込みはこちら（PR）",
        "affiliate_url_env": "FANZA_PREMIUM_AFFILIATE_URL",
        "default_url": "https://www.fanzaportal.com/dmm-premium",
    },
}


def resolve_premium_promo(
    *,
    account_id: str | None = None,
    site: str | None = None,
) -> dict[str, str] | None:
    """記事末尾に出すプレミアム宣伝の解決結果。出さない場合は None。

    戻り値キー: heading, blurb, cta_label, affiliate_url
    """
    from utils.blog_targets import normalize_portal_site

    acc_cfg: dict[str, Any] = {}
    if account_id:
        acc_cfg = BLOG_ACCOUNT_SETTINGS.get(str(account_id), {}) or {}
        if acc_cfg.get("premium_promo_enabled") is False:
            return None

    site_raw = (
        str(acc_cfg.get("premium_promo_site") or "").strip()
        or str(site or "").strip()
        or str(acc_cfg.get("site") or "").strip()
        or "fanza"
    )
    site_key = normalize_portal_site(site_raw, fallback="fanza")
    base = PREMIUM_PROMO_BY_SITE.get(site_key) or PREMIUM_PROMO_BY_SITE["fanza"]
    if not base.get("enabled", True):
        return None

    url = ""
    if account_id:
        url = os.environ.get(f"PREMIUM_AFFILIATE_URL_{account_id}", "").strip()
    if not url:
        env_name = str(base.get("affiliate_url_env") or "").strip()
        if env_name:
            url = os.environ.get(env_name, "").strip()
    if not url:
        url = str(base.get("default_url") or "").strip()
    if not url:
        return None

    return {
        "heading": str(base.get("heading") or "").strip(),
        "blurb": str(base.get("blurb") or "").strip(),
        "cta_label": str(base.get("cta_label") or "").strip(),
        "affiliate_url": url,
    }
