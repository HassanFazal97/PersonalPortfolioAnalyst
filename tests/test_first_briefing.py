"""POST /digest/first — onboarding's instant first briefing."""

import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main
from app.config import get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_AUTH = {"Authorization": "Bearer test-token"}


def _client(monkeypatch, repo):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


def _seed_position(repo, uid):
    if not hasattr(repo, "_position_rows"):
        repo._position_rows = {}
    repo._position_rows[(uid, "NVDA", "Manual")] = SimpleNamespace(
        user_id=uid, ticker="NVDA", quantity=1, avg_cost=1,
        currency="USD", account="Manual",
    )


def test_first_briefing_runs_once_in_background(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    _seed_position(repo, uid)
    client = _client(monkeypatch, repo)
    monkeypatch.setattr(main, "_user_id", lambda request: uid)

    ran = []

    async def fake_pipeline(repo_, *, user_id, force):
        ran.append(user_id)
        return {"status": "completed"}

    async def no_digest(repo_, *, user_id, tz):
        return None

    monkeypatch.setattr(main, "run_digest_pipeline", fake_pipeline)
    monkeypatch.setattr(main, "get_latest_digest", no_digest)

    resp = client.post("/digest/first", headers=_AUTH)
    assert resp.status_code == 202
    assert resp.json()["status"] == "started"
    # TestClient runs the loop to completion, so the background task is done.
    assert ran == [uid]
    assert (uid, "first_briefing") in repo.funnel_events


def test_first_briefing_noop_when_digest_exists(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    _seed_position(repo, uid)
    client = _client(monkeypatch, repo)
    monkeypatch.setattr(main, "_user_id", lambda request: uid)

    async def has_digest(repo_, *, user_id, tz):
        return {"body": "existing"}

    monkeypatch.setattr(main, "get_latest_digest", has_digest)
    assert client.post("/digest/first", headers=_AUTH).json()["status"] == "exists"


def test_first_briefing_requires_holdings(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid)
    client = _client(monkeypatch, repo)
    monkeypatch.setattr(main, "_user_id", lambda request: uid)

    async def no_digest(repo_, *, user_id, tz):
        return None

    monkeypatch.setattr(main, "get_latest_digest", no_digest)
    assert client.post("/digest/first", headers=_AUTH).status_code == 400
