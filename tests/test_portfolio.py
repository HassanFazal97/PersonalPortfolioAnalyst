from types import SimpleNamespace

import app.tools.market as market
from app.tools.portfolio import get_portfolio


class FakeRepo:
    def __init__(self, positions):
        self._positions = positions

    async def list_positions(self):
        return self._positions


def _pos(ticker, qty, avg_cost, currency, account="taxable"):
    return SimpleNamespace(
        ticker=ticker, quantity=qty, avg_cost=avg_cost, currency=currency, account=account
    )


async def test_get_portfolio_aggregates_with_fx(monkeypatch):
    market.cache_clear()

    prices = {
        "NVDA": {"last_price": 200.0, "previous_close": 190.0, "volume": 1},  # USD
        "SHOP.TO": {"last_price": 100.0, "previous_close": 100.0, "volume": 1},  # CAD
        "USDCAD=X": {"last_price": 1.4, "previous_close": 1.4, "volume": 1},
    }
    monkeypatch.setattr(market, "_fetch_quote_raw", lambda t: prices[t])

    ctx = SimpleNamespace(
        repo=FakeRepo(
            [
                _pos("NVDA", 10, 150.0, "USD"),
                _pos("SHOP.TO", 5, 80.0, "CAD"),
            ]
        )
    )

    out = await get_portfolio({}, ctx)
    totals = out["totals"]

    # NVDA: 10 * 200 = 2000 USD -> 2800 CAD; SHOP: 5 * 100 = 500 CAD -> 3300 CAD
    assert totals["total_market_value_cad"] == 3300.0
    assert totals["usdcad_rate"] == 1.4
    assert totals["includes_all_positions"] is True

    nvda = next(p for p in out["positions"] if p["ticker"] == "NVDA")
    assert nvda["market_value"] == 2000.0
    assert nvda["unrealized_pnl"] == 500.0  # (200-150)*10
    assert nvda["day_change_pct"] == 5.26  # (200-190)/190*100


async def test_get_portfolio_handles_missing_quote(monkeypatch):
    market.cache_clear()

    def fetch(t):
        if t == "USDCAD=X":
            return {"last_price": 1.4, "previous_close": 1.4, "volume": 1}
        raise RuntimeError("delisted")

    monkeypatch.setattr(market, "_fetch_quote_raw", fetch)

    ctx = SimpleNamespace(repo=FakeRepo([_pos("XYZ", 1, 10.0, "CAD")]))
    out = await get_portfolio({}, ctx)
    assert out["positions"][0]["error"] == "quote unavailable"
    assert out["totals"]["includes_all_positions"] is False


async def test_get_portfolio_empty(monkeypatch):
    ctx = SimpleNamespace(repo=FakeRepo([]))
    out = await get_portfolio({}, ctx)
    assert out["positions"] == []
