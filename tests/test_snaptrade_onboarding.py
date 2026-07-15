"""Tests for per-user SnapTrade onboarding and credential encryption."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from app.config import DEFAULT_USER_ID
from app.crypto.secrets import decrypt_secret, encrypt_secret
from app.integrations.snaptrade.client import SnapTradeError
from app.integrations.snaptrade.onboarding import (
    portfolio_status,
    register_snaptrade_user,
    resolve_credentials,
    snaptrade_user_id_for,
)
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_FERNET_KEY = Fernet.generate_key().decode()


def test_encrypt_decrypt_round_trip():
    ciphertext = encrypt_secret(_FERNET_KEY, "super-secret")
    assert decrypt_secret(_FERNET_KEY, ciphertext) == "super-secret"


def test_snaptrade_user_id_is_stable():
    uid = uuid.uuid4()
    assert snaptrade_user_id_for(uid) == f"user-{uid}"


@pytest.mark.asyncio
async def test_register_snaptrade_user_persists_encrypted_secret(monkeypatch):
    repo = FakeRepo()
    settings = MagicMock()
    settings.broker_secrets_key = _FERNET_KEY
    settings.snaptrade_user_secret = ""

    mock_service = MagicMock()
    mock_service.register_user.return_value = {
        "userId": f"user-{_OWNER}",
        "userSecret": "plain-secret",
    }
    monkeypatch.setattr(
        "app.integrations.snaptrade.onboarding.SnapTradeService",
        lambda *a, **k: mock_service,
    )
    monkeypatch.setattr(
        "app.integrations.snaptrade.onboarding.is_personal_key_mode",
        lambda s: False,
    )

    result = await register_snaptrade_user(repo, _OWNER, settings)
    assert result["registered"] is True
    row = await repo.get_snaptrade_credentials(_OWNER)
    assert row is not None
    assert decrypt_secret(_FERNET_KEY, row.user_secret_enc) == "plain-secret"


def _commercial_mode(monkeypatch, service):
    monkeypatch.setattr(
        "app.integrations.snaptrade.onboarding.SnapTradeService",
        lambda *a, **k: service,
    )
    monkeypatch.setattr(
        "app.integrations.snaptrade.onboarding.is_personal_key_mode",
        lambda s: False,
    )
    monkeypatch.setattr(
        "app.integrations.snaptrade.onboarding._REREGISTER_DELAY_SECONDS", 0
    )


def _user_exists_error():
    return SnapTradeError(
        "register_user failed with HTTP 400: user already exists",
        status=400,
        code="1010",
    )


@pytest.mark.asyncio
async def test_register_recovers_orphaned_remote_user(monkeypatch):
    # SnapTrade knows the userId but we hold no secret (disconnect cleared it
    # or the stale-credential self-heal dropped the row). The secret is only
    # issued at registration, so recovery = delete remote user + re-register.
    repo = FakeRepo()
    settings = MagicMock()
    settings.broker_secrets_key = _FERNET_KEY
    settings.snaptrade_user_secret = ""
    user = uuid.uuid4()

    service = MagicMock()
    service.register_user.side_effect = [
        _user_exists_error(),
        {"userId": f"user-{user}", "userSecret": "fresh-secret"},
    ]
    _commercial_mode(monkeypatch, service)

    result = await register_snaptrade_user(repo, user, settings)

    service.delete_user.assert_called_once_with(f"user-{user}")
    assert result["registered"] is True
    row = await repo.get_snaptrade_credentials(user)
    assert decrypt_secret(_FERNET_KEY, row.user_secret_enc) == "fresh-secret"


@pytest.mark.asyncio
async def test_register_retries_while_remote_deletion_queues(monkeypatch):
    # SnapTrade deletes users asynchronously: a register fired right after the
    # delete can bounce with 1010 again before eventually succeeding.
    repo = FakeRepo()
    settings = MagicMock()
    settings.broker_secrets_key = _FERNET_KEY
    settings.snaptrade_user_secret = ""
    user = uuid.uuid4()

    service = MagicMock()
    service.register_user.side_effect = [
        _user_exists_error(),
        _user_exists_error(),
        _user_exists_error(),
        {"userId": f"user-{user}", "userSecret": "fresh-secret"},
    ]
    _commercial_mode(monkeypatch, service)

    result = await register_snaptrade_user(repo, user, settings)
    assert result["registered"] is True
    assert service.register_user.call_count == 4


@pytest.mark.asyncio
async def test_register_other_errors_propagate_without_deleting(monkeypatch):
    # Only the orphaned-user case may delete remote state; anything else
    # (rate limits, bad keys) must surface untouched.
    repo = FakeRepo()
    settings = MagicMock()
    settings.broker_secrets_key = _FERNET_KEY
    settings.snaptrade_user_secret = ""

    service = MagicMock()
    service.register_user.side_effect = SnapTradeError(
        "register_user failed with HTTP 429: slow down", status=429
    )
    _commercial_mode(monkeypatch, service)

    with pytest.raises(SnapTradeError):
        await register_snaptrade_user(repo, uuid.uuid4(), settings)
    service.delete_user.assert_not_called()


@pytest.mark.asyncio
async def test_register_is_idempotent(monkeypatch):
    repo = FakeRepo()
    settings = MagicMock()
    settings.broker_secrets_key = _FERNET_KEY
    enc = encrypt_secret(_FERNET_KEY, "existing")
    await repo.save_snaptrade_credentials(
        user_id=_OWNER,
        snaptrade_user_id=f"user-{_OWNER}",
        user_secret_enc=enc,
    )

    result = await register_snaptrade_user(repo, _OWNER, settings)
    assert result["registered"] is False


@pytest.mark.asyncio
async def test_owner_falls_back_to_env_when_no_db_row():
    repo = FakeRepo()
    settings = MagicMock()
    settings.broker_secrets_key = _FERNET_KEY
    settings.snaptrade_user_id = "portfolio-owner"
    settings.snaptrade_user_secret = "env-secret"

    creds = await resolve_credentials(repo, _OWNER, settings)
    assert creds is not None
    assert creds.user_secret == "env-secret"


# --- portfolio_status: live vs disabled connections ---------------------------


async def _registered_repo():
    repo = FakeRepo()
    await repo.save_snaptrade_credentials(
        user_id=_OWNER,
        snaptrade_user_id=f"user-{_OWNER}",
        user_secret_enc=encrypt_secret(_FERNET_KEY, "secret"),
    )
    return repo


def _status_service(monkeypatch, connections):
    service = MagicMock()
    service.list_connections.return_value = connections
    service.list_accounts.return_value = []

    async def fake_service_for_user(repo, user_id, settings):
        return service

    monkeypatch.setattr(
        "app.integrations.snaptrade.onboarding.service_for_user",
        fake_service_for_user,
    )
    return service


@pytest.mark.asyncio
async def test_status_active_connection_is_connected(monkeypatch):
    repo = await _registered_repo()
    _status_service(monkeypatch, [{"id": "auth-1", "disabled": False}])
    status = await portfolio_status(repo, _OWNER, MagicMock())
    assert status["connected"] is True
    assert status["connection_disabled"] is False


@pytest.mark.asyncio
async def test_status_disabled_connection_flags_reconnect(monkeypatch):
    # SnapTrade marks a connection disabled when brokerage auth breaks; that
    # must read as "reconnect needed", not "connected".
    repo = await _registered_repo()
    _status_service(monkeypatch, [{"id": "auth-1", "disabled": True}])
    status = await portfolio_status(repo, _OWNER, MagicMock())
    assert status["connected"] is False
    assert status["connection_disabled"] is True


@pytest.mark.asyncio
async def test_status_no_connections_is_not_disabled(monkeypatch):
    # A registered user who never connected: no banner signal, onboarding
    # keeps its empty state.
    repo = await _registered_repo()
    _status_service(monkeypatch, [])
    status = await portfolio_status(repo, _OWNER, MagicMock())
    assert status["connected"] is False
    assert status["connection_disabled"] is False


# --- stale credentials self-heal (test → prod key swap) ------------------------


@pytest.mark.asyncio
async def test_status_stale_user_clears_dead_row(monkeypatch):
    # 401/1083 means the stored secret was registered under a different
    # clientId — the row is dead and must be dropped so the user can
    # re-register.
    user = uuid.uuid4()
    repo = FakeRepo()
    await repo.save_snaptrade_credentials(
        user_id=user,
        snaptrade_user_id=f"user-{user}",
        user_secret_enc=encrypt_secret(_FERNET_KEY, "secret"),
    )
    service = _status_service(monkeypatch, [])
    service.list_connections.side_effect = SnapTradeError(
        "list_connections failed with HTTP 401", status=401, code="1083"
    )
    settings = MagicMock()
    settings.snaptrade_user_secret = ""

    status = await portfolio_status(repo, user, settings)

    assert status["registered"] is False
    assert status["connected"] is False
    assert await repo.get_snaptrade_credentials(user) is None


@pytest.mark.asyncio
async def test_status_non_stale_error_keeps_row(monkeypatch):
    # Transient failures (5xx, rate limits, network) must not destroy
    # credentials — only degrade to "not connected".
    repo = await _registered_repo()
    service = _status_service(monkeypatch, [])
    service.list_connections.side_effect = SnapTradeError(
        "list_connections failed with HTTP 500", status=500
    )

    status = await portfolio_status(repo, _OWNER, MagicMock())

    assert status["registered"] is True
    assert status["connected"] is False
    assert await repo.get_snaptrade_credentials(_OWNER) is not None
