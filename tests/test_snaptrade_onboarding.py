"""Tests for per-user SnapTrade onboarding and credential encryption."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from app.config import DEFAULT_USER_ID
from app.crypto.secrets import decrypt_secret, encrypt_secret
from app.integrations.snaptrade.onboarding import (
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
