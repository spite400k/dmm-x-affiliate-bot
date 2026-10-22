"""blog_repository: Supabase 制限・欠落テーブルの分岐テスト。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from db import blog_repository as br


class APIError(Exception):
    """postgrest.exceptions.APIError 相当（型名だけ合わせる）。"""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.args = (payload,)
        super().__init__(payload)


def test_is_missing_blog_table_error_pgrst205_dict() -> None:
    assert br._is_missing_blog_table_error(
        APIError({"code": "PGRST205", "message": "missing"})
    )


def test_is_missing_blog_table_error_text() -> None:
    assert br._is_missing_blog_table_error(RuntimeError("Could not find the table x"))
    assert not br._is_missing_blog_table_error(RuntimeError("other"))


def test_is_supabase_service_restricted_error_code_402() -> None:
    assert br._is_supabase_service_restricted_error(
        APIError(
            {
                "message": "JSON could not be generated",
                "code": 402,
                "hint": "Refer to full message for details",
                "details": (
                    'b\'{"message":"Service for this project is restricted due to '
                    "the following violations: exceed_egress_quota. "
                    "The project owner must upgrade their plan or remove spend "
                    "caps to restore service.\"}'"
                ),
            }
        )
    )


def test_is_supabase_service_restricted_error_string_code() -> None:
    assert br._is_supabase_service_restricted_error(
        APIError({"code": "402", "message": "Payment Required"})
    )


def test_is_supabase_service_restricted_error_egress_in_details() -> None:
    assert br._is_supabase_service_restricted_error(
        APIError(
            {
                "code": "XX",
                "message": "",
                "details": "exceed_egress_quota spend caps",
            }
        )
    )


def test_is_supabase_service_restricted_error_restricted_message() -> None:
    assert br._is_supabase_service_restricted_error(
        APIError(
            {
                "code": "XX",
                "message": "Service for this project is restricted",
            }
        )
    )


def test_is_supabase_service_restricted_error_text_fallback() -> None:
    assert br._is_supabase_service_restricted_error(
        RuntimeError("HTTP 402 Payment Required from gateway")
    )
    assert br._is_supabase_service_restricted_error(
        RuntimeError("exceed_egress_quota")
    )
    assert br._is_supabase_service_restricted_error(
        RuntimeError("Service for this project is restricted by policy")
    )
    assert not br._is_supabase_service_restricted_error(RuntimeError("timeout"))


def test_is_supabase_service_restricted_error_apierror_unrelated_falls_through() -> None:
    """dict 分岐に入るが制限キーワード無し → text 判定へ（どちらも不一致）。"""
    assert not br._is_supabase_service_restricted_error(
        APIError({"code": "XX", "message": "unrelated", "hint": "", "details": ""})
    )


def test_is_supabase_service_restricted_error_apierror_non_dict_args() -> None:
    err = APIError({"code": 402})
    err.args = ("not-a-dict",)
    assert not br._is_supabase_service_restricted_error(err)


def test_is_supabase_service_restricted_error_spend_caps_only() -> None:
    assert br._is_supabase_service_restricted_error(
        APIError({"code": "XX", "message": "", "details": "remove spend caps"})
    )


def test_list_enabled_blog_rows_missing_table_returns_empty() -> None:
    with patch.object(br, "init_supabase") as init:
        client = MagicMock()
        init.return_value = client
        (
            client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.execute
        ).side_effect = APIError({"code": "PGRST205"})
        assert br.list_enabled_blog_rows("2", "livedoor") == []


def test_list_enabled_blog_rows_restricted_raises_runtime_error() -> None:
    with patch.object(br, "init_supabase") as init:
        client = MagicMock()
        init.return_value = client
        (
            client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.execute
        ).side_effect = APIError(
            {
                "message": "JSON could not be generated",
                "code": 402,
                "hint": "Refer to full message for details",
                "details": "exceed_egress_quota",
            }
        )
        with pytest.raises(RuntimeError, match="exceed_egress_quota|制限"):
            br.list_enabled_blog_rows("2", "livedoor")


def test_list_enabled_blog_rows_other_error_reraises() -> None:
    with patch.object(br, "init_supabase") as init:
        client = MagicMock()
        init.return_value = client
        (
            client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.execute
        ).side_effect = RuntimeError("network down")
        with pytest.raises(RuntimeError, match="network down"):
            br.list_enabled_blog_rows("2", "livedoor")


def test_list_enabled_blog_rows_success() -> None:
    with patch.object(br, "init_supabase") as init:
        client = MagicMock()
        init.return_value = client
        (
            client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.execute
        ).return_value = MagicMock(data=[{"blog_id": "a"}])
        assert br.list_enabled_blog_rows("2", "livedoor") == [{"blog_id": "a"}]


def test_list_enabled_blog_rows_success_none_data() -> None:
    with patch.object(br, "init_supabase") as init:
        client = MagicMock()
        init.return_value = client
        (
            client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.execute
        ).return_value = MagicMock(data=None)
        assert br.list_enabled_blog_rows("2", "livedoor") == []


def test_supabase_restricted_runtime_error_message() -> None:
    err = br._supabase_restricted_runtime_error(RuntimeError("detail-x"))
    assert "402" in str(err) or "制限" in str(err)
    assert "detail-x" in str(err)
