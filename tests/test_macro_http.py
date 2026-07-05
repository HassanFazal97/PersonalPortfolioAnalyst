"""HTTP-level tests for macro alert endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app

_OWNER = uuid.UUID(DEFAULT_USER_ID)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = AsyncMock()
    app.state.repo.ping = AsyncMock(return_value=True)
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


def test_macro_scan_requires_auth(client):
    assert client.post("/macro/scan").status_code == 401


def test_macro_scan_for_owner(client, monkeypatch):
    expected = {
        "run_id": str(uuid.uuid4()),
        "status": "completed",
        "user_id": DEFAULT_USER_ID,
        "events_found": 0,
        "alerts": [],
    }
    monkeypatch.setattr(
        "app.main.run_macro_scan",
        AsyncMock(return_value=expected),
    )
    resp = client.post(
        "/macro/scan",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_list_alerts_scoped_to_user(client, monkeypatch):
    from types import SimpleNamespace

    alert = SimpleNamespace(
        id=uuid.uuid4(),
        category="monetary",
        severity="high",
        headline="Fed holds",
        body="Rates unchanged.",
        tickers=["NVDA"],
        delivered=True,
        created_at=None,
    )
    app = client.app
    app.state.repo.recent_alerts = AsyncMock(return_value=[alert])

    resp = client.get(
        "/alerts",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    data = resp.json()["alerts"]
    assert len(data) == 1
    assert data[0]["headline"] == "Fed holds"
