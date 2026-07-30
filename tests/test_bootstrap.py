"""GET /dashboard/bootstrap: aggregation, ETag, snapshot SWR, invalidation."""

import uuid

from fastapi.testclient import TestClient

import app.main as main
from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from app.perf import snapshot
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}

SECTIONS = set(snapshot.SECTION_NAMES)


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
    app.state.delivery_adapters = {}
    return TestClient(app)


def _fake_portfolio(positions=None):
    async def fake(payload, ctx):
        return {"positions": positions or [], "totals": {}}

    return fake


def test_bootstrap_requires_auth(monkeypatch):
    assert _client(monkeypatch, FakeRepo()).get("/dashboard/bootstrap").status_code == 401


def test_bootstrap_returns_all_sections(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    monkeypatch.setattr(main.portfolio, "get_portfolio", _fake_portfolio())
    body = _client(monkeypatch, repo).get("/dashboard/bootstrap", headers=_AUTH).json()
    assert body["v"] == 1
    assert set(body["sections"]) == SECTIONS
    for name in SECTIONS:
        assert "data" in body["sections"][name] or "error" in body["sections"][name]
    # me/portfolio must build cleanly on the happy path.
    assert body["sections"]["me"]["data"]["is_owner"] is True
    assert body["sections"]["portfolio"]["data"]["positions"] == []


def test_bootstrap_section_shapes_match_individual_endpoints(monkeypatch):
    """Golden parity: the client feeds bootstrap sections to the same
    renderers the individual endpoints feed — shapes must not drift."""
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    monkeypatch.setattr(
        main.portfolio,
        "get_portfolio",
        _fake_portfolio([{"ticker": "NVDA", "quantity": 10}]),
    )
    client = _client(monkeypatch, repo)
    boot = client.get("/dashboard/bootstrap", headers=_AUTH).json()["sections"]
    assert boot["me"]["data"] == client.get("/me", headers=_AUTH).json()
    assert boot["portfolio"]["data"] == client.get("/portfolio", headers=_AUTH).json()
    assert boot["watchlist"]["data"] == client.get("/watchlist", headers=_AUTH).json()
    assert (
        boot["notifications"]["data"]
        == client.get("/me/notifications", headers=_AUTH).json()
    )


def test_bootstrap_etag_304(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    monkeypatch.setattr(main.portfolio, "get_portfolio", _fake_portfolio())
    client = _client(monkeypatch, repo)
    first = client.get("/dashboard/bootstrap", headers=_AUTH)
    etag = first.headers["ETag"]
    assert first.headers["Cache-Control"].startswith("private")
    again = client.get(
        "/dashboard/bootstrap", headers={**_AUTH, "If-None-Match": etag}
    )
    assert again.status_code == 304


def test_warm_bootstrap_serves_snapshot_without_rebuilding(monkeypatch):
    """The SWR invariant: once the snapshot is warm, a GET must not re-run
    the section builders (no yfinance/SnapTrade inline)."""
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    monkeypatch.setattr(main.portfolio, "get_portfolio", _fake_portfolio())
    client = _client(monkeypatch, repo)
    assert client.get("/dashboard/bootstrap", headers=_AUTH).status_code == 200

    async def explode(payload, ctx):  # any rebuild would now blow up
        raise AssertionError("portfolio rebuilt inline on a warm request")

    monkeypatch.setattr(main.portfolio, "get_portfolio", explode)
    body = client.get("/dashboard/bootstrap", headers=_AUTH).json()
    assert body["sections"]["portfolio"]["data"]["positions"] == []
    assert body["refreshing"] == []


def test_write_invalidation_rebuilds_section(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    monkeypatch.setattr(main.portfolio, "get_portfolio", _fake_portfolio())
    client = _client(monkeypatch, repo)
    before = client.get("/dashboard/bootstrap", headers=_AUTH).json()
    assert before["sections"]["me"]["data"]["timezone"] == "America/Toronto"
    resp = client.patch(
        "/me", headers=_AUTH, json={"timezone": "America/Vancouver"}
    )
    assert resp.status_code == 200
    after = client.get("/dashboard/bootstrap", headers=_AUTH).json()
    assert after["sections"]["me"]["data"]["timezone"] == "America/Vancouver"


def test_failed_section_degrades_not_sinks(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")

    async def broken(payload, ctx):
        raise RuntimeError("yfinance down")

    monkeypatch.setattr(main.portfolio, "get_portfolio", broken)
    body = _client(monkeypatch, repo).get("/dashboard/bootstrap", headers=_AUTH).json()
    assert "error" in body["sections"]["portfolio"]
    assert "data" in body["sections"]["me"]


def test_failed_section_is_not_cached(monkeypatch):
    """An errored section must be rebuilt on the next request, not served
    as a cached failure."""
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")

    async def broken(payload, ctx):
        raise RuntimeError("transient")

    monkeypatch.setattr(main.portfolio, "get_portfolio", broken)
    client = _client(monkeypatch, repo)
    assert "error" in client.get("/dashboard/bootstrap", headers=_AUTH).json()["sections"]["portfolio"]
    monkeypatch.setattr(main.portfolio, "get_portfolio", _fake_portfolio())
    body = client.get("/dashboard/bootstrap", headers=_AUTH).json()
    assert body["sections"]["portfolio"]["data"]["positions"] == []
