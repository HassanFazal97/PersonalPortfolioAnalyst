"""Signed HTTP client for SnapTrade Personal API keys.

Personal keys (created via the SnapTrade dashboard SDK flow) are tied to the
account owner at signup. They authenticate with only ``clientId`` +
``consumerKey`` — no ``registerUser``, no ``userId``, no ``userSecret``.

See https://docs.snaptrade.com/docs/authentication-methods
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from base64 import b64encode
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings

BASE_URL = "https://api.snaptrade.com/api/v1"
WEALTHSIMPLE_BROKER = "WEALTHSIMPLETRADE"


class PersonalSnapTradeError(RuntimeError):
    pass


def _is_refresh_unavailable(exc: Exception) -> bool:
    """Real-time plans return 403/1141 — data is already live, refresh is optional."""
    msg = str(exc)
    return "1141" in msg or "Manual refresh not enabled" in msg


def _is_personal_register_error(exc: Exception) -> bool:
    body = str(exc)
    return "1012" in body or "registerUser is not available" in body


def compute_request_signature(
    *, path: str, query: str, consumer_key: str, body: Any | None
) -> str:
    """HMAC-SHA256 signature per SnapTrade request-signatures docs."""
    sig_object = {
        "content": None if body is None or body == {} else body,
        "path": f"/api/v1{path}",
        "query": query,
    }
    sig_content = json.dumps(sig_object, separators=(",", ":"), sort_keys=True)
    digest = hmac.new(
        consumer_key.encode(), sig_content.encode(), hashlib.sha256
    ).digest()
    return b64encode(digest).decode()


class PersonalSnapTradeClient:
    """SnapTrade Personal API key client (no userId / userSecret)."""

    def __init__(self, settings: Settings) -> None:
        if not settings.snaptrade_client_id or not settings.snaptrade_consumer_key:
            raise PersonalSnapTradeError(
                "SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY must be set in .env"
            )
        self._client_id = settings.snaptrade_client_id
        self._consumer_key = settings.snaptrade_consumer_key

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        extra_query: dict[str, str] | None = None,
    ) -> Any:
        timestamp = str(int(time.time()))
        query_params = {"clientId": self._client_id, "timestamp": timestamp}
        if extra_query:
            query_params.update(extra_query)
        query = urlencode(query_params)
        signature = compute_request_signature(
            path=path,
            query=query,
            consumer_key=self._consumer_key,
            body=body,
        )
        url = f"{BASE_URL}{path}?{query}"
        headers = {"Signature": signature, "Content-Type": "application/json"}
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method, url, headers=headers, json=body)
        if response.status_code >= 400:
            raise PersonalSnapTradeError(
                f"{method} {path} failed with HTTP {response.status_code}: {response.text}"
            )
        if not response.content:
            return None
        return response.json()

    def connection_portal_url(self, *, broker: str = WEALTHSIMPLE_BROKER) -> str:
        body = {
            "broker": broker,
            "connectionType": "read",
            "connectionPortalVersion": "v4",
        }
        data = self._request("POST", "/snapTrade/login", body=body)
        if isinstance(data, dict):
            url = data.get("redirectURI") or data.get("redirect_uri")
            if url:
                return url
        raise PersonalSnapTradeError(f"Login response missing redirectURI: {data!r}")

    def list_accounts(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/accounts")
        if not isinstance(data, list):
            raise PersonalSnapTradeError(f"Unexpected accounts response: {data!r}")
        return [a for a in data if isinstance(a, dict)]

    def list_connections(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/authorizations")
        if not isinstance(data, list):
            raise PersonalSnapTradeError(f"Unexpected connections response: {data!r}")
        return [c for c in data if isinstance(c, dict)]

    def refresh_connection(self, authorization_id: str) -> bool:
        """Trigger a holdings refresh. Returns False if the plan disallows manual refresh."""
        try:
            self._request("POST", f"/authorizations/{authorization_id}/refresh")
            return True
        except PersonalSnapTradeError as exc:
            if _is_refresh_unavailable(exc):
                return False
            raise

    def get_account_positions(self, account_id: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/accounts/{account_id}/positions")
        if not isinstance(data, list):
            raise PersonalSnapTradeError(f"Unexpected positions response: {data!r}")
        return [p for p in data if isinstance(p, dict)]
