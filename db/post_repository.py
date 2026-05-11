from datetime import datetime, timezone

from db.supabase_client import init_supabase

_BATCH = 50
_STATUS_TABLE = "trn_dmm_item_blog_post_status"


def get_next_post(service: str, floor: str, account_id: str, blog_key: str | None = None):
    """未投稿の作品を1件返す。

    blog_key 省略時: trn_dmm_items.is_posted（従来、X / FC2 キュー用）。
    blog_key 指定時: trn_dmm_item_blog_post_status でそのブログの投稿済みを判定
    （ライブドアは livedoor:{blog_id} を渡す想定）。
    """
    supabase = init_supabase(account_id)
    if blog_key is None:
        res = (
            supabase.table("trn_dmm_items")
            .select("*")
            .eq("is_posted", False)
            .eq("service", service)
            .eq("floor", floor)
            .gt("review_count", 0)
            .order("review_count", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    offset = 0
    while True:
        res = (
            supabase.table("trn_dmm_items")
            .select("*")
            .eq("service", service)
            .eq("floor", floor)
            .gt("review_count", 0)
            .order("review_count", desc=True)
            .range(offset, offset + _BATCH - 1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return None
        ids = [r["id"] for r in rows]
        posted = (
            supabase.table(_STATUS_TABLE)
            .select("dmm_item_id")
            .eq("blog_key", blog_key)
            .eq("is_posted", True)
            .in_("dmm_item_id", ids)
            .execute()
        )
        posted_set = {r["dmm_item_id"] for r in (posted.data or [])}
        for row in rows:
            if row["id"] not in posted_set:
                return row
        offset += _BATCH


def _mark_item_removed_from_queue(
    post_id: str, account_id: str, blog_key: str | None = None
) -> None:
    """キューから除外する（成功・失敗で共通）。

    blog_key 省略時: trn_dmm_items.is_posted を立てる。
    blog_key 指定時: trn_dmm_item_blog_post_status を更新／挿入。
    """
    now = datetime.now(timezone.utc).isoformat()
    supabase = init_supabase(account_id)
    if blog_key is None:
        supabase.table("trn_dmm_items").update(
            {"is_posted": True, "posted_at": now}
        ).eq("id", post_id).execute()
        return

    existing = (
        supabase.table(_STATUS_TABLE)
        .select("id")
        .eq("dmm_item_id", post_id)
        .eq("blog_key", blog_key)
        .limit(1)
        .execute()
    )
    if existing.data:
        supabase.table(_STATUS_TABLE).update(
            {"is_posted": True, "posted_at": now, "updated_at": now}
        ).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase.table(_STATUS_TABLE).insert(
            {
                "dmm_item_id": post_id,
                "blog_key": blog_key,
                "is_posted": True,
                "posted_at": now,
                "updated_at": now,
            }
        ).execute()


def mark_post_as_posted(
    post_id: str, account_id: str, blog_key: str | None = None
) -> None:
    """投稿成功時。キューから除外する。"""
    _mark_item_removed_from_queue(post_id, account_id, blog_key=blog_key)


def mark_post_failed_skip_queue(
    post_id: str, account_id: str, blog_key: str | None = None
) -> None:
    """post_full_twitter 失敗時。同一作品の再取得を防ぐためキューから除外する（次回は別作品）。"""
    _mark_item_removed_from_queue(post_id, account_id, blog_key=blog_key)
