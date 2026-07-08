"""HTTP routes for /me/notifications: register, verify, preferred channel."""

import re
import uuid

from fastapi.testclient import TestClient

from app.config import DEFAULT_USER_ID, get_settings
from app.delivery.adapters.base import SendResult
from app.delivery.adapters.discord import DiscordAdapter
from app.delivery.adapters.email_resend import ResendEmailAdapter
from app.delivery.adapters.twilio_sms import TwilioSMSAdapter
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}
WEBHOOK = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnop"


class CaptureAdapter:
    """Records outbound sends and returns success — used as a fake provider."""

    def __init__(self, channel: str, *, ok: bool = True):
        self.channel = channel
        self.sent: list[tuple[str, str, dict]] = []
        self._ok = ok

    async def send(self, destination, body, payload):
        self.sent.append((destination, body, payload))
        return SendResult(ok=self._ok, error=None if self._ok else "delivery failed")


def _adapters(*, discord=True, email=False, sms=False, discord_ok=True):
    adapters = {}
    if discord:
        adapters["discord"] = CaptureAdapter("discord", ok=discord_ok)
    if email:
        adapters["email"] = CaptureAdapter("email")
    if sms:
        adapters["sms"] = CaptureAdapter("sms")
    return adapters


def _client(monkeypatch, repo, *, adapters=None, env: dict[str, str] | None = None):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    for key, value in (env or {}).items():
        if value:
            monkeypatch.setenv(key, value)
        else:
            monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    app.state.delivery_scheduler = None
    app.state.delivery_adapters = adapters if adapters is not None else _adapters()
    return TestClient(app)


def _extract_code(body: str) -> str:
    match = re.search(r"\b(\d{6})\b", body)
    assert match is not None, body
    return match.group(1)


def test_notifications_requires_auth(monkeypatch):
    assert _client(monkeypatch, FakeRepo()).get("/me/notifications").status_code == 401


def test_get_notifications_empty(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    body = _client(monkeypatch, repo).get("/me/notifications", headers=_AUTH).json()
    assert body["preferred_channel"] is None
    assert body["channels"] == []
    assert "discord" in body["available_channels"]


def test_get_notifications_lists_registered_channels(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    repo._notification_channels[(_OWNER, "discord")] = type(
        "Row",
        (),
        {
            "channel": "discord",
            "destination": WEBHOOK,
            "verified_at": now,
            "opted_out_at": None,
            "consent_at": None,
        },
    )()
    repo._users_by_id[_OWNER].preferred_channel = "discord"

    body = _client(monkeypatch, repo).get("/me/notifications", headers=_AUTH).json()
    assert body["preferred_channel"] == "discord"
    assert len(body["channels"]) == 1
    ch = body["channels"][0]
    assert ch["channel"] == "discord"
    assert ch["verified"] is True
    assert ch["destination_masked"].startswith("discord webhook")


def test_register_sms_requires_consent(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    client = _client(
        monkeypatch,
        repo,
        adapters=_adapters(sms=True),
        env={
            "TWILIO_ACCOUNT_SID": "ACtest",
            "TWILIO_AUTH_TOKEN": "token",
            "TWILIO_FROM_NUMBER": "+15005550006",
        },
    )
    resp = client.post(
        "/me/notifications/channel",
        headers=_AUTH,
        json={"channel": "sms", "destination": "+14165551234", "consent": False},
    )
    assert resp.status_code == 400
    assert "consent" in resp.json()["detail"].lower()


def test_register_rejects_unconfigured_channel(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    resp = _client(monkeypatch, repo, adapters=_adapters(email=False)).post(
        "/me/notifications/channel",
        headers=_AUTH,
        json={"channel": "email", "destination": "you@example.com", "consent": False},
    )
    assert resp.status_code == 400
    assert "not available" in resp.json()["detail"]


def test_register_rejects_bad_destination(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    resp = _client(monkeypatch, repo).post(
        "/me/notifications/channel",
        headers=_AUTH,
        json={"channel": "discord", "destination": "https://evil.example/hook"},
    )
    assert resp.status_code == 400
    assert "webhook" in resp.json()["detail"].lower()


def test_register_channel_sends_code(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    adapters = _adapters()
    client = _client(monkeypatch, repo, adapters=adapters)
    resp = client.post(
        "/me/notifications/channel",
        headers=_AUTH,
        json={"channel": "discord", "destination": WEBHOOK},
    )
    assert resp.status_code == 202
    assert resp.json() == {"status": "code_sent", "channel": "discord"}
    assert len(adapters["discord"].sent) == 1
    assert _extract_code(adapters["discord"].sent[0][1])


def test_register_channel_send_failure_returns_502(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    adapters = _adapters(discord_ok=False)
    resp = _client(monkeypatch, repo, adapters=adapters).post(
        "/me/notifications/channel",
        headers=_AUTH,
        json={"channel": "discord", "destination": WEBHOOK},
    )
    assert resp.status_code == 502


def test_verify_channel_happy_path(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    adapters = _adapters()
    client = _client(monkeypatch, repo, adapters=adapters)
    client.post(
        "/me/notifications/channel",
        headers=_AUTH,
        json={"channel": "discord", "destination": WEBHOOK},
    )
    code = _extract_code(adapters["discord"].sent[0][1])
    resp = client.post(
        "/me/notifications/verify",
        headers=_AUTH,
        json={"channel": "discord", "code": code},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["preferred_channel"] == "discord"
    assert body["channels"][0]["verified"] is True


def test_verify_wrong_code(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    adapters = _adapters()
    client = _client(monkeypatch, repo, adapters=adapters)
    client.post(
        "/me/notifications/channel",
        headers=_AUTH,
        json={"channel": "discord", "destination": WEBHOOK},
    )
    resp = client.post(
        "/me/notifications/verify",
        headers=_AUTH,
        json={"channel": "discord", "code": "000000"},
    )
    assert resp.status_code == 400
    assert "wrong code" in resp.json()["detail"].lower()


def test_set_preferred_among_verified_channels(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    adapters = _adapters(email=True)
    client = _client(
        monkeypatch,
        repo,
        adapters=adapters,
        env={"RESEND_API_KEY": "re_test", "EMAIL_FROM": "Digest <d@example.com>"},
    )
    for channel, destination in (
        ("discord", WEBHOOK),
        ("email", "you@example.com"),
    ):
        client.post(
            "/me/notifications/channel",
            headers=_AUTH,
            json={"channel": channel, "destination": destination},
        )
        code = _extract_code(adapters[channel].sent[0][1])
        client.post(
            "/me/notifications/verify",
            headers=_AUTH,
            json={"channel": channel, "code": code},
        )

    resp = client.post(
        "/me/notifications/preferred",
        headers=_AUTH,
        json={"channel": "email"},
    )
    assert resp.status_code == 200
    assert resp.json()["preferred_channel"] == "email"


def test_set_preferred_rejects_unverified(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    resp = _client(
        monkeypatch,
        repo,
        adapters=_adapters(email=True),
        env={"RESEND_API_KEY": "re_test", "EMAIL_FROM": "Digest <d@example.com>"},
    ).post(
        "/me/notifications/preferred",
        headers=_AUTH,
        json={"channel": "email"},
    )
    assert resp.status_code == 400
    assert "not verified" in resp.json()["detail"].lower()


def test_available_channels_reflects_env(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    body = _client(
        monkeypatch,
        repo,
        adapters={
            "discord": DiscordAdapter(),
            "email": ResendEmailAdapter(api_key="k", from_addr="d@x.com"),
            "sms": TwilioSMSAdapter(
                account_sid="AC1", auth_token="t", from_number="+15005550006"
            ),
        },
    ).get("/me/notifications", headers=_AUTH).json()
    assert set(body["available_channels"]) == {"discord", "email", "sms"}
