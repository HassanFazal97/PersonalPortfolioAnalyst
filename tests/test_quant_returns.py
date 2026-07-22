"""Returns-matrix builder: currency additivity, date alignment, exclusions."""

from __future__ import annotations

from math import log

import numpy as np

from app.quant.returns import build_returns_matrix


def _series(start_date_ordinal: int, prices: list[float]) -> list[dict]:
    """Build {date, adj_close} rows from a price list on consecutive days."""
    from datetime import date, timedelta

    base = date.fromordinal(start_date_ordinal)
    return [
        {"date": (base + timedelta(days=i)).isoformat(), "adj_close": p}
        for i, p in enumerate(prices)
    ]


def test_cad_holding_returns_are_plain_log_returns():
    prices = [100.0, 110.0, 99.0, 108.0, 100.0]
    rm = build_returns_matrix(
        {"RY.TO": _series(739000, prices)},
        {"RY.TO": "CAD"},
        fx_rows=None,
        min_obs=2,
    )
    assert rm.tickers == ["RY.TO"]
    expected = [log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]
    np.testing.assert_allclose(rm.matrix[:, 0], expected, atol=1e-12)


def test_usd_holding_adds_fx_log_return_exactly():
    # Currency additivity: r_cad == r_local + r_fx, to floating tolerance.
    px = [100.0, 105.0, 103.0, 110.0, 108.0]
    fx = [1.35, 1.36, 1.34, 1.37, 1.33]
    rm = build_returns_matrix(
        {"NVDA": _series(739000, px)},
        {"NVDA": "USD"},
        fx_rows=_series(739000, fx),
        min_obs=2,
    )
    assert rm.tickers == ["NVDA"]
    r_local = np.array([log(px[i] / px[i - 1]) for i in range(1, len(px))])
    r_fx = np.array([log(fx[i] / fx[i - 1]) for i in range(1, len(fx))])
    np.testing.assert_allclose(rm.matrix[:, 0], r_local + r_fx, atol=1e-12)


def test_usd_holding_excluded_when_fx_missing():
    rm = build_returns_matrix(
        {"NVDA": _series(739000, [100.0, 101.0, 102.0])},
        {"NVDA": "USD"},
        fx_rows=None,
        min_obs=2,
    )
    assert rm.tickers == []
    assert "NVDA" in rm.excluded
    assert "FX" in rm.excluded["NVDA"]


def test_date_intersection_not_positional_zip():
    # RY.TO is missing one date the US names have; alignment must intersect on
    # dates, not zip positionally, or returns smear across mismatched days.
    from datetime import date, timedelta

    base = date.fromordinal(739000)

    def row(i, p):
        return {"date": (base + timedelta(days=i)).isoformat(), "adj_close": p}

    aapl = [row(i, 100.0 + i) for i in range(6)]  # days 0..5
    ry = [row(i, 50.0 + i) for i in [0, 1, 3, 4, 5]]  # missing day 2
    rm = build_returns_matrix(
        {"AAPL": aapl, "RY.TO": ry},
        {"AAPL": "CAD", "RY.TO": "CAD"},  # keep it FX-free for this test
        fx_rows=None,
        min_obs=2,
    )
    # Common dates = {0,1,3,4,5} -> 4 return rows, both columns present.
    assert set(rm.tickers) == {"AAPL", "RY.TO"}
    assert rm.n_obs == 4
    # The return spanning the day-1 -> day-3 gap uses day-1 and day-3 prices.
    j = rm.tickers.index("AAPL")
    expected_gap = log(103.0 / 101.0)  # AAPL day3=103, day1=101
    assert rm.dates[1] == (base + timedelta(days=3)).isoformat()
    np.testing.assert_allclose(rm.matrix[1, j], expected_gap, atol=1e-12)


def test_short_history_holding_excluded_not_padded():
    long = _series(739000, [100.0 + i for i in range(10)])
    short = _series(739000, [10.0, 11.0])  # only 2 prices -> 1 return
    rm = build_returns_matrix(
        {"LONG": long, "SHORT": short},
        {"LONG": "CAD", "SHORT": "CAD"},
        fx_rows=None,
        min_obs=5,
    )
    assert rm.tickers == ["LONG"]
    assert "SHORT" in rm.excluded
