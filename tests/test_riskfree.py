"""BoC risk-free rate: nightly sync, stored read, override, fail-open."""

from datetime import date, timedelta
from types import SimpleNamespace

from app.quant.performance import DEFAULT_RISK_FREE_ANNUAL
from app.tools import riskfree
from tests.fakes import FakeRepo


async def test_sync_persists_and_read_returns_decimal(monkeypatch):
    repo = FakeRepo()

    async def fake_fetch():
        return (date.today(), 4.35)

    monkeypatch.setattr(riskfree, "fetch_boc_tbill_yield", fake_fetch)
    assert await riskfree.sync_risk_free(repo) is True

    rf = await riskfree.current_risk_free_annual(
        repo, SimpleNamespace(risk_free_rate_annual=0.0)
    )
    assert abs(rf - 0.0435) < 1e-9


async def test_explicit_override_wins(monkeypatch):
    repo = FakeRepo()
    rf = await riskfree.current_risk_free_annual(
        repo, SimpleNamespace(risk_free_rate_annual=0.05)
    )
    assert rf == 0.05


async def test_stale_or_missing_observation_fails_open():
    repo = FakeRepo()
    settings = SimpleNamespace(risk_free_rate_annual=0.0)
    # Nothing stored at all -> historical default.
    assert (
        await riskfree.current_risk_free_annual(repo, settings)
        == DEFAULT_RISK_FREE_ANNUAL
    )
    # A stale observation (rate has moved on) is treated as absent.
    old = date.today() - timedelta(days=30)
    await repo.upsert_daily_prices(
        riskfree.RISK_FREE_TICKER, [{"date": old.isoformat(), "adj_close": 9.99}]
    )
    assert (
        await riskfree.current_risk_free_annual(repo, settings)
        == DEFAULT_RISK_FREE_ANNUAL
    )


async def test_fetch_failure_never_breaks_sync(monkeypatch):
    async def boom():
        return None

    monkeypatch.setattr(riskfree, "fetch_boc_tbill_yield", boom)
    assert await riskfree.sync_risk_free(FakeRepo()) is False
