"""Tests for SnapTradeService error wrapping around the commercial SDK."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from snaptrade_client.exceptions import ApiException

from app.integrations.snaptrade.client import (
    SnapTradeError,
    SnapTradeService,
    SnapTradeUserCredentials,
)


def _service_with_backend() -> tuple[SnapTradeService, MagicMock]:
    settings = MagicMock()
    settings.snaptrade_client_id = "client-id"
    settings.snaptrade_consumer_key = "consumer-key"
    service = SnapTradeService(
        settings,
        credentials=SnapTradeUserCredentials(
            snaptrade_user_id="user-1", user_secret="secret"
        ),
    )
    backend = MagicMock()
    service._backend = backend
    return service, backend


def _api_exception_401_1083() -> ApiException:
    exc = ApiException(status=401, reason="Unauthorized")
    exc.body = {
        "detail": "Invalid userID or userSecret provided",
        "status_code": 401,
        "code": "1083",
    }
    return exc


def test_list_connections_wraps_api_exception_with_code():
    # The SDK raises ApiException on 4xx before any body reaches _require_ok;
    # it must surface as SnapTradeError so callers can degrade gracefully.
    service, backend = _service_with_backend()
    backend.list_connections.side_effect = _api_exception_401_1083()

    with pytest.raises(SnapTradeError) as ei:
        service.list_connections()

    assert ei.value.status == 401
    assert ei.value.code == "1083"
    assert ei.value.stale_user is True


def test_list_accounts_wraps_api_exception():
    service, backend = _service_with_backend()
    backend.list_accounts.side_effect = ApiException(status=500, reason="oops")

    with pytest.raises(SnapTradeError) as ei:
        service.list_accounts()

    assert ei.value.status == 500
    assert ei.value.stale_user is False


def test_error_without_code_is_not_stale():
    assert SnapTradeError("boom", status=401).stale_user is False
