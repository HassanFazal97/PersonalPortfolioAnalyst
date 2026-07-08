"""Account-management endpoints: chat history, brokerage disconnect, delete account."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main
from app.config import DEFAULT_USER_ID, get_settings
from app.integrations.snaptrade.client import SnapTradeError
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}
SECRET = "test-jwt-secret-with-at-least-32-bytes-of-length"


def _client(monkeypatch, repo, *, jwt_secret=None):
    # No `with`: skip lifespan and inject the fake repo (matches tests/test_me.py).
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    if jwt_secret:
        monkeypatch.setenv("SUPABASE_JWT_SECRET", jwt_secret)
    else:
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_jwt(sub: str, email: str = "user@example.com") -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(
        json.dumps(
            {
                "sub": sub,
                "aud": "authenticated",
                "email": email,
                "exp": int(time.time()) + 3600,
            }
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(SECRET.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(sig)}"


async def _seed_chats(repo, user_id, n, *, start=None):
    start = start or datetime.now(timezone.utc)
    for i in range(n):
        rid = await repo.create_run(
            trigger="chat", user_message=f"q{i}", model="m",
            prompt_version="v1", user_id=user_id,
        )
        repo.runs[rid]["created_at"] = start + timedelta(minutes=i)
        await repo.finalize_run(rid, status="succeeded", final_answer=f"a{i}")


# ---- GET /chat/history -----------------------------------------------------


def test_chat_history_requires_auth(monkeypatch):
    assert _client(monkeypatch, FakeRepo()).get("/chat/history").status_code == 401


async def test_chat_history_shape_and_order(monkeypatch):
    repo = FakeRepo()
    await _seed_chats(repo, _OWNER, 3)
    # A digest run must not leak into chat history.
    await repo.create_run(
        trigger="digest", user_message="digest", model="m",
        prompt_version="v1", user_id=_OWNER,
    )
    body = _client(monkeypatch, repo).get("/chat/history", headers=_AUTH).json()
    turns = body["turns"]
    assert len(turns) == 6
    assert [t["role"] for t in turns] == ["user", "assistant"] * 3
    assert turns[0]["content"] == "q0"  # chronological: oldest first
    assert turns[-1]["content"] == "a2"
    assert all(t["created_at"] for t in turns)


async def test_chat_history_skips_unanswered_runs(monkeypatch):
    repo = FakeRepo()
    rid = await repo.create_run(
        trigger="chat", user_message="failed question", model="m",
        prompt_version="v1", user_id=_OWNER,
    )
    await repo.finalize_run(rid, status="failed", final_answer=None)
    turns = _client(monkeypatch, repo).get(
        "/chat/history", headers=_AUTH
    ).json()["turns"]
    assert [t["role"] for t in turns] == ["user"]


async def test_chat_history_limit(monkeypatch):
    repo = FakeRepo()
    await _seed_chats(repo, _OWNER, 8)
    turns = _client(monkeypatch, repo).get(
        "/chat/history?limit=4", headers=_AUTH
    ).json()["turns"]
    assert len(turns) == 4
    assert [t["content"] for t in turns] == ["q6", "a6", "q7", "a7"]


async def test_chat_history_scoped_to_user(monkeypatch):
    repo = FakeRepo()
    await _seed_chats(repo, uuid.uuid4(), 2)  # someone else's chats
    body = _client(monkeypatch, repo).get("/chat/history", headers=_AUTH).json()
    assert body["turns"] == []


# ---- DELETE /connection ----------------------------------------------------


def test_disconnect_requires_auth(monkeypatch):
    assert _client(monkeypatch, FakeRepo()).delete("/connection").status_code == 401


def test_disconnect_404_when_nothing_stored(monkeypatch):
    resp = _client(monkeypatch, FakeRepo()).delete("/connection", headers=_AUTH)
    assert resp.status_code == 404


async def test_disconnect_clears_local_even_when_remote_fails(monkeypatch):
    repo = FakeRepo()
    await repo.save_snaptrade_credentials(
        user_id=_OWNER, snaptrade_user_id="user-1", user_secret_enc=b"enc"
    )

    async def boom(repo_, user_id, settings):
        raise SnapTradeError("snaptrade down")

    monkeypatch.setattr(main, "service_for_user", boom)
    resp = _client(monkeypatch, repo).delete("/connection", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["disconnected"] is True
    assert body["remote_deleted"] is False
    assert body["local_cleared"] is True
    assert "snaptrade down" in body["remote_error"]
    assert await repo.get_snaptrade_credentials(_OWNER) is None


async def test_disconnect_deletes_remote_user(monkeypatch):
    repo = FakeRepo()
    await repo.save_snaptrade_credentials(
        user_id=_OWNER, snaptrade_user_id="user-1", user_secret_enc=b"enc"
    )
    deleted = []

    async def fake_service(repo_, user_id, settings):
        return SimpleNamespace(delete_user=lambda: deleted.append(user_id) or True)

    monkeypatch.setattr(main, "service_for_user", fake_service)
    body = _client(monkeypatch, repo).delete("/connection", headers=_AUTH).json()
    assert body["remote_deleted"] is True
    assert body["remote_error"] is None
    assert deleted == [_OWNER]
    assert await repo.get_snaptrade_credentials(_OWNER) is None


# ---- DELETE /me ------------------------------------------------------------


def test_delete_me_requires_auth(monkeypatch):
    assert _client(monkeypatch, FakeRepo()).delete("/me").status_code == 401


def test_delete_me_blocks_owner(monkeypatch):
    # The seeded owner backs the service token and background jobs.
    resp = _client(monkeypatch, FakeRepo()).delete("/me", headers=_AUTH)
    assert resp.status_code == 400


async def test_delete_me_removes_app_data(monkeypatch):
    repo = FakeRepo()
    auth_id = uuid.uuid4()
    uid = await repo.get_or_create_user(auth_id=auth_id, email="jane@example.com")
    await repo.upsert_position(
        ticker="NVDA", quantity=1, avg_cost=1, currency="CAD",
        account="TFSA", user_id=uid,
    )
    await _seed_chats(repo, uid, 2)
    client = _client(monkeypatch, repo, jwt_secret=SECRET)
    headers = {"Authorization": f"Bearer {_make_jwt(str(auth_id))}"}

    resp = client.delete("/me", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is True
    assert body["auth_user_deleted"] is False  # no service-role key configured
    assert await repo.get_user(uid) is None
    assert await repo.list_positions(user_id=uid) == []
    assert await repo.list_chat_runs(uid) == []


async def test_delete_me_reports_auth_deletion(monkeypatch):
    repo = FakeRepo()
    auth_id = uuid.uuid4()
    await repo.get_or_create_user(auth_id=auth_id, email="jane@example.com")

    async def fake_admin_delete(settings, aid):
        assert aid == auth_id
        return True

    monkeypatch.setattr(main, "_delete_supabase_auth_user", fake_admin_delete)
    client = _client(monkeypatch, repo, jwt_secret=SECRET)
    headers = {"Authorization": f"Bearer {_make_jwt(str(auth_id))}"}
    body = client.delete("/me", headers=headers).json()
    assert body == {"deleted": True, "auth_user_deleted": True}
