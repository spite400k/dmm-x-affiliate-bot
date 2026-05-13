import logging
import os
from typing import Any

from db.supabase_client import init_supabase

logger = logging.getLogger(__name__)

DEFAULT_BLOG_ACCOUNT_TABLE = "mst_blog_accounts"
DEFAULT_FC2_XMLRPC_URL = "http://blog.fc2.com/xmlrpc.php"


def _is_missing_blog_table_error(exc: BaseException) -> bool:
    """PostgREST が未定義テーブルへアクセスしたときの PGRST205 等。"""
    if type(exc).__name__ == "APIError" and exc.args and isinstance(exc.args[0], dict):
        return exc.args[0].get("code") == "PGRST205"
    text = str(exc)
    return "PGRST205" in text or "Could not find the table" in text


def _pick(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _table_name() -> str:
    return os.getenv("BLOG_ACCOUNT_MASTER_TABLE", DEFAULT_BLOG_ACCOUNT_TABLE)


def list_enabled_blog_rows(account_id: str, platform: str) -> list[dict[str, Any]]:
    """enabled=true の行をすべて返す（blog_id 昇順）。

    テーブル未作成（PGRST205）のときは空リストを返す。
    """
    try:
        logger.info(f"account_id: {account_id}, platform: {platform}")
        supabase = init_supabase(account_id)
        res = (
            supabase.table(_table_name())
            .select("*")
            .eq("account_id", account_id)
            .eq("platform", platform)
            .eq("enabled", True)
            .order("blog_id")
            .execute()
        )
    except Exception as e:
        if _is_missing_blog_table_error(e):
            logger.warning(
                "Supabase にテーブル %r が無いためブログマスタ参照をスキップします。"
                " SQL Editor で db/DDL/ddl_mst_blog_accounts.sql を実行してください。詳細: %s",
                _table_name(),
                e,
            )
            return []
        raise
    return list(res.data or [])


def _get_enabled_blog_row(account_id: str, platform: str) -> dict[str, Any] | None:
    """enabled=true の行を最大1件返す（複数行ある場合は先頭）。

    テーブル未作成（PGRST205）のときは None を返す（呼び出し側でエラー終了など）。
    """
    rows = list_enabled_blog_rows(account_id, platform)
    return rows[0] if rows else None


def get_enabled_fc2_blog_config(account_id: str) -> dict[str, str] | None:
    """FC2ブログ投稿用の接続情報をマスタテーブルから取得する。

    必須カラム:
      account_id, platform, enabled, blog_id, username, api_password
    任意カラム:
      blog_key, xmlrpc_url, site, service, floor（後者は targets 未設定時の 1 件指定用）

    BLOG_ACCOUNT_MASTER_TABLE を指定するとテーブル名を変更できる。
    """
    row = _get_enabled_blog_row(account_id, "fc2")
    if not row:
        return None

    blog_id = _pick(row, "blog_id", "fc2_blog_id")
    username = _pick(row, "username", "login_id", "email")
    password = _pick(row, "api_password", "xmlrpc_password", "password")
    if not blog_id or not username or not password:
        return None

    blog_key = _pick(row, "blog_key", "post_key") or f"fc2:{account_id}:{blog_id}"
    xmlrpc_url = _pick(row, "xmlrpc_url", "api_url") or DEFAULT_FC2_XMLRPC_URL
    out: dict[str, str] = {
        "blog_key": blog_key,
        "blog_id": blog_id,
        "username": username,
        "password": password,
        "xmlrpc_url": xmlrpc_url,
    }
    for k in ("site", "service", "floor"):
        v = str(row.get(k) or "").strip()
        if v:
            out[k] = v
    return out


def _livedoor_row_to_config(row: dict[str, Any]) -> dict[str, str] | None:
    """1行分を AtomPub 用フラット dict に変換。必須欠けなら None。"""
    blog_id = _pick(row, "blog_id", "livedoor_blog_name")
    username = _pick(row, "username", "livedoor_id")
    password = _pick(row, "api_password", "atompub_password")
    if not blog_id or not username or not password:
        return None

    status_blog_key = f"livedoor:{blog_id}"
    blog_memo = _pick(row, "blog_memo", "blog_key", "post_key")
    xmlrpc_url = _pick(row, "xmlrpc_url", "api_url")
    basic_user = _pick(row, "atompub_basic_username", "basic_auth_username")
    out: dict[str, str] = {
        "blog_id": blog_id,
        "username": username,
        "api_password": password,
        "blog_key": status_blog_key,
        "blog_memo": blog_memo,
        "xmlrpc_url": xmlrpc_url,
    }
    if basic_user:
        out["atompub_basic_username"] = basic_user
    for k in ("site", "service", "floor"):
        v = str(row.get(k) or "").strip()
        if v:
            out[k] = v
    return out


def list_enabled_livedoor_blog_configs(account_id: str) -> list[dict[str, str]]:
    """platform=livedoor, enabled=true の行をすべて返す（blog_id 昇順）。

    各行に site / service / floor があれば、main_livedoor_atompub がその組み合わせで
    未投稿キューを参照するのに使う。必須列欠けの行はスキップする。
    """
    out: list[dict[str, str]] = []
    for row in list_enabled_blog_rows(account_id, "livedoor"):
        cfg = _livedoor_row_to_config(row)
        if cfg:
            out.append(cfg)
    return out


def get_enabled_livedoor_blog_config(account_id: str) -> dict[str, str] | None:
    """ライブドア AtomPub 用の接続情報をマスタから取得する（有効行が複数あるときは先頭）。

    platform = 'livedoor', enabled = true の行を参照する。
    blog_id は AtomPub のブログ名（/atompub/ と /article の間。例: …/atompub/staff/article なら staff）。

    trn_dmm_item_blog_post_status 用のキーは常に livedoor:{blog_id}（マスタの blog_key 列は参照しない）。
    blog_memo / blog_key / post_key 列は備考（人間可読なブログ名など）のみ。ログ用。

    任意カラム atompub_basic_username: Basic 認証ユーザー名（401 時に blog_id と同じにする等）。
    任意 site, service, floor: マスタ側の既定（config の targets が空のとき 1 件分のキュー指定に使用）。

    複数ブログを使う場合は list_enabled_livedoor_blog_configs を参照。
    """
    rows = list_enabled_livedoor_blog_configs(account_id)
    return rows[0] if rows else None


def apply_livedoor_env_from_config(cfg: dict[str, str]) -> None:
    """livedoor_blog.post が参照する環境変数にマスタの値を流し込む。"""
    os.environ["LIVEDOOR_ID"] = cfg["username"]
    os.environ["LIVEDOOR_ATOMPUB_PASSWORD"] = cfg["api_password"]
    os.environ["LIVEDOOR_BLOG_NAME"] = cfg["blog_id"]
    bu = str(cfg.get("atompub_basic_username") or "").strip()
    if bu:
        os.environ["LIVEDOOR_ATOMPUB_BASIC_USER"] = bu
    else:
        os.environ.pop("LIVEDOOR_ATOMPUB_BASIC_USER", None)
