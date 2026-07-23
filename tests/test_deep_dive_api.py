"""/deep-dive routes: Pro gating, quotas, concurrency, tenant scoping."""

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
    monkeypatch.setattr(main, "_user_id", lambda request: uid)


def _seed_position(repo, uid):
    if not hasattr(repo, "_position_rows"):
        repo._position_rows = {}
    repo._position_rows[(uid, "NVDA", "TFSA")] = SimpleNamespace(
        user_id=uid, ticker="NVDA", quantity=1, avg_cost=1,
        currency="USD", account="TFSA",
    )


def _fake_pipeline(monkeypatch, *, status="completed"):
    calls = []

    async def fake(repo, *, user_id, report_id, run_id, client=None, on_event=None):
        calls.append({"user_id": user_id, "report_id": report_id})
        if on_event is not None:
            await on_event({"type": "dd_stage", "stage": "plan", "status": "started"})
        await repo.update_deep_dive_report(
            report_id, status=status, summary="s", report={"overview": "o"}
        )
        return {"report_id": str(report_id), "status": status}

    monkeypatch.setattr(main, "run_deep_dive", fake)
    return calls


def test_deep_dive_free_user_is_403(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post("/deep-dive", headers=_AUTH)
    assert resp.status_code == 403
    assert "Pro" in resp.json()["detail"]


def test_deep_dive_starts_for_pro(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    _seed_position(repo, uid)
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    _fake_pipeline(monkeypatch)

    resp = client.post("/deep-dive", headers=_AUTH)
    assert resp.status_code == 202
    body = resp.json()
    assert "report_id" in body and "run_id" in body
    # The report + anchor run rows are created synchronously by the route
    # (the pipeline itself runs as a background task).
    assert len(repo.deep_dive_reports) == 1
    assert any(r["trigger"] == "deep_dive" for r in repo.runs.values())


def test_deep_dive_requires_positions(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)
    resp = client.post("/deep-dive", headers=_AUTH)  # no positions seeded
    assert resp.status_code == 400
    assert "brokerage" in resp.json()["detail"]


def test_deep_dive_weekly_quota_429(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    limit = get_settings().deep_dive_weekly_limit
    now = datetime.now(timezone.utc)
    repo.deep_dive_reports = {}
    for i in range(limit):
        rid = uuid.uuid4()
        repo.deep_dive_reports[rid] = SimpleNamespace(
            id=rid, user_id=uid, run_id=uuid.uuid4(), status="completed",
            report=None, summary=None, progress={}, cost_usd=None,
            created_at=now - timedelta(days=1), completed_at=now,
        )

    resp = client.post("/deep-dive", headers=_AUTH)
    assert resp.status_code == 429
    assert "unlocks" in resp.json()["detail"]


def test_deep_dive_monthly_cap_402(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    repo._cost_override[uid] = 99.0
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.post("/deep-dive", headers=_AUTH)
    assert resp.status_code == 402


def test_deep_dive_report_is_tenant_scoped_404(monkeypatch):
    repo = FakeRepo()
    owner_uid = uuid.uuid4()
    intruder = uuid.uuid4()
    repo.seed_user(owner_uid, plan="pro")
    repo.seed_user(intruder, plan="pro")
    rid = uuid.uuid4()
    repo.deep_dive_reports = {
        rid: SimpleNamespace(
            id=rid, user_id=owner_uid, run_id=uuid.uuid4(), status="completed",
            report={"overview": "o"}, summary="s", progress={}, cost_usd=0.5,
            created_at=datetime.now(timezone.utc), completed_at=None,
        )
    }
    client = _client(monkeypatch, repo)

    _as_user(monkeypatch, intruder)
    assert client.get(f"/deep-dive/{rid}", headers=_AUTH).status_code == 404

    _as_user(monkeypatch, owner_uid)
    data = client.get(f"/deep-dive/{rid}", headers=_AUTH).json()
    assert data["status"] == "completed"
    assert data["report"]["overview"] == "o"


def test_deep_dive_list_returns_own_reports(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    rid = uuid.uuid4()
    repo.deep_dive_reports = {
        rid: SimpleNamespace(
            id=rid, user_id=uid, run_id=uuid.uuid4(), status="partial",
            report=None, summary="s", progress={"plan": "completed"},
            cost_usd=None, created_at=datetime.now(timezone.utc), completed_at=None,
        )
    }
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    data = client.get("/deep-dive", headers=_AUTH).json()
    assert len(data["reports"]) == 1
    assert data["reports"][0]["status"] == "partial"


def test_deep_dive_events_snapshot_for_finished_report(monkeypatch):
    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="pro")
    rid = uuid.uuid4()
    repo.deep_dive_reports = {
        rid: SimpleNamespace(
            id=rid, user_id=uid, run_id=uuid.uuid4(), status="completed",
            report=None, summary=None, progress={"plan": "completed"},
            cost_usd=None, created_at=datetime.now(timezone.utc), completed_at=None,
        )
    }
    client = _client(monkeypatch, repo)
    _as_user(monkeypatch, uid)

    resp = client.get(f"/deep-dive/{rid}/events", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "event: dd_snapshot" in resp.text
    assert '"plan": "completed"' in resp.text
