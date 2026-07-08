import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_USER_ID, get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_OWNER = uuid.UUID(DEFAULT_USER_ID)
_AUTH = {"Authorization": "Bearer test-token"}


def _client(monkeypatch, repo):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


def test_news_requires_auth(monkeypatch):
    assert _client(monkeypatch, FakeRepo()).get("/news").status_code == 401


@pytest.mark.asyncio
async def test_news_merges_sources(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    run_id = uuid.uuid4()
    await repo.upsert_digest(
        run_id=run_id,
        body="Brief body",
        digest_date=date.today(),
        user_id=_OWNER,
    )
    await repo.create_alert_if_new(
        run_id=run_id,
        category="monetary",
        severity="high",
        headline="Rate hike",
        body="Fed signals pause",
        tickers=["NVDA"],
        fingerprint="fp1",
        user_id=_OWNER,
    )
    await repo.insert_news_items_if_new(
        _OWNER,
        [{"ticker": "NVDA", "headline": "NVDA beats", "summary": "Strong quarter"}],
        run_id=run_id,
    )

    client = _client(monkeypatch, repo)
    items = client.get("/news", headers=_AUTH).json()["items"]
    kinds = {i["kind"] for i in items}
    assert "digest" in kinds
    assert "alert" in kinds
    assert "holding" in kinds


@pytest.mark.asyncio
async def test_news_filters_by_ticker(monkeypatch):
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    run_id = uuid.uuid4()
    await repo.create_alert_if_new(
        run_id=run_id,
        category="energy",
        severity="medium",
        headline="Oil spike",
        body="Crude up",
        tickers=["XOM"],
        fingerprint="fp2",
        user_id=_OWNER,
    )
    await repo.insert_news_items_if_new(
        _OWNER,
        [{"ticker": "NVDA", "headline": "NVDA news", "summary": "x"}],
        run_id=run_id,
    )

    client = _client(monkeypatch, repo)
    items = client.get("/news?ticker=NVDA&kind=holding,alert", headers=_AUTH).json()["items"]
    assert all(
        i["kind"] == "holding" or "NVDA" in (i.get("tickers") or [])
        for i in items
    )
    assert not any(
        i["kind"] == "alert" and i.get("tickers") == ["XOM"] for i in items
    )
