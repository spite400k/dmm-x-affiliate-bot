from datetime import datetime, timezone
from db.supabase_client import init_supabase



def get_next_post(service,floor,account_id):
    supabase = init_supabase(account_id)

    res = supabase.table("trn_dmm_items").select("*").eq("is_posted", False).eq("service", service).eq("floor", floor).gt("review_count",0).order("review_count", desc=True).limit(1).execute()
    return res.data[0] if res.data else None

def mark_post_as_posted(post_id: str,account_id):
    # 現在時刻（UTC）
    now = datetime.now(timezone.utc).isoformat()  # ← ISO 8601 文字列に変換

    supabase = init_supabase(account_id)
    supabase.table("trn_dmm_items") \
        .update({
            "is_posted": True,
            "posted_at": now
        }) \
        .eq("id", post_id) \
        .execute()