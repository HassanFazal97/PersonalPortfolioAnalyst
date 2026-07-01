"""Thin wrapper around the SnapTrade Python SDK (commercial) and personal HTTP client."""

from __future__ import annotations

from typing import Any, Protocol

from snaptrade_client import SnapTrade
from snaptrade_client.exceptions import ApiException

from app.config import Settings
from app.integrations.snaptrade.personal_client import (
    PersonalSnapTradeClient,
    PersonalSnapTradeError,
    _is_personal_register_error,
)

WEALTHSIMPLE_BROKER = "WEALTHSIMPLE"


class SnapTradeError(RuntimeError):
    """SnapTrade API call failed or returned an unexpected payload."""


def _body(response: Any) -> Any:
    return getattr(response, "body", response)


def _require_ok(response: Any, *, action: str) -> Any:
    status = getattr(response, "status", 200)
    if status >= 400:
        raise SnapTradeError(f"{action} failed with HTTP {status}: {_body(response)}")
    return _body(response)


class _SnapTradeBackend(Protocol):
    def connection_portal_url(self, *, broker: str = WEALTHSIMPLE_BROKER) -> str: ...

    def list_accounts(self) -> list[dict[str, Any]]: ...

    def list_connections(self) -> list[dict[str, Any]]: ...

    def refresh_connection(self, authorization_id: str) -> None: ...

    def get_account_positions(self, account_id: str) -> list[dict[str, Any]]: ...


class _CommercialBackend:
    """Commercial SnapTrade keys: clientId + consumerKey + userId + userSecret."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = SnapTrade(
            client_id=settings.snaptrade_client_id,
            consumer_key=settings.snaptrade_consumer_key,
        )

    @property
    def user_id(self) -> str:
        return self._settings.snaptrade_user_id

    @property
    def user_secret(self) -> str:
        secret = self._settings.snaptrade_user_secret
        if not secret:
            raise SnapTradeError("SNAPTRADE_USER_SECRET is not set.")
        return secret

    def register_user(self, user_id: str | None = None) -> dict[str, str]:
        uid = user_id or self._settings.snaptrade_user_id
        response = self._client.authentication.register_snap_trade_user(user_id=uid)
        body = _require_ok(response, action="register_snap_trade_user")
        if not isinstance(body, dict):
            raise SnapTradeError(f"Unexpected register response: {body!r}")
        user_secret = body.get("userSecret") or body.get("user_secret")
        if not user_secret:
            raise SnapTradeError(f"Register response missing userSecret: {body!r}")
        return {"userId": uid, "userSecret": user_secret}

    def connection_portal_url(self, *, broker: str = WEALTHSIMPLE_BROKER) -> str:
        response = self._client.authentication.login_snap_trade_user(
            user_id=self.user_id,
            user_secret=self.user_secret,
            broker=broker,
            connection_type="read",
            connection_portal_version="v4",
        )
        body = _require_ok(response, action="login_snap_trade_user")
        if isinstance(body, dict):
            url = body.get("redirectURI") or body.get("redirect_uri")
            if url:
                return url
        raise SnapTradeError(f"Login response missing redirectURI: {body!r}")

    def list_accounts(self) -> list[dict[str, Any]]:
        response = self._client.account_information.list_user_accounts(
            user_id=self.user_id,
            user_secret=self.user_secret,
        )
        body = _require_ok(response, action="list_user_accounts")
        if not isinstance(body, list):
            raise SnapTradeError(f"Unexpected accounts response: {body!r}")
        return [a for a in body if isinstance(a, dict)]

    def list_connections(self) -> list[dict[str, Any]]:
        response = self._client.connections.list_brokerage_authorizations(
            user_id=self.user_id,
            user_secret=self.user_secret,
        )
        body = _require_ok(response, action="list_brokerage_authorizations")
        if not isinstance(body, list):
            raise SnapTradeError(f"Unexpected connections response: {body!r}")
        return [c for c in body if isinstance(c, dict)]

    def refresh_connection(self, authorization_id: str) -> None:
        response = self._client.connections.refresh_brokerage_authorization(
            authorization_id=authorization_id,
            user_id=self.user_id,
            user_secret=self.user_secret,
        )
        _require_ok(response, action="refresh_brokerage_authorization")

    def get_account_positions(self, account_id: str) -> list[dict[str, Any]]:
        response = self._client.account_information.get_user_account_positions(
            account_id=account_id,
            user_id=self.user_id,
            user_secret=self.user_secret,
        )
        body = _require_ok(response, action="get_user_account_positions")
        if not isinstance(body, list):
            raise SnapTradeError(f"Unexpected positions response: {body!r}")
        return [p for p in body if isinstance(p, dict)]


def is_personal_key_mode(settings: Settings) -> bool:
    """Personal dashboard keys omit userSecret; commercial keys require it."""
    if settings.snaptrade_auth_mode == "personal":
        return True
    if settings.snaptrade_auth_mode == "commercial":
        return False
    # Auto: no secret → personal (dashboard SDK keys).
    return not settings.snaptrade_user_secret


class SnapTradeService:
    """SnapTrade client — auto-selects personal vs commercial auth."""

    def __init__(self, settings: Settings) -> None:
        if not settings.snaptrade_client_id or not settings.snaptrade_consumer_key:
            raise SnapTradeError(
                "SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY must be set in .env"
            )
        self._settings = settings
        self.personal_mode = is_personal_key_mode(settings)
        if self.personal_mode:
            self._backend: _SnapTradeBackend = PersonalSnapTradeClient(settings)
        else:
            self._backend = _CommercialBackend(settings)

    def register_user(self, user_id: str | None = None) -> dict[str, str]:
        if self.personal_mode:
            raise SnapTradeError(
                "Personal SnapTrade keys do not use registerUser. Your user is "
                "already provisioned at signup — only CLIENT_ID and CONSUMER_KEY "
                "are needed. Run this script again to get the connect URL."
            )
        if not isinstance(self._backend, _CommercialBackend):
            raise SnapTradeError("register_user is only available in commercial mode.")
        try:
            return self._backend.register_user(user_id)
        except ApiException as exc:
            if _is_personal_register_error(exc):
                raise SnapTradeError(
                    "These look like Personal SnapTrade keys (registerUser blocked). "
                    "Remove SNAPTRADE_USER_ID and SNAPTRADE_USER_SECRET from .env — "
                    "only CLIENT_ID and CONSUMER_KEY are needed."
                ) from exc
            raise SnapTradeError(str(exc)) from exc

    def connection_portal_url(self, *, broker: str = WEALTHSIMPLE_BROKER) -> str:
        try:
            return self._backend.connection_portal_url(broker=broker)
        except PersonalSnapTradeError as exc:
            raise SnapTradeError(str(exc)) from exc

    def list_accounts(self) -> list[dict[str, Any]]:
        try:
            return self._backend.list_accounts()
        except PersonalSnapTradeError as exc:
            raise SnapTradeError(str(exc)) from exc

    def list_connections(self) -> list[dict[str, Any]]:
        try:
            return self._backend.list_connections()
        except PersonalSnapTradeError as exc:
            raise SnapTradeError(str(exc)) from exc

    def refresh_connection(self, authorization_id: str) -> None:
        try:
            self._backend.refresh_connection(authorization_id)
        except PersonalSnapTradeError as exc:
            raise SnapTradeError(str(exc)) from exc

    def get_account_positions(self, account_id: str) -> list[dict[str, Any]]:
        try:
            return self._backend.get_account_positions(account_id)
        except PersonalSnapTradeError as exc:
            raise SnapTradeError(str(exc)) from exc
