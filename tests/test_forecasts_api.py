"""GET /forecasts/calibration: auth gate, payload shape, TTL cache."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main
from app.config import get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_AUTH = {"Authorization": "Bearer test-token"}


class ForecastFakeRepo(FakeRepo):
    def __init__(self):
        super().__init__()
        self.resolved_forecasts = []
        self.status_counts = {"open": 0, "resolved": 0}

    async def list_forecasts(self, *, source=None, status=None, since=None, limit=5000):
        return self.resolved_forecasts

    async def count_forecasts_by_status(self):
        return self.status_counts


def _client(monkeypatch, repo):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()
    main._calibration_cache.clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    app.state.delivery_adapters = {}
    return TestClient(app)


def _resolved_row(family: str, outcome: str):
    return SimpleNamespace(
        family_key=family,
        source="picks",
        claim_type="relative_performance",
        confidence_verbal="high",
        outcome=outcome,
        brier=0.0625,
        probability=0.75,
    )


def test_calibration_requires_auth(monkeypatch):
    client = _client(monkeypatch, ForecastFakeRepo())
    assert client.get("/forecasts/calibration").status_code == 401


def test_calibration_payload_shape(monkeypatch):
    repo = ForecastFakeRepo()
    repo.status_counts = {"open": 3, "resolved": 2}
    repo.resolved_forecasts = [_resolved_row("A", "hit"), _resolved_row("B", "miss")]
    body = _client(monkeypatch, repo).get("/forecasts/calibration", headers=_AUTH).json()
    assert body["counts"] == {"open": 3, "resolved": 2}
    cal = body["calibration"]
    assert cal["overall"]["families"] == 2
    assert cal["overall"]["hit_rate_pct"] == 50.0
    # Two families is far under the >=30 public gate: bucket must be gated.
    assert cal["buckets"][0]["gated"] is True


def test_calibration_cached_within_ttl(monkeypatch):
    repo = ForecastFakeRepo()
    client = _client(monkeypatch, repo)
    assert client.get("/forecasts/calibration", headers=_AUTH).status_code == 200
    # Mutate the fake: the cached payload must win inside the TTL.
    repo.status_counts = {"open": 99}
    body = client.get("/forecasts/calibration", headers=_AUTH).json()
    assert body["counts"] == {"open": 0, "resolved": 0}
