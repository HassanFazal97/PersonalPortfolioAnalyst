"""One-click Discord connect: state signing, code exchange, and the
connect-url / OAuth-callback routes."""

import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_USER_ID, get_settings
from app.delivery import discord_connect
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}
_SECRET = "state-secret"  # pinned; .env may set its own UNSUBSCRIBE_SECRET
WEBHOOK = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnop"
CALLBACK = "/integrations/discord/callback"

_DISCORD_ENV = {
    "DISCORD_CLIENT_ID": "client-123",
    "DISCORD_CLIENT_SECRET": "shhh",
    "PUBLIC_BASE_URL": "https://app.test",
}


def _client(monkeypatch, repo, *, env: dict[str, str] | None = None):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", _SECRET)
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    # setenv("") rather than delenv: .env may define these, and pydantic
    # reads .env directly — only a present-but-empty env var overrides it.
    for key in ("DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "PUBLIC_BASE_URL"):
        monkeypatch.setenv(key, "")
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    app.state.delivery_scheduler = None
    app.state.delivery_adapters = {}
    return TestClient(app)


# ---- state token -----------------------------------------------------------


def test_state_roundtrip():
    state = discord_connect.sign_state(_SECRET, _OWNER, return_to="settings")
    assert discord_connect.verify_state(_SECRET, state) == (
        _OWNER,
        "/app/settings/delivery",
    )


def test_state_onboarding_return_path():
    state = discord_connect.sign_state(_SECRET, _OWNER, return_to="onboarding")
    assert discord_connect.verify_state(_SECRET, state) == (_OWNER, "/app/onboarding")


def test_state_rejects_tampering():
    state = discord_connect.sign_state(_SECRET, _OWNER, return_to="settings")
    other = str(uuid.uuid4())
    tampered = other + state[len(str(_OWNER)) :]
    assert discord_connect.verify_state(_SECRET, tampered) is None


def test_state_rejects_wrong_secret():
    state = discord_connect.sign_state(_SECRET, _OWNER, return_to="settings")
    assert discord_connect.verify_state("other-secret", state) is None


def test_state_rejects_garbage_and_empty():
    assert discord_connect.verify_state(_SECRET, "") is None
    assert discord_connect.verify_state(_SECRET, "a:b:c") is None
    assert discord_connect.verify_state("", "anything") is None


def test_state_expires(monkeypatch):
    state = discord_connect.sign_state(_SECRET, _OWNER, return_to="settings")
    issued = int(state.split(":")[2])
    monkeypatch.setattr(
        discord_connect.time,
        "time",
        lambda: issued + discord_connect.STATE_TTL_SECONDS + 1,
    )
    assert discord_connect.verify_state(_SECRET, state) is None


def test_sign_state_rejects_unknown_return_to():
    with pytest.raises(ValueError):
        discord_connect.sign_state(_SECRET, _OWNER, return_to="https://evil.example")


def test_authorize_url():
    url = discord_connect.authorize_url(
        "client-123", redirect_uri="https://app.test" + CALLBACK, state="st"
    )
    parsed = urlparse(url)
    assert parsed.scheme == "https" and parsed.netloc == "discord.com"
    query = parse_qs(parsed.query)
    assert query["client_id"] == ["client-123"]
    assert query["scope"] == ["webhook.incoming"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["https://app.test" + CALLBACK]
    assert query["state"] == ["st"]


# ---- code exchange ---------------------------------------------------------


def _transport(status: int, body: dict):
    return httpx.MockTransport(lambda request: httpx.Response(status, json=body))


async def test_exchange_code_returns_webhook_url():
    url = await discord_connect.exchange_code(
        "client-123",
        "shhh",
        code="abc",
        redirect_uri="https://app.test" + CALLBACK,
        transport=_transport(200, {"webhook": {"url": WEBHOOK}}),
    )
    assert url == WEBHOOK


async def test_exchange_code_rejected_status():
    with pytest.raises(discord_connect.DiscordConnectError):
        await discord_connect.exchange_code(
            "client-123",
            "shhh",
            code="abc",
            redirect_uri="https://app.test" + CALLBACK,
            transport=_transport(400, {"error": "invalid_grant"}),
        )


async def test_exchange_code_missing_or_foreign_webhook():
    for body in ({}, {"webhook": {}}, {"webhook": {"url": "https://evil.example/h"}}):
        with pytest.raises(discord_connect.DiscordConnectError):
            await discord_connect.exchange_code(
                "client-123",
                "shhh",
                code="abc",
                redirect_uri="https://app.test" + CALLBACK,
                transport=_transport(200, body),
            )


# ---- /me/notifications/discord/connect-url ---------------------------------


def test_connect_url_unconfigured_returns_503(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER)
    resp = _client(monkeypatch, repo).get(
        "/me/notifications/discord/connect-url", headers=_AUTH
    )
    assert resp.status_code == 503


def test_connect_url_requires_auth(monkeypatch):
    repo = FakeRepo()
    resp = _client(monkeypatch, repo, env=_DISCORD_ENV).get(
        "/me/notifications/discord/connect-url"
    )
    assert resp.status_code == 401


def test_connect_url_rejects_unknown_return_to(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER)
    resp = _client(monkeypatch, repo, env=_DISCORD_ENV).get(
        "/me/notifications/discord/connect-url",
        headers=_AUTH,
        params={"return_to": "https://evil.example"},
    )
    assert resp.status_code == 400


def test_connect_url_mints_signed_state(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER)
    resp = _client(monkeypatch, repo, env=_DISCORD_ENV).get(
        "/me/notifications/discord/connect-url", headers=_AUTH
    )
    assert resp.status_code == 200
    query = parse_qs(urlparse(resp.json()["url"]).query)
    assert query["client_id"] == ["client-123"]
    assert query["redirect_uri"] == ["https://app.test" + CALLBACK]
    parsed = discord_connect.verify_state(_SECRET, query["state"][0])
    assert parsed == (_OWNER, "/app/settings/delivery")


def test_notifications_payload_advertises_discord_oauth(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER)
    assert (
        _client(monkeypatch, repo, env=_DISCORD_ENV)
        .get("/me/notifications", headers=_AUTH)
        .json()["discord_oauth"]
        is True
    )
    assert (
        _client(monkeypatch, repo)
        .get("/me/notifications", headers=_AUTH)
        .json()["discord_oauth"]
        is False
    )


# ---- OAuth callback --------------------------------------------------------


def _fake_exchange(monkeypatch, *, url=WEBHOOK, fail=False):
    calls = []

    async def fake(client_id, client_secret, *, code, redirect_uri, **kwargs):
        calls.append({"code": code, "redirect_uri": redirect_uri})
        if fail:
            raise discord_connect.DiscordConnectError("boom")
        return url

    monkeypatch.setattr(discord_connect, "exchange_code", fake)
    return calls


def test_callback_stores_verified_preferred_channel(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER)
    calls = _fake_exchange(monkeypatch)
    client = _client(monkeypatch, repo, env=_DISCORD_ENV)
    state = discord_connect.sign_state(_SECRET, _OWNER, return_to="settings")
    resp = client.get(
        CALLBACK, params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/settings/delivery?discord=connected"
    assert calls[0]["code"] == "abc"
    assert calls[0]["redirect_uri"] == "https://app.test" + CALLBACK
    row = repo._notification_channels[(_OWNER, "discord")]
    assert row.destination == WEBHOOK
    assert row.verified_at is not None
    assert repo._users_by_id[_OWNER].preferred_channel == "discord"


def test_callback_onboarding_returns_to_onboarding(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER)
    _fake_exchange(monkeypatch)
    client = _client(monkeypatch, repo, env=_DISCORD_ENV)
    state = discord_connect.sign_state(_SECRET, _OWNER, return_to="onboarding")
    resp = client.get(
        CALLBACK, params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert resp.headers["location"] == "/app/onboarding?discord=connected"


def test_callback_invalid_state_redirects_error(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER)
    client = _client(monkeypatch, repo, env=_DISCORD_ENV)
    resp = client.get(
        CALLBACK, params={"code": "abc", "state": "forged"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/settings/delivery?discord=error"
    assert (_OWNER, "discord") not in repo._notification_channels


def test_callback_user_cancelled(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER)
    client = _client(monkeypatch, repo, env=_DISCORD_ENV)
    state = discord_connect.sign_state(_SECRET, _OWNER, return_to="settings")
    resp = client.get(
        CALLBACK,
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )
    assert resp.headers["location"] == "/app/settings/delivery?discord=cancelled"
    assert (_OWNER, "discord") not in repo._notification_channels


def test_callback_exchange_failure_redirects_error(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER)
    _fake_exchange(monkeypatch, fail=True)
    client = _client(monkeypatch, repo, env=_DISCORD_ENV)
    state = discord_connect.sign_state(_SECRET, _OWNER, return_to="settings")
    resp = client.get(
        CALLBACK, params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert resp.headers["location"] == "/app/settings/delivery?discord=error"
    assert (_OWNER, "discord") not in repo._notification_channels
