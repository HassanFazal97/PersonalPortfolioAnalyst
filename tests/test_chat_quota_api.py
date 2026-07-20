"""Chat quota surfacing: /me.chat_quota, /chat 402 detail, per-plan budgets."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main
from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}


def _client(monkeypatch, repo):
    # No `with`: skip lifespan and inject the fake repo, as in tests/test_me.py.
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


def _as_user(monkeypatch, uid):
    """Route the request identity to a non-owner user (bearer binds owner)."""
    monkeypatch.setattr(main, "_user_id", lambda request: uid)


def _seed_chat_runs(repo, uid, n, *, age=timedelta(hours=1)):
    stamp = datetime.now(timezone.utc) - age
    for _ in range(n):
        repo.runs[uuid.uuid4()] = {
            "trigger": "chat",
            "user_id": uid,
            "status": "completed",
            "created_at": stamp,
        }


def _fake_run_agent(monkeypatch, repo, *, capture=None):
    """Replace the agent loop with a stub that records a chat run like the
    real loop would (so the post-run quota reflects the question just asked)."""

    async def fake(message, *, trigger, system_prompt, tools, budget, db,
                   user_id, **kwargs):
        if capture is not None:
            capture["budget"] = budget
            capture["system_prompt"] = system_prompt
            capture["history"] = kwargs.get("history")
        run_id = uuid.uuid4()
        repo.runs[run_id] = {
            "trigger": trigger,
            "user_id": user_id,
            "status": "completed",
            "created_at": datetime.now(timezone.utc),
        }
        return SimpleNamespace(
            run_id=run_id, answer="hi", status="completed", iterations=1,
            input_tokens=10, output_tokens=5, cost_usd=0.001, latency_ms=20,
            tool_summaries=[],
        )

    monkeypatch.setattr(main, "run_agent", fake)


def test_me_includes_chat_quota_for_free_user(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    _seed_chat_runs(repo, uid, 1)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    quota = client.get("/me", headers=_AUTH).json()["chat_quota"]
    settings = get_settings()
    assert quota["limit"] == settings.free_weekly_chat_limit
    assert quota["used"] == 1
    assert quota["remaining"] == settings.free_weekly_chat_limit - 1
    assert quota["window"] == "week"
    assert quota["resets_at"] is not None


def test_me_chat_quota_null_for_owner(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    client = _client(monkeypatch, repo)

    assert client.get("/me", headers=_AUTH).json()["chat_quota"] is None


def test_chat_402_detail_reaches_the_client(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    settings_limit = get_settings().free_weekly_chat_limit
    _seed_chat_runs(repo, uid, settings_limit)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post("/chat", json={"message": "hello"}, headers=_AUTH)
    assert resp.status_code == 402
    assert "free questions this week" in resp.json()["detail"]


def test_chat_response_carries_updated_quota(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    _fake_run_agent(monkeypatch, repo)

    data = client.post("/chat", json={"message": "hello"}, headers=_AUTH).json()
    settings = get_settings()
    assert data["chat_quota"]["used"] == 1
    assert data["chat_quota"]["remaining"] == settings.pro_daily_chat_limit - 1
    assert data["chat_quota"]["window"] == "day"


def test_chat_budget_is_per_plan(monkeypatch):
    settings = get_settings()
    for plan, expected in (
        ("free", settings.free_chat_max_cost_usd),
        ("pro", settings.pro_chat_max_cost_usd),
    ):
        repo = FakeRepo()
        uid = uuid.uuid4()
        repo.seed_user(uid, plan=plan)
        client = _client(monkeypatch, repo)
        _as_user(monkeypatch, uid)
        capture = {}
        _fake_run_agent(monkeypatch, repo, capture=capture)

        assert client.post(
            "/chat", json={"message": "hello"}, headers=_AUTH
        ).status_code == 200
        assert capture["budget"].max_cost_usd == expected


def test_owner_chat_uses_service_budget(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    client = _client(monkeypatch, repo)
    capture = {}
    _fake_run_agent(monkeypatch, repo, capture=capture)

    data = client.post("/chat", json={"message": "hello"}, headers=_AUTH).json()
    settings = get_settings()
    assert capture["budget"].max_cost_usd == settings.chat_max_cost_usd
    assert data["chat_quota"] is None
