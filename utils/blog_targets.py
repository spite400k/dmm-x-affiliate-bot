"""ブログ投稿用の service / floor / site を、Python 設定と Supabase マスタから解決する。"""

from __future__ import annotations

from typing import Any

# FANZA / アダルトフロア。Seesaa はアダルト投稿が利用規約 NG。
ADULT_BLOG_FLOORS = frozenset(
    {
        "videoa",
        "videoc",
        "anime",
        "nikkatsu",
        "digital_doujin",
    }
)
ADULT_BLOG_SERVICES = frozenset({"doujin"})


def normalize_portal_site(site: str | None, *, fallback: str = "fanza") -> str:
    """ポータル URL 判定用に site 表記を dmm / fanza に揃える。

    マスタに \"DMM.com\" 等が入っていても dmm 扱いにする。
    """
    s = str(site or "").strip().lower().replace(" ", "")
    if s in ("dmm", "dmm.com", "dmmcom", "www.dmm.com"):
        return "dmm"
    if s in ("fanza",):
        return "fanza"
    if not s:
        fb = str(fallback or "").strip().lower() or "fanza"
        return normalize_portal_site(fb, fallback="fanza")
    return "fanza"


def is_adult_blog_target(
    site: str | None,
    service: str | None = None,
    floor: str | None = None,
) -> bool:
    """FANZA またはアダルト floor/service なら True（Seesaa 投稿禁止判定用）。"""
    site_raw = str(site or "").strip()
    if site_raw and normalize_portal_site(site_raw, fallback="dmm") == "fanza":
        return True
    fl = str(floor or "").strip().lower()
    if fl in ADULT_BLOG_FLOORS:
        return True
    svc = str(service or "").strip().lower()
    return svc in ADULT_BLOG_SERVICES


def is_adult_item_row(item_row: dict[str, Any] | None) -> bool:
    """trn_dmm_items 行がアダルト（FANZA）なら True。"""
    if not item_row:
        return False
    site = str(item_row.get("site") or "").strip()
    service = str(item_row.get("service") or "").strip()
    floor = str(item_row.get("floor") or "").strip()
    if is_adult_blog_target(site, service, floor):
        return True
    site_u = site.upper().replace(" ", "")
    return site_u == "FANZA" or site_u.startswith("FANZA")


def resolve_post_targets(
    acc_cfg: dict[str, Any],
    master: dict[str, str] | None,
) -> list[dict[str, str]]:
    """投稿キュー参照用の (service, floor, site) リストを返す。

    優先順位:
      1. acc_cfg[\"targets\"] が空でなければその各要素（各要素に site があれば優先）
      2. それ以外で master に service と floor があれば 1 件だけ

    site の既定: master[\"site\"] → acc_cfg[\"site\"] → \"fanza\"（いずれもポータル判定前に正規化）
    """
    master = master or {}
    default_site_raw = (
        str(master.get("site") or "").strip()
        or str(acc_cfg.get("site") or "").strip()
        or "fanza"
    )
    default_site = normalize_portal_site(default_site_raw)
    raw = acc_cfg.get("targets") or []
    out: list[dict[str, str]] = []
    if raw:
        for t in raw:
            if not isinstance(t, dict):
                continue
            service = str(t.get("service") or "").strip()
            floor = str(t.get("floor") or "").strip()
            if not service or not floor:
                continue
            site = normalize_portal_site(
                str(t.get("site") or "").strip(),
                fallback=default_site,
            )
            out.append({"service": service, "floor": floor, "site": site})
        return out

    ms = str(master.get("service") or "").strip()
    mf = str(master.get("floor") or "").strip()
    if ms and mf:
        out.append({"service": ms, "floor": mf, "site": default_site})
    return out
