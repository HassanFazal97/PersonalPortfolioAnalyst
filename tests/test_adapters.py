"""Provider adapters against a monkeypatched httpx.AsyncClient."""

import httpx
import pytest

import app.delivery.adapters.discord as discord_mod
import app.delivery.adapters.email_resend as resend_mod
import app.delivery.adapters.twilio_sms as twilio_mod
from app.delivery.adapters.discord import DiscordAdapter, _chunk
from app.delivery.adapters.email_resend import ResendEmailAdapter
from app.delivery.adapters.twilio_sms import TwilioSMSAdapter
from app.delivery.channels import mask_destination, validate_destination

WEBHOOK = "https://discord.com/api/webhooks/123/token"


class StubClient:
    """Records posts and replies with a scripted response."""

    def __init__(self, status_code=204, json_body=None, exc=None):
        self.requests = []
        self._status = status_code
        self._json = json_body or {}
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        if self._exc:
            raise self._exc
        self.requests.append((url, kwargs))
        return httpx.Response(self._status, json=self._json)


def _patch(monkeypatch, module, stub):
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kw: stub)


# --- discord -----------------------------------------------------------------


async def test_discord_success(monkeypatch):
    stub = StubClient(status_code=204)
    _patch(monkeypatch, discord_mod, stub)
    result = await DiscordAdapter().send(WEBHOOK, "hi", {})
    assert result.ok
    assert stub.requests[0][1]["json"] == {"content": "hi"}


async def test_discord_deleted_webhook_is_permanent(monkeypatch):
    _patch(monkeypatch, discord_mod, StubClient(status_code=404))
    result = await DiscordAdapter().send(WEBHOOK, "hi", {})
    assert not result.ok and result.permanent


async def test_discord_rate_limit_is_transient(monkeypatch):
    _patch(monkeypatch, discord_mod, StubClient(status_code=429))
    result = await DiscordAdapter().send(WEBHOOK, "hi", {})
    assert not result.ok and not result.permanent


async def test_discord_rejects_non_webhook_url():
    result = await DiscordAdapter().send("https://evil.example/x", "hi", {})
    assert not result.ok and result.permanent


async def test_discord_network_error_is_transient(monkeypatch):
    _patch(monkeypatch, discord_mod, StubClient(exc=httpx.ConnectError("down")))
    result = await DiscordAdapter().send(WEBHOOK, "hi", {})
    assert not result.ok and not result.permanent


def test_discord_chunks_long_bodies():
    chunks = _chunk("x" * 4500)
    assert [len(c) for c in chunks] == [2000, 2000, 500]


# --- resend email -------------------------------------------------------------


async def test_resend_success_sends_subject(monkeypatch):
    stub = StubClient(status_code=200, json_body={"id": "em_1"})
    _patch(monkeypatch, resend_mod, stub)
    adapter = ResendEmailAdapter(api_key="k", from_addr="Digest <d@x.com>")
    result = await adapter.send("u@y.com", "body", {"subject": "Morning digest"})
    assert result.ok and result.provider_message_id == "em_1"
    sent = stub.requests[0][1]["json"]
    assert sent["to"] == ["u@y.com"]
    assert sent["subject"] == "Morning digest"


async def test_resend_4xx_is_permanent_5xx_transient(monkeypatch):
    adapter = ResendEmailAdapter(api_key="k", from_addr="d@x.com")
    _patch(monkeypatch, resend_mod, StubClient(status_code=422, json_body={"message": "bad"}))
    result = await adapter.send("u@y.com", "b", {})
    assert not result.ok and result.permanent
    _patch(monkeypatch, resend_mod, StubClient(status_code=500))
    result = await adapter.send("u@y.com", "b", {})
    assert not result.ok and not result.permanent


# --- twilio sms ----------------------------------------------------------------


def _twilio():
    return TwilioSMSAdapter(account_sid="AC1", auth_token="t", from_number="+15005550006")


async def test_twilio_success(monkeypatch):
    stub = StubClient(status_code=201, json_body={"sid": "SM1"})
    _patch(monkeypatch, twilio_mod, stub)
    result = await _twilio().send("+14165551234", "hi", {})
    assert result.ok and result.provider_message_id == "SM1"
    url, kwargs = stub.requests[0]
    assert "AC1/Messages.json" in url
    assert kwargs["data"]["To"] == "+14165551234"


@pytest.mark.parametrize("code", [21211, 21610])
async def test_twilio_permanent_error_codes(monkeypatch, code):
    stub = StubClient(status_code=400, json_body={"code": code, "message": "no"})
    _patch(monkeypatch, twilio_mod, stub)
    result = await _twilio().send("+1416", "hi", {})
    assert not result.ok and result.permanent


async def test_twilio_5xx_is_transient(monkeypatch):
    _patch(monkeypatch, twilio_mod, StubClient(status_code=503, json_body={}))
    result = await _twilio().send("+14165551234", "hi", {})
    assert not result.ok and not result.permanent


# --- destination validation -----------------------------------------------------


def test_validate_destination_matrix():
    assert validate_destination("sms", "+14165551234") is None
    assert validate_destination("sms", "4165551234") is not None
    assert validate_destination("email", "a@b.com") is None
    assert validate_destination("email", "not-an-email") is not None
    assert validate_destination("discord", WEBHOOK) is None
    assert validate_destination("discord", "https://evil.example/hook") is not None
    assert validate_destination("telegram", "x") is not None


def test_mask_destination():
    assert mask_destination("sms", "+14165551234") == "+1•••••1234"
    assert mask_destination("email", "fazal@gmail.com") == "f•••@gmail.com"
    assert mask_destination("discord", WEBHOOK).endswith("oken")
