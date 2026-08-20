"""run_forecast_ledger: idempotent extraction, due-only resolution, expiry."""

from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace

import pytest

from app.agent.forecasts import jobs
from app.config import get_settings

TODAY = dt.date(2026, 8, 20)
RUN_ID = uuid.uuid4()


class StubRepo:
    def __init__(self):
        self.forecasts: dict[str, dict] = {}  # claim_key -> row
        self.due: list[SimpleNamespace] = []
        self.resolved: dict[uuid.UUID, dict] = {}
        self.picks_runs: list[SimpleNamespace] = []
        self.alerts: list[SimpleNamespace] = []
        self.reports: list[SimpleNamespace] = []
        self.digests: list[SimpleNamespace] = []

    async def list_picks_runs(self, *, limit=10):
        return self.picks_runs

    async def list_deep_dive_reports_since(self, since, **kw):
        return self.reports

    async def list_alerts_since(self, since):
        return self.alerts

    async def list_digests_since(self, since):
        return self.digests

    async def insert_forecasts_if_new(self, rows):
        inserted = 0
        for row in rows:
            if row["claim_key"] not in self.forecasts:
                self.forecasts[row["claim_key"]] = row
                inserted += 1
        return inserted

    async def list_due_forecasts(self, as_of, **kw):
        return [f for f in self.due if f.status == "open" and f.due_date <= as_of]

    async def resolve_forecast(self, forecast_id, **fields):
        self.resolved[forecast_id] = fields
        for f in self.due:
            if f.id == forecast_id:
                f.status = fields.get("status", f.status)

    async def get_daily_prices_bulk(self, tickers, *, since=None):
        bars = [
            SimpleNamespace(price_date=dt.date(2026, 5, 19), adj_close=100.0),
            SimpleNamespace(price_date=dt.date(2026, 7, 30), adj_close=110.0),
            SimpleNamespace(price_date=dt.date(2026, 8, 19), adj_close=112.0),
        ]
        return {t: bars for t in tickers}


@pytest.fixture
def repo():
    return StubRepo()


@pytest.fixture(autouse=True)
def _fake_benchmark(monkeypatch):
    async def fake_closes(repo, ticker, days):
        return [
            {"date": "2026-05-19", "adj_close": 400.0},
            {"date": "2026-07-30", "adj_close": 408.0},
            {"date": "2026-08-19", "adj_close": 410.0},
        ]

    monkeypatch.setattr(jobs.price_store, "get_adjusted_closes", fake_closes)


def _picks_run():
    return SimpleNamespace(
        id=uuid.uuid4(),
        run_date=TODAY,
        status="completed",
        run_id=RUN_ID,
        payload={"picks": [{"ticker": "NVDA", "rank": 1, "confidence": 0.7, "thesis": "T"}]},
    )


async def test_extraction_is_idempotent(repo):
    repo.picks_runs = [_picks_run()]
    s1 = await jobs.run_forecast_ledger(repo, get_settings(), today=TODAY)
    assert s1["inserted"] == 1
    s2 = await jobs.run_forecast_ledger(repo, get_settings(), today=TODAY)
    assert s2["inserted"] == 0  # same claim_key, no duplicate


async def test_old_error_and_runless_sources_skipped(repo):
    repo.picks_runs = [
        SimpleNamespace(id=uuid.uuid4(), run_date=TODAY - dt.timedelta(days=30),
                        status="completed", run_id=RUN_ID, payload={"picks": []}),
        SimpleNamespace(id=uuid.uuid4(), run_date=TODAY, status="error",
                        run_id=RUN_ID, payload={"picks": []}),
    ]
    repo.alerts = [
        SimpleNamespace(id=uuid.uuid4(), run_id=None, user_id=uuid.uuid4(),
                        category="macro_trade", severity="high",
                        headline="H", tickers=["NVDA"],
                        created_at=dt.datetime(2026, 8, 19, tzinfo=dt.timezone.utc)),
    ]
    stats = await jobs.run_forecast_ledger(repo, get_settings(), today=TODAY)
    assert stats["inserted"] == 0
    assert stats["alerts_without_run"] == 1


async def test_prose_docs_counted_when_no_client(repo):
    repo.digests = [
        SimpleNamespace(id=uuid.uuid4(), run_id=RUN_ID, user_id=uuid.uuid4(),
                        body="NVDA may fall.", digest_date=TODAY)
    ]
    stats = await jobs.run_forecast_ledger(repo, get_settings(), today=TODAY)
    assert stats["prose_docs_skipped_no_client"] == 1
    assert stats["inserted"] == 0  # never guessed without a model


def _due_row(claim_type, *, due=dt.date(2026, 8, 1), ticker="NVDA", direction="up"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        claim_type=claim_type,
        primary_ticker=ticker,
        direction=direction,
        horizon_days=30,
        as_of_date=dt.date(2026, 7, 2),
        due_date=due,
        probability=0.62,
        magnitude_min_pct=None,
        status="open",
    )


async def test_resolution_resolves_expires_and_leaves_open(repo):
    direction = _due_row("direction")             # resolvable, elapsed -> hit
    event = _due_row("event")                     # unresolvable -> expired
    future = _due_row("direction", due=dt.date(2026, 12, 1))  # beyond bench -> open
    repo.due = [direction, event, future]
    stats = await jobs.run_forecast_ledger(repo, get_settings(), today=TODAY)
    assert stats["resolved"] == 1 and stats["expired"] == 1 and stats["still_open"] == 0
    assert repo.resolved[direction.id]["outcome"] == "hit"       # 100 -> 110
    assert repo.resolved[direction.id]["realized_value"] == 10.0
    assert repo.resolved[direction.id]["benchmark_value"] == 2.0
    assert repo.resolved[event.id]["status"] == "expired"
    assert future.id not in repo.resolved  # due_date filter keeps it out entirely
