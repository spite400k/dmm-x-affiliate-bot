from db.supabase_client import supabase

def get_next_post():
    res = supabase.table("trn_dmm_items").select("*").eq("is_posted", False).limit(1).execute()
    return res.data[0] if res.data else None

def mark_post_as_posted(post_id: str):
    supabase.table("trn_dmm_items").update({"is_posted": True}).eq("id", post_id).execute()
