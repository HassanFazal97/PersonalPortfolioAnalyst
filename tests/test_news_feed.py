import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_USER_ID, get_settings
from app.db.repo import digest_mentions_ticker
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


def test_digest_mentions_ticker_word_boundaries():
    assert digest_mentions_ticker("NVDA -2.1% on export news", "NVDA")
    # Exchange-suffixed tickers match on the root the prose actually uses.
    assert digest_mentions_ticker("SHOP fell 4% after earnings", "SHOP.TO")
    assert digest_mentions_ticker("SHOP.TO fell 4%", "SHOP.TO")
    # Word boundaries + case sensitivity: TE must not match 'tech' or 'Te'.
    assert not digest_mentions_ticker("Big tech rallied broadly", "TE")
    assert digest_mentions_ticker("TE gained on new contracts", "TE")
    assert not digest_mentions_ticker(None, "NVDA")
    assert not digest_mentions_ticker("Quiet day across the book", "NVDA")


@pytest.mark.asyncio
async def test_ticker_filtered_feed_includes_mentioning_digests(monkeypatch):
    # The stock detail page asks for digest,holding,alert with a ticker —
    # digests that mention the ticker appear, others are dropped.
    repo = FakeRepo()
    repo.seed_user(_OWNER, plan="pro")
    run_id = uuid.uuid4()
    await repo.upsert_digest(
        run_id=run_id,
        body="NVDA slid 3% premarket; rest of the book flat.",
        digest_date=date(2026, 7, 14),
        user_id=_OWNER,
    )
    await repo.upsert_digest(
        run_id=run_id,
        body="Quiet macro day, nothing actionable.",
        digest_date=date(2026, 7, 15),
        user_id=_OWNER,
    )

    client = _client(monkeypatch, repo)
    items = client.get(
        "/news?ticker=NVDA&kind=digest,holding,alert", headers=_AUTH
    ).json()["items"]
    digests = [i for i in items if i["kind"] == "digest"]
    assert len(digests) == 1
    assert "NVDA" in digests[0]["body"]
    # Unfiltered feed still returns both digests.
    all_items = client.get("/news?kind=digest", headers=_AUTH).json()["items"]
    assert len([i for i in all_items if i["kind"] == "digest"]) == 2
