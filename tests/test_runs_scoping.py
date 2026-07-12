"""Tenant isolation on the run-inspection endpoints.

GET /runs and GET /runs/{id} expose full chat/digest trajectories, so a
signed-in user must only ever see their own rows; the owner/service token
keeps unscoped access for ops debugging.
"""

import base64
import hashlib
import hmac
import json
import time
import uuid

from fastapi.testclient import TestClient

from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}
SECRET = "test-jwt-secret-with-at-least-32-bytes-of-length"


def _client(monkeypatch, repo):
    # No `with`: skip lifespan and inject the fake repo (matches tests/test_me.py).
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwt_auth(sub: str) -> dict:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(
        json.dumps(
            {
                "sub": sub,
                "aud": "authenticated",
                "email": f"{sub}@example.com",
                "exp": int(time.time()) + 3600,
            }
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(SECRET.encode(), signing_input, hashlib.sha256).digest()
    return {"Authorization": f"Bearer {header}.{payload}.{_b64(sig)}"}


async def _seed_run(repo, user_id, message):
    rid = await repo.create_run(
        trigger="chat", user_message=message, model="m",
        prompt_version="v1", user_id=user_id,
    )
    await repo.finalize_run(rid, status="succeeded", final_answer=f"re: {message}")
    return rid


def _setup(monkeypatch):
    repo = FakeRepo()
    client = _client(monkeypatch, repo)
    auth_a = _jwt_auth(str(uuid.uuid4()))
    auth_b = _jwt_auth(str(uuid.uuid4()))
    # First authenticated call provisions each user; then look up their ids.
    assert client.get("/me", headers=auth_a).status_code == 200
    assert client.get("/me", headers=auth_b).status_code == 200
    ids = list(repo._users_by_auth.values())
    user_a, user_b = ids[0], ids[1]
    return repo, client, auth_a, auth_b, user_a, user_b


def test_list_runs_scoped_to_caller(monkeypatch):
    repo, client, auth_a, auth_b, user_a, user_b = _setup(monkeypatch)
    import asyncio

    asyncio.run(_seed_run(repo, user_a, "a-secret"))
    asyncio.run(_seed_run(repo, user_b, "b-secret"))

    a_runs = client.get("/runs", headers=auth_a).json()["runs"]
    assert [r["user_message"] for r in a_runs] == ["a-secret"]

    b_runs = client.get("/runs", headers=auth_b).json()["runs"]
    assert [r["user_message"] for r in b_runs] == ["b-secret"]

    owner_runs = client.get("/runs", headers=_AUTH).json()["runs"]
    assert {r["user_message"] for r in owner_runs} == {"a-secret", "b-secret"}


def test_get_run_denies_other_users(monkeypatch):
    repo, client, auth_a, auth_b, user_a, user_b = _setup(monkeypatch)
    import asyncio

    rid = asyncio.run(_seed_run(repo, user_a, "a-secret"))

    assert client.get(f"/runs/{rid}", headers=auth_a).status_code == 200
    # Another user gets 404 (not 403): run ids must not be probeable.
    assert client.get(f"/runs/{rid}", headers=auth_b).status_code == 404
    # Owner/service token retains access for ops debugging.
    assert client.get(f"/runs/{rid}", headers=_AUTH).status_code == 200
