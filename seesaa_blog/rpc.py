"""Seesaa XML-RPC クライアント（エンドポイントフォールバック・User-Agent）。"""

from __future__ import annotations

import logging
import os
import xmlrpc.client
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

DEFAULT_SEESAA_XMLRPC_URL = "https://blog.seesaa.jp/rpc"
SEESAA_XMLRPC_FALLBACK_URLS = (
    "https://blog.seesaa.jp/rpc",
    "https://ssl.seesaa.jp/blog/rpc",
)

T = TypeVar("T")


class SeesaaXmlRpcTransport(xmlrpc.client.SafeTransport):
    """User-Agent 付き HTTPS トランスポート。"""

    def __init__(self, user_agent: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._user_agent = (
            user_agent
            or os.environ.get("SEESAA_XMLRPC_USER_AGENT", "").strip()
            or (
                "Mozilla/5.0 (compatible; dmm-x-affiliate-bot/1.0; "
                "+https://github.com/)"
            )
        )

    def send_headers(self, connection, headers) -> None:
        super().send_headers(connection, headers)
        connection.putheader("User-Agent", self._user_agent)
        connection.putheader("Accept", "text/xml")


def normalize_rpc_url(url: str) -> str:
    """末尾スラッシュ等を整える（…/rpc/ は 403 になりやすい）。"""
    u = str(url or "").strip().rstrip("/")
    if u.endswith("/rpc/"):
        return u[:-1]
    return u


def rpc_endpoint_candidates(primary: str) -> list[str]:
    """優先 URL と既知のフォールバックを重複なく返す。"""
    seen: set[str] = set()
    out: list[str] = []
    for u in (primary, *SEESAA_XMLRPC_FALLBACK_URLS):
        n = normalize_rpc_url(u)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def is_seesaa_access_denied(exc: BaseException) -> bool:
    """クラウド IP ブロック等で 403/401 になるケース。"""
    if isinstance(exc, xmlrpc.client.ProtocolError):
        return exc.errcode in (401, 403)
    low = str(exc).lower()
    return "403 forbidden" in low or (
        "forbidden" in low and "protocolerror" in low
    )


def seesaa_server_proxy(url: str) -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy(
        normalize_rpc_url(url),
        transport=SeesaaXmlRpcTransport(),
        allow_none=True,
    )


def seesaa_xmlrpc_call(
    primary_url: str,
    fn: Callable[[xmlrpc.client.ServerProxy], T],
) -> T:
    """複数エンドポイントを順に試す。403 は次の URL へ。"""
    last: BaseException | None = None
    for url in rpc_endpoint_candidates(primary_url):
        try:
            logger.debug("Seesaa XML-RPC 試行: %s", url)
            return fn(seesaa_server_proxy(url))
        except xmlrpc.client.ProtocolError as e:
            last = e
            if e.errcode in (401, 403):
                logger.warning(
                    "Seesaa XML-RPC HTTP %s @ %s — 別エンドポイントを試します",
                    e.errcode,
                    url,
                )
                continue
            raise
    if last is not None:
        raise last
    raise RuntimeError("Seesaa XML-RPC: 試行するエンドポイントがありません")
