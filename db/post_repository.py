from datetime import datetime, timezone
from db.supabase_client import supabase

def get_next_post(service,floor):
    res = supabase.table("trn_dmm_items").select("*").eq("is_posted", False).eq("service", service).eq("floor", floor).limit(1).execute()
    return res.data[0] if res.data else None

def mark_post_as_posted(post_id: str):
    # 現在時刻（UTC）
    now = datetime.now(timezone.utc).isoformat()  # ← ISO 8601 文字列に変換

    supabase.table("trn_dmm_items") \
        .update({
            "is_posted": True,
            "posted_at": now
        }) \
        .eq("id", post_id) \
        .execute()