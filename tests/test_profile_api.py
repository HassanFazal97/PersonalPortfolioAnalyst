"""API tests for the investor-profile endpoints (PUT /me/profile,
POST /me/profile/dismiss, GET /me/profile/projections) and the /me payload."""

import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from app.tools import portfolio_risk
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}


def _client(monkeypatch, repo):
    # Same lifespan-skipping pattern as tests/test_me.py.
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


def test_me_includes_default_profile(monkeypatch):
    body = _client(monkeypatch, FakeRepo()).get("/me", headers=_AUTH).json()
    prof = body["profile"]
    assert prof["is_default"] is True
    assert prof["completed"] is False
    assert prof["archetype"] == "long_term_growth"


def test_put_profile_derives_archetype(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    client = _client(monkeypatch, repo)
    resp = client.put(
        "/me/profile",
        headers=_AUTH,
        json={
            "experience": "1_5y",
            "goals": ["short_term_gains"],
            "horizon": "weeks_months",
            "chosen_posture": "aggressive",
        },
    )
    assert resp.status_code == 200
    prof = resp.json()["profile"]
    assert prof["archetype"] == "swing_trader"
    assert prof["risk_tolerance"] == 8  # aggressive posture mapping
    assert prof["completed"] is True
    assert prof["is_default"] is False


def test_put_profile_current_posture_keeps_default_risk(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    client = _client(monkeypatch, repo)
    resp = client.put(
        "/me/profile",
        headers=_AUTH,
        json={"horizon": "years", "goals": [], "chosen_posture": "current"},
    )
    assert resp.status_code == 200
    assert resp.json()["profile"]["risk_tolerance"] == 5


@pytest.mark.parametrize(
    "payload",
    [
        {"experience": "veteran"},
        {"horizon": "eons"},
        {"goals": ["moon"]},
        {"risk_tolerance": 11},
        {"risk_tolerance": 0},
        {"chosen_posture": "yolo"},
    ],
)
def test_put_profile_rejects_unknown_values(monkeypatch, payload):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    resp = _client(monkeypatch, repo).put(
        "/me/profile", headers=_AUTH, json=payload
    )
    assert resp.status_code == 400


def test_dismiss_is_idempotent_and_persists(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    client = _client(monkeypatch, repo)
    first = client.post("/me/profile/dismiss", headers=_AUTH)
    assert first.status_code == 200
    assert first.json()["profile"]["prompt_dismissed"] is True
    again = client.post("/me/profile/dismiss", headers=_AUTH)
    assert again.status_code == 200
    assert again.json()["profile"]["prompt_dismissed"] is True


def test_projections_falls_back_without_positions(monkeypatch):
    """No analyzable portfolio -> illustrative fans, never a dead end, and
    crucially NOT a 402 (the endpoint is deliberately ungated)."""
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="free")

    async def fake_get_portfolio(payload, ctx):
        return {"positions": [], "totals": {}}

    monkeypatch.setattr(
        portfolio_risk.portfolio, "get_portfolio", fake_get_portfolio
    )
    resp = _client(monkeypatch, repo).get(
        "/me/profile/projections", headers=_AUTH
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["fallback"] is True
    for key in ("defensive", "current", "aggressive"):
        p = body["postures"][key]
        assert len(p["bands_pct"]["p50"]) > 10
        assert p["terminal_pct"]["p5"] < p["terminal_pct"]["p95"]
    # Fallback vols are ordered defensive < current < aggressive.
    vols = [body["postures"][k]["annualized_vol_pct"]
            for k in ("defensive", "current", "aggressive")]
    assert vols == sorted(vols)


@pytest.mark.asyncio
async def test_posture_scaling_property(monkeypatch):
    """Scaling the covariance by k**2 scales portfolio vol by exactly k."""
    rng = np.random.default_rng(7)
    matrix = rng.normal(0, 0.01, size=(300, 2))
    rm = type(
        "RM",
        (),
        {"matrix": matrix, "tickers": ["A", "B"], "n_assets": 2, "excluded": {},
         "benchmark_returns": None},
    )()
    loaded = portfolio_risk._Loaded(
        rm, np.array([100.0, 200.0]), {"A": 100.0, "B": 200.0}, []
    )

    async def fake_load(payload, ctx, *, with_benchmark):
        return loaded

    monkeypatch.setattr(portfolio_risk, "_load_portfolio_returns", fake_load)
    out = await portfolio_risk.risk_posture_projections(ctx=None)
    assert out["available"] is True
    assert out["portfolio_value_cad"] == 300.0
    # Payload values are rounded to 2 decimals, hence the absolute tolerance.
    cur = out["postures"]["current"]["annualized_vol_pct"]
    assert out["postures"]["defensive"]["annualized_vol_pct"] == pytest.approx(
        0.6 * cur, abs=0.01
    )
    assert out["postures"]["aggressive"]["annualized_vol_pct"] == pytest.approx(
        1.5 * cur, abs=0.01
    )
    # Wider vol -> wider outcome fan and (with zero drift) more losing runs.
    assert (
        out["postures"]["aggressive"]["terminal_pct"]["p5"]
        < out["postures"]["defensive"]["terminal_pct"]["p5"]
    )
    assert out["postures"]["current"]["terminal_cad"]["p50"] > 0
