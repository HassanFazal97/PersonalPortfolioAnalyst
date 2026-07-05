import uuid

from fastapi.testclient import TestClient

import app.main as main
from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}


def _client(monkeypatch, repo):
    # No `with`: skip lifespan (which would null app.state.repo without a DB) and
    # inject the fake repo directly, matching tests/test_macro_http.py.
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


def test_me_requires_auth(monkeypatch):
    assert _client(monkeypatch, FakeRepo()).get("/me").status_code == 401


def test_me_owner_defaults(monkeypatch):
    # Owner has no seeded row -> sensible defaults, plan pro, is_owner true.
    body = _client(monkeypatch, FakeRepo()).get("/me", headers=_AUTH).json()
    assert body["is_owner"] is True
    assert body["plan"] == "pro"
    assert body["timezone"] == "America/Toronto"


def test_patch_me_persists(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    client = _client(monkeypatch, repo)
    resp = client.patch(
        "/me",
        headers=_AUTH,
        json={"digest_enabled": False, "timezone": "America/Vancouver",
              "digest_send_time": "06:30"},
    )
    assert resp.status_code == 200
    after = client.get("/me", headers=_AUTH).json()
    assert after["digest_enabled"] is False
    assert after["timezone"] == "America/Vancouver"
    assert after["digest_send_time"] == "06:30"


def test_patch_me_rejects_bad_time(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    resp = _client(monkeypatch, repo).patch(
        "/me", headers=_AUTH, json={"digest_send_time": "99:99"}
    )
    assert resp.status_code == 400


def test_get_portfolio(monkeypatch):
    async def fake_portfolio(payload, ctx):
        return {"positions": [{"ticker": "NVDA", "quantity": 10}], "totals": {}}

    monkeypatch.setattr(main.portfolio, "get_portfolio", fake_portfolio)
    resp = _client(monkeypatch, FakeRepo()).get("/portfolio", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["positions"][0]["ticker"] == "NVDA"
