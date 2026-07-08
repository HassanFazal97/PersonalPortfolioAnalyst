"""Email unsubscribe (CASL): signed tokens, the /unsubscribe endpoint, the
Resend adapter's footer link + List-Unsubscribe headers, and the dispatcher
stamping the link into email payloads."""

import uuid
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

import app.delivery.adapters.email_resend as resend_mod
from app.config import DEFAULT_USER_ID, get_settings
from app.delivery.adapters.base import SendResult
from app.delivery.adapters.email_resend import ResendEmailAdapter
from app.delivery.dispatcher import Dispatcher
from app.delivery.unsubscribe import sign_token, unsubscribe_url, verify_token
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
SECRET = "unsubscribe-test-secret"
BASE_URL = "https://app.example.com"


# --- token sign/verify ---------------------------------------------------------


def test_token_roundtrip():
    token = sign_token(SECRET, _OWNER, "email")
    assert verify_token(SECRET, token) == (_OWNER, "email")


def test_token_is_stable_per_user_channel():
    assert sign_token(SECRET, _OWNER, "email") == sign_token(SECRET, _OWNER, "email")
    assert sign_token(SECRET, _OWNER, "email") != sign_token(SECRET, _OWNER, "sms")


def test_tampered_channel_is_rejected():
    token = sign_token(SECRET, _OWNER, "email")
    user_part, _, sig = token.rsplit(":", 2)
    assert verify_token(SECRET, f"{user_part}:sms:{sig}") is None


def test_tampered_user_is_rejected():
    token = sign_token(SECRET, _OWNER, "email")
    _, channel, sig = token.rsplit(":", 2)
    assert verify_token(SECRET, f"{uuid.uuid4()}:{channel}:{sig}") is None


def test_wrong_secret_is_rejected():
    token = sign_token(SECRET, _OWNER, "email")
    assert verify_token("other-secret", token) is None


def test_garbage_tokens_are_rejected():
    assert verify_token(SECRET, "") is None
    assert verify_token(SECRET, "not-a-token") is None
    assert verify_token(SECRET, "a:b") is None
    assert verify_token(SECRET, "a:b:c:d") is None
    assert verify_token("", sign_token(SECRET, _OWNER, "email")) is None


def test_non_uuid_user_is_rejected():
    import hashlib
    import hmac as hmac_mod

    sig = hmac_mod.new(SECRET.encode(), b"nope:email", hashlib.sha256).hexdigest()
    assert verify_token(SECRET, f"nope:email:{sig}") is None


def test_unsubscribe_url_needs_base_and_secret():
    ok = SimpleNamespace(unsubscribe_secret=SECRET, api_token="", public_base_url=BASE_URL)
    url = unsubscribe_url(ok, _OWNER, "email")
    assert url.startswith(f"{BASE_URL}/unsubscribe?token=")
    no_base = SimpleNamespace(unsubscribe_secret=SECRET, api_token="", public_base_url="")
    assert unsubscribe_url(no_base, _OWNER, "email") is None
    no_secret = SimpleNamespace(unsubscribe_secret="", api_token="", public_base_url=BASE_URL)
    assert unsubscribe_url(no_secret, _OWNER, "email") is None


def test_unsubscribe_secret_falls_back_to_api_token():
    from app.delivery.unsubscribe import unsubscribe_secret

    assert unsubscribe_secret(SimpleNamespace(unsubscribe_secret="s", api_token="t")) == "s"
    assert unsubscribe_secret(SimpleNamespace(unsubscribe_secret="", api_token="t")) == "t"


# --- GET/POST /unsubscribe -------------------------------------------------------


def _client(monkeypatch, repo):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", SECRET)
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE_URL)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    app.state.delivery_scheduler = None
    app.state.delivery_adapters = {}
    return TestClient(app)


async def _seed_email_channel(repo, user_id=_OWNER, destination="u@example.com"):
    repo.seed_user(user_id, email=destination)
    await repo.upsert_notification_channel(
        user_id, channel="email", destination=destination
    )
    await repo.mark_channel_verified(user_id, "email")


def test_unsubscribe_marks_channel_opted_out(monkeypatch):
    import asyncio

    repo = FakeRepo()
    asyncio.run(_seed_email_channel(repo))
    token = sign_token(SECRET, _OWNER, "email")
    resp = _client(monkeypatch, repo).get("/unsubscribe", params={"token": token})
    assert resp.status_code == 200
    assert "unsubscribed" in resp.text.lower()
    row = repo._notification_channels[(_OWNER, "email")]
    assert row.opted_out_at is not None


def test_unsubscribe_one_click_post(monkeypatch):
    import asyncio

    repo = FakeRepo()
    asyncio.run(_seed_email_channel(repo))
    token = sign_token(SECRET, _OWNER, "email")
    resp = _client(monkeypatch, repo).post("/unsubscribe", params={"token": token})
    assert resp.status_code == 200
    assert repo._notification_channels[(_OWNER, "email")].opted_out_at is not None


def test_unsubscribe_needs_no_bearer_token(monkeypatch):
    # No Authorization header anywhere in these requests: the token is the auth.
    repo = FakeRepo()
    token = sign_token(SECRET, _OWNER, "email")
    resp = _client(monkeypatch, repo).get("/unsubscribe", params={"token": token})
    assert resp.status_code == 200  # valid token, channel simply not registered


def test_unsubscribe_invalid_token_is_generic_400(monkeypatch):
    repo = FakeRepo()
    client = _client(monkeypatch, repo)
    for bad in ["", "garbage", f"{_OWNER}:email:deadbeef"]:
        resp = client.get("/unsubscribe", params={"token": bad})
        assert resp.status_code == 400
        assert "isn't valid" in resp.text


def test_unsubscribe_tampered_token_does_not_opt_out(monkeypatch):
    import asyncio

    repo = FakeRepo()
    asyncio.run(_seed_email_channel(repo))
    token = sign_token("attacker-secret", _OWNER, "email")
    resp = _client(monkeypatch, repo).get("/unsubscribe", params={"token": token})
    assert resp.status_code == 400
    assert repo._notification_channels[(_OWNER, "email")].opted_out_at is None


# --- Resend adapter: footer link + headers ---------------------------------------


class StubClient:
    def __init__(self, status_code=200, json_body=None):
        self.requests = []
        self._status = status_code
        self._json = json_body or {"id": "em_1"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return httpx.Response(self._status, json=self._json)


async def test_resend_includes_unsubscribe_footer_and_headers(monkeypatch):
    stub = StubClient()
    monkeypatch.setattr(resend_mod.httpx, "AsyncClient", lambda **kw: stub)
    adapter = ResendEmailAdapter(api_key="k", from_addr="Digest <d@x.com>")
    url = f"{BASE_URL}/unsubscribe?token=abc"
    result = await adapter.send(
        "u@y.com", "digest body", {"subject": "Morning digest", "unsubscribe_url": url}
    )
    assert result.ok
    sent = stub.requests[0][1]["json"]
    assert sent["text"].startswith("digest body")
    assert url in sent["text"]
    assert "unsubscribe" in sent["text"].lower()
    assert sent["headers"]["List-Unsubscribe"] == f"<{url}>"
    assert sent["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


async def test_resend_without_link_sends_no_unsubscribe_headers(monkeypatch):
    stub = StubClient()
    monkeypatch.setattr(resend_mod.httpx, "AsyncClient", lambda **kw: stub)
    adapter = ResendEmailAdapter(api_key="k", from_addr="d@x.com")
    await adapter.send("u@y.com", "body", {"subject": "s"})
    sent = stub.requests[0][1]["json"]
    assert "headers" not in sent
    assert sent["text"] == "body"


# --- dispatcher stamps the link into email payloads ------------------------------


class FakeQueueRepo:
    def __init__(self, messages):
        self.messages = messages

    async def claim_due_outbound(self, limit=25, *, lease_seconds=120):
        return self.messages[:limit]

    async def record_send_result(self, msg_id, **kwargs):
        return "sent"


class CaptureAdapter:
    channel = "email"

    def __init__(self):
        self.calls = []

    async def send(self, destination, body, payload):
        self.calls.append((destination, body, payload))
        return SendResult(ok=True)


def _msg(channel="email"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=_OWNER,
        channel=channel,
        destination="u@example.com",
        body="hello",
        payload={"kind": "digest", "subject": "Morning digest"},
        attempts=0,
    )


async def test_dispatcher_adds_unsubscribe_url_to_email_payload():
    msg = _msg()
    adapter = CaptureAdapter()
    dispatcher = Dispatcher(
        FakeQueueRepo([msg]),
        {"email": adapter},
        unsubscribe_url_for=lambda uid, ch: f"{BASE_URL}/unsubscribe?token={uid}-{ch}",
    )
    await dispatcher.tick()
    payload = adapter.calls[0][2]
    assert payload["unsubscribe_url"] == f"{BASE_URL}/unsubscribe?token={_OWNER}-email"
    assert payload["subject"] == "Morning digest"
    # The stored row's payload is not mutated.
    assert "unsubscribe_url" not in msg.payload


async def test_dispatcher_leaves_non_email_payloads_alone():
    msg = _msg(channel="discord")
    adapter = CaptureAdapter()
    adapter.channel = "discord"
    dispatcher = Dispatcher(
        FakeQueueRepo([msg]),
        {"discord": adapter},
        unsubscribe_url_for=lambda uid, ch: "should-not-appear",
    )
    await dispatcher.tick()
    assert "unsubscribe_url" not in adapter.calls[0][2]


async def test_dispatcher_without_builder_keeps_payload():
    msg = _msg()
    adapter = CaptureAdapter()
    await Dispatcher(FakeQueueRepo([msg]), {"email": adapter}).tick()
    assert "unsubscribe_url" not in adapter.calls[0][2]
