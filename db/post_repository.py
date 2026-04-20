from datetime import datetime, timezone

from db.supabase_client import init_supabase


def get_next_post(service: str, floor: str, account_id: str):
    supabase = init_supabase(account_id)

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


def _mark_item_removed_from_queue(post_id: str, account_id: str) -> None:
    """is_posted=True にして get_next_post の対象外にする（成功・失敗で共通）。"""
    now = datetime.now(timezone.utc).isoformat()
    supabase = init_supabase(account_id)
    supabase.table("trn_dmm_items").update({"is_posted": True, "posted_at": now}).eq(
        "id", post_id
    ).execute()


def mark_post_as_posted(post_id: str, account_id: str) -> None:
    """投稿成功時。キューから除外する。"""
    _mark_item_removed_from_queue(post_id, account_id)


def mark_post_failed_skip_queue(post_id: str, account_id: str) -> None:
    """post_full_twitter 失敗時。同一作品の再取得を防ぐためキューから除外する（次回は別作品）。"""
    _mark_item_removed_from_queue(post_id, account_id)