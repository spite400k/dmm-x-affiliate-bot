from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

def init_supabase(account: str = "0") -> Client:
    sufix = account.upper()  # "main" → "MAIN"

    url = os.getenv(f"SUPABASE_URL_{sufix}")
    key = os.getenv(f"SUPABASE_KEY_{sufix}")

    if not url or not key:
        raise ValueError(f"Invalid Supabase credentials for account `{account}`")

    return create_client(url, key)
