"""Per-user SnapTrade onboarding: register, connect portal, resolve credentials."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.config import DEFAULT_USER_ID, Settings
from app.crypto.secrets import SecretsError, decrypt_secret, encrypt_secret
from app.db.repo import Repo
from app.integrations.snaptrade.client import (
    SnapTradeError,
    SnapTradeService,
    SnapTradeUserCredentials,
    is_personal_key_mode,
)

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)


def snaptrade_user_id_for(app_user_id: uuid.UUID) -> str:
    return f"user-{app_user_id}"


def _require_commercial_for_user(settings: Settings, user_id: uuid.UUID) -> None:
    """JWT users must use commercial mode with per-user credentials."""
    if user_id == _OWNER_USER_ID:
        return
    if is_personal_key_mode(settings):
        raise SnapTradeError(
            "Personal SnapTrade keys only work for the owner account. "
            "Configure commercial SnapTrade keys for multi-user onboarding."
        )
    if not settings.broker_secrets_key:
        raise SnapTradeError(
            "BROKER_SECRETS_KEY is not configured — required to store per-user "
            "broker credentials."
        )


async def resolve_credentials(
    repo: Repo,
    user_id: uuid.UUID,
    settings: Settings,
) -> SnapTradeUserCredentials | None:
    """Load decrypted SnapTrade credentials for a user.

    Owner falls back to env ``SNAPTRADE_USER_*`` when no DB row exists."""
    row = await repo.get_snaptrade_credentials(user_id)
    if row is not None:
        try:
            secret = decrypt_secret(settings.broker_secrets_key, row.user_secret_enc)
        except SecretsError as exc:
            raise SnapTradeError(str(exc)) from exc
        return SnapTradeUserCredentials(
            snaptrade_user_id=row.snaptrade_user_id,
            user_secret=secret,
        )
    if user_id == _OWNER_USER_ID and settings.snaptrade_user_secret:
        return SnapTradeUserCredentials(
            snaptrade_user_id=settings.snaptrade_user_id,
            user_secret=settings.snaptrade_user_secret,
        )
    return None


async def register_snaptrade_user(
    repo: Repo,
    user_id: uuid.UUID,
    settings: Settings,
) -> dict[str, str]:
    """Idempotent SnapTrade user registration for the app user."""
    _require_commercial_for_user(settings, user_id)
    existing = await resolve_credentials(repo, user_id, settings)
    if existing is not None:
        return {
            "snaptrade_user_id": existing.snaptrade_user_id,
            "registered": False,
        }

    st_user_id = snaptrade_user_id_for(user_id)
    service = SnapTradeService(settings, credentials=None)
    result = service.register_user(st_user_id)
    secret = result["userSecret"]
    enc = encrypt_secret(settings.broker_secrets_key, secret)
    await repo.save_snaptrade_credentials(
        user_id=user_id,
        snaptrade_user_id=st_user_id,
        user_secret_enc=enc,
    )
    return {"snaptrade_user_id": st_user_id, "registered": True}


async def service_for_user(
    repo: Repo,
    user_id: uuid.UUID,
    settings: Settings,
) -> SnapTradeService:
    """Build a SnapTrade client scoped to the authenticated user."""
    _require_commercial_for_user(settings, user_id)
    creds = await resolve_credentials(repo, user_id, settings)
    if creds is None:
        raise SnapTradeError(
            "SnapTrade is not registered for this user. "
            "Call POST /portfolio/snaptrade/register first."
        )
    return SnapTradeService(settings, credentials=creds)


async def portfolio_status(
    repo: Repo,
    user_id: uuid.UUID,
    settings: Settings,
) -> dict[str, Any]:
    """Connection/sync status for onboarding UI."""
    row = await repo.get_snaptrade_credentials(user_id)
    registered = row is not None or (
        user_id == _OWNER_USER_ID and bool(settings.snaptrade_user_secret)
    )
    connected = False
    connection_disabled = False
    accounts_count = 0
    if registered:
        try:
            service = await service_for_user(repo, user_id, settings)
            connections = service.list_connections()
            # SnapTrade flags a connection ``disabled`` when its brokerage auth
            # breaks (revoked/expired). Only live connections count as
            # connected; a disabled-only set means "reconnect needed".
            active = [c for c in connections if not c.get("disabled")]
            connected = len(active) > 0
            connection_disabled = bool(connections) and not active
            if connected and row is not None and row.connected_at is None:
                await repo.update_snaptrade_status(
                    user_id, connected_at=datetime.now()
                )
            accounts_count = len(service.list_accounts())
        except SnapTradeError:
            pass
    return {
        "registered": registered,
        "connected": connected,
        "connection_disabled": connection_disabled,
        "accounts_count": accounts_count,
        "last_sync_at": row.last_sync_at.isoformat() if row and row.last_sync_at else None,
        "last_sync_error": row.last_sync_error if row else None,
    }
