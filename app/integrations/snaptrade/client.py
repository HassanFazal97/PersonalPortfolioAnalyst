"""Thin wrapper around the SnapTrade Python SDK (commercial) and personal HTTP client."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from snaptrade_client import SnapTrade
from snaptrade_client.exceptions import ApiException

from app.config import Settings
from app.integrations.snaptrade.personal_client import (
    PersonalSnapTradeClient,
    PersonalSnapTradeError,
    _is_personal_register_error,
    _is_refresh_unavailable,
)


@dataclass(frozen=True)
class SnapTradeUserCredentials:
    """Per-user SnapTrade identity (commercial mode)."""

    snaptrade_user_id: str
    user_secret: str


class SnapTradeError(RuntimeError):
    """SnapTrade API call failed or returned an unexpected payload."""

    # 401/1083: the userId/userSecret was registered under a different
    # clientId (e.g. test keys swapped for prod) — the remote user does
    # not exist in this environment.
    STALE_USER_CODE = "1083"

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code

    @property
    def stale_user(self) -> bool:
        return self.code == self.STALE_USER_CODE


def _api_error(exc: ApiException, *, action: str) -> SnapTradeError:
    status = getattr(exc, "status", None)
    body = getattr(exc, "body", None)
    code = None
    if isinstance(body, Mapping):
        raw = body.get("code")
        code = str(raw) if raw is not None else None
    return SnapTradeError(
        f"{action} failed with HTTP {status}: {body}", status=status, code=code
    )


def _body(response: Any) -> Any:
    return getattr(response, "body", response)


def _require_ok(response: Any, *, action: str) -> Any:
    status = getattr(response, "status", 200)
    if status >= 400:
        raise SnapTradeError(f"{action} failed with HTTP {status}: {_body(response)}")
    return _body(response)


class _SnapTradeBackend(Protocol):
    def connection_portal_url(self, *, broker: str | None = None) -> str: ...

    def list_accounts(self) -> list[dict[str, Any]]: ...

    def list_connections(self) -> list[dict[str, Any]]: ...

    def refresh_connection(self, authorization_id: str) -> bool: ...

    def get_account_positions(self, account_id: str) -> list[dict[str, Any]]: ...


class _CommercialBackend:
    """Commercial SnapTrade keys: clientId + consumerKey + userId + userSecret."""

    def __init__(
        self,
        settings: Settings,
        credentials: SnapTradeUserCredentials | None = None,
    ) -> None:
        self._settings = settings
        self._credentials = credentials
        self._client = SnapTrade(
            client_id=settings.snaptrade_client_id,
            consumer_key=settings.snaptrade_consumer_key,
        )

    @property
    def user_id(self) -> str:
        if self._credentials is not None:
            return self._credentials.snaptrade_user_id
        return self._settings.snaptrade_user_id

    @property
    def user_secret(self) -> str:
        if self._credentials is not None:
            return self._credentials.user_secret
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

    def connection_portal_url(self, *, broker: str | None = None) -> str:
        # No broker → the portal shows SnapTrade's full brokerage picker.
        extra = {"broker": broker} if broker else {}
        response = self._client.authentication.login_snap_trade_user(
            user_id=self.user_id,
            user_secret=self.user_secret,
            connection_type="read",
            connection_portal_version="v4",
            **extra,
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

    def refresh_connection(self, authorization_id: str) -> bool:
        try:
            response = self._client.connections.refresh_brokerage_authorization(
                authorization_id=authorization_id,
                user_id=self.user_id,
                user_secret=self.user_secret,
            )
            _require_ok(response, action="refresh_brokerage_authorization")
            return True
        except ApiException as exc:
            if _is_refresh_unavailable(exc):
                return False
            raise

    def delete_user(self) -> bool:
        """Delete the SnapTrade user, severing every brokerage connection."""
        response = self._client.authentication.delete_snap_trade_user(
            user_id=self.user_id
        )
        _require_ok(response, action="delete_snap_trade_user")
        return True

    def get_account_positions(self, account_id: str) -> list[dict[str, Any]]:
        response = self._client.account_information.get_all_account_positions(
            account_id=account_id,
            user_id=self.user_id,
            user_secret=self.user_secret,
        )
        body = _require_ok(response, action="get_all_account_positions")
        results = body.get("results") if isinstance(body, dict) else None
        if results is None:
            raise SnapTradeError(f"Unexpected positions response: {body!r}")
        return [p for p in results if isinstance(p, dict)]


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

    def __init__(
        self,
        settings: Settings,
        *,
        credentials: SnapTradeUserCredentials | None = None,
    ) -> None:
        if not settings.snaptrade_client_id or not settings.snaptrade_consumer_key:
            raise SnapTradeError(
                "SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY must be set in .env"
            )
        self._settings = settings
        self.personal_mode = credentials is None and is_personal_key_mode(settings)
        if self.personal_mode:
            self._backend: _SnapTradeBackend = PersonalSnapTradeClient(settings)
        else:
            self._backend = _CommercialBackend(settings, credentials)

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
            raise _api_error(exc, action="register_user") from exc

    def connection_portal_url(self, *, broker: str | None = None) -> str:
        try:
            return self._backend.connection_portal_url(broker=broker)
        except PersonalSnapTradeError as exc:
            raise SnapTradeError(str(exc)) from exc
        except ApiException as exc:
            raise _api_error(exc, action="connection_portal_url") from exc

    def list_accounts(self) -> list[dict[str, Any]]:
        try:
            return self._backend.list_accounts()
        except PersonalSnapTradeError as exc:
            raise SnapTradeError(str(exc)) from exc
        except ApiException as exc:
            raise _api_error(exc, action="list_accounts") from exc

    def list_connections(self) -> list[dict[str, Any]]:
        try:
            return self._backend.list_connections()
        except PersonalSnapTradeError as exc:
            raise SnapTradeError(str(exc)) from exc
        except ApiException as exc:
            raise _api_error(exc, action="list_connections") from exc

    def refresh_connection(self, authorization_id: str) -> bool:
        """Trigger a holdings refresh. Returns False if manual refresh is unavailable."""
        try:
            return self._backend.refresh_connection(authorization_id)
        except PersonalSnapTradeError as exc:
            if _is_refresh_unavailable(exc):
                return False
            raise SnapTradeError(str(exc)) from exc
        except ApiException as exc:
            raise _api_error(exc, action="refresh_connection") from exc

    def delete_user(self) -> bool:
        """Delete the SnapTrade user remotely (commercial mode only).

        Personal dashboard keys have no per-user deletion — returns False so
        callers can still clear local state and say what happened."""
        if self.personal_mode or not isinstance(self._backend, _CommercialBackend):
            return False
        try:
            return self._backend.delete_user()
        except ApiException as exc:
            raise _api_error(exc, action="delete_user") from exc

    def get_account_positions(self, account_id: str) -> list[dict[str, Any]]:
        try:
            return self._backend.get_account_positions(account_id)
        except PersonalSnapTradeError as exc:
            raise SnapTradeError(str(exc)) from exc
        except ApiException as exc:
            raise _api_error(exc, action="get_account_positions") from exc
