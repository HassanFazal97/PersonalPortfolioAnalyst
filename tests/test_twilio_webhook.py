"""Twilio inbound webhook: signature validation and STOP/HELP/START handling."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.delivery.twilio_inbound import (
    EMPTY_TWIML,
    HELP_TWIML,
    compute_signature,
    handle_inbound_sms,
)
from app.main import create_app

AUTH_TOKEN = "twilio-test-token"
BASE_URL = "https://app.example.com"
WEBHOOK_URL = f"{BASE_URL}/webhooks/twilio/sms"


class FakeOptOutRepo:
    def __init__(self):
        self.calls = []

    async def set_opt_out_by_destination(self, *, channel, destination, opted_out):
        self.calls.append((channel, destination, opted_out))
        return 1


# --- keyword handling (unit) --------------------------------------------------


async def test_stop_sets_opt_out():
    repo = FakeOptOutRepo()
    twiml = await handle_inbound_sms(repo, from_number="+14165551234", body=" stop ")
    assert twiml == EMPTY_TWIML
    assert repo.calls == [("sms", "+14165551234", True)]


async def test_start_clears_opt_out():
    repo = FakeOptOutRepo()
    await handle_inbound_sms(repo, from_number="+14165551234", body="START")
    assert repo.calls == [("sms", "+14165551234", False)]


async def test_help_replies_without_state_change():
    repo = FakeOptOutRepo()
    twiml = await handle_inbound_sms(repo, from_number="+1416", body="help")
    assert twiml == HELP_TWIML
    assert repo.calls == []


async def test_ordinary_message_is_ignored():
    repo = FakeOptOutRepo()
    twiml = await handle_inbound_sms(repo, from_number="+1416", body="what is NVDA doing")
    assert twiml == EMPTY_TWIML
    assert repo.calls == []


# --- route + signature (integration) -------------------------------------------


def _client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "t")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE_URL)
    get_settings.cache_clear()
    return TestClient(create_app())


def _signed_post(client, params, *, signature=None):
    sig = signature or compute_signature(AUTH_TOKEN, WEBHOOK_URL, params)
    return client.post(
        "/webhooks/twilio/sms", data=params, headers={"X-Twilio-Signature": sig}
    )


def test_webhook_rejects_bad_signature(monkeypatch):
    with _client(monkeypatch) as client:
        resp = _signed_post(
            client, {"From": "+1416", "Body": "STOP"}, signature="bogus"
        )
    assert resp.status_code == 403


def test_webhook_rejects_missing_signature(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.post("/webhooks/twilio/sms", data={"From": "+1", "Body": "STOP"})
    assert resp.status_code == 403


def test_webhook_needs_no_bearer_token_but_valid_signature(monkeypatch):
    # DATABASE_URL is empty so repo is None -> route fails at _require_repo with
    # 503, proving the request got past both bearer auth and signature check.
    with _client(monkeypatch) as client:
        resp = _signed_post(client, {"From": "+14165551234", "Body": "HELP"})
    assert resp.status_code == 503
