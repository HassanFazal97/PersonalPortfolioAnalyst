import app.tools.market as market
from app.tools.market import (
    annualized_volatility_pct,
    get_price_history,
    get_quote,
    max_drawdown_pct,
    period_return_pct,
)


def test_period_return_pct():
    assert period_return_pct([100.0, 110.0]) == 10.0
    assert period_return_pct([100.0]) is None


def test_max_drawdown_pct():
    # peak 120 then trough 90 -> -25%
    assert max_drawdown_pct([100.0, 120.0, 90.0, 100.0]) == -25.0
    assert max_drawdown_pct([100.0, 101.0, 102.0]) == 0.0


def test_annualized_volatility_is_positive_for_varying_series():
    vol = annualized_volatility_pct([100.0, 102.0, 99.0, 101.0, 100.0])
    assert vol is not None and vol > 0


async def test_get_quote_computes_day_change_and_caches(monkeypatch):
    market.cache_clear()
    calls = {"n": 0}

    def fake_fetch(ticker):
        calls["n"] += 1
        return {"last_price": 110.0, "previous_close": 100.0, "volume": 1234}

    monkeypatch.setattr(market, "_fetch_quote_raw", fake_fetch)

    r1 = await get_quote({"tickers": ["nvda"]})
    q = r1["quotes"][0]
    assert q["ticker"] == "NVDA"
    assert q["day_change_pct"] == 10.0
    assert q["volume"] == 1234

    # Second call within TTL is served from cache (no extra fetch).
    await get_quote({"tickers": ["NVDA"]})
    assert calls["n"] == 1


async def test_get_quote_cache_expires(monkeypatch):
    market.cache_clear()
    t = {"now": 1000.0}
    calls = {"n": 0}

    monkeypatch.setattr(market, "_clock", lambda: t["now"])

    def fake_fetch(ticker):
        calls["n"] += 1
        return {"last_price": 50.0, "previous_close": 50.0, "volume": 1}

    monkeypatch.setattr(market, "_fetch_quote_raw", fake_fetch)

    await get_quote({"tickers": ["AAPL"]})
    t["now"] += market.QUOTE_TTL_SECONDS + 1
    await get_quote({"tickers": ["AAPL"]})
    assert calls["n"] == 2


async def test_get_price_history_validates_days(monkeypatch):
    monkeypatch.setattr(market, "_fetch_history_raw", lambda t, d: [])
    try:
        await get_price_history({"ticker": "NVDA", "days": 4})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


async def test_get_price_history_computes_metrics(monkeypatch):
    rows = [
        {"date": "2024-01-01", "open": 100, "high": 101, "low": 99, "close": 100.0, "volume": 10},
        {"date": "2024-01-02", "open": 100, "high": 121, "low": 100, "close": 120.0, "volume": 10},
        {"date": "2024-01-03", "open": 120, "high": 120, "low": 90, "close": 90.0, "volume": 10},
    ]
    monkeypatch.setattr(market, "_fetch_history_raw", lambda t, d: rows)
    out = await get_price_history({"ticker": "nvda", "days": 30})
    assert out["ticker"] == "NVDA"
    assert out["bars_returned"] == 3
    assert out["period_return_pct"] == -10.0
    assert out["max_drawdown_pct"] == -25.0
