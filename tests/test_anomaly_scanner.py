"""Detector scan over daily bars (app/agent/anomaly/scanner.py).

History fetches are monkeypatched at app.tools.market._fetch_history_raw —
the same seam tests/test_market.py uses; no network.
"""

import math
import random
from datetime import date, timedelta

from app.agent.anomaly import scanner
from app.config import Settings
from app.tools import market


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _rows(closes: list[float], start=date(2025, 1, 2)) -> list[dict]:
    rows = []
    d = start
    for close in closes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        rows.append({
            "date": d.isoformat(), "open": close, "high": close,
            "low": close, "close": close, "volume": 1000,
        })
        d += timedelta(days=1)
    return rows


def _random_walk(n: int, seed: int, daily_vol=0.01, drift=0.0) -> list[float]:
    rng = random.Random(seed)
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * math.exp(rng.gauss(drift, daily_vol)))
    return closes


def test_log_returns_basic():
    rets = scanner.log_returns([100.0, 110.0, 99.0])
    assert rets[0] == math.log(1.1)
    assert len(rets) == 2


def test_final_day_crash_flags_zscore_down():
    closes = _random_walk(130, seed=1)
    closes.append(closes[-1] * 0.92)  # -8% final day on ~1% daily vol
    flags = scanner.run_detectors_on_series("AAPL", _rows(closes), settings=_settings())
    zflags = [f for f in flags if f.detector == "zscore"]
    assert zflags, "8% single-day drop on a 1%-vol series must flag"
    assert zflags[0].direction == "down"
    assert zflags[0].ticker == "AAPL"
    assert zflags[0].day_change_pct is not None and zflags[0].day_change_pct < -7


def test_sustained_drift_flags_cusum_within_lag():
    # Only the final bar's verdict counts, so a drift alerts on the scan day
    # when cumulative evidence crosses h. Simulate the daily cadence: extend
    # the series one bar at a time (one "day" per scan) and require a CUSUM
    # flag within a reasonable number of drift days.
    closes = _random_walk(90, seed=2)  # quiet history freezes the baseline
    rng = random.Random(3)
    flagged = None
    for day in range(1, 41):
        closes.append(closes[-1] * math.exp(rng.gauss(-0.012, 0.01)))
        flags = scanner.run_detectors_on_series(
            "RY.TO", _rows(closes), settings=_settings()
        )
        cflags = [f for f in flags if f.detector == "cusum"]
        if cflags:
            flagged = (day, cflags[0])
            break
    assert flagged is not None, "sustained -1.2σ/day drift never tripped CUSUM"
    day, flag = flagged
    assert day <= 30, f"CUSUM lag too long: {day} days"
    assert flag.direction == "down"


def test_quiet_series_produces_no_flags():
    closes = _random_walk(130, seed=4)
    flags = scanner.run_detectors_on_series("MSFT", _rows(closes), settings=_settings())
    assert flags == []


def test_short_history_is_skipped():
    closes = _random_walk(10, seed=5)
    closes.append(closes[-1] * 0.80)  # even a huge move can't be judged yet
    flags = scanner.run_detectors_on_series("NEWIPO", _rows(closes), settings=_settings())
    assert flags == []


async def test_scan_tickers_fetch_failure_skips_ticker(monkeypatch):
    good = _random_walk(130, seed=6)
    good.append(good[-1] * 0.90)

    def fake_fetch(ticker, days):
        if ticker == "BAD":
            raise RuntimeError("yfinance exploded")
        return _rows(good)

    monkeypatch.setattr(market, "_fetch_history_raw", fake_fetch)
    monkeypatch.setattr(scanner, "_FETCH_STAGGER_S", 0.0)
    result = await scanner.scan_tickers(["BAD", "GOOD"], settings=_settings())
    assert "BAD" not in result
    assert "GOOD" in result


async def test_scan_tickers_only_returns_flagged(monkeypatch):
    quiet = _random_walk(130, seed=7)
    spiked = _random_walk(130, seed=8)
    spiked.append(spiked[-1] * 1.09)

    def fake_fetch(ticker, days):
        return _rows(spiked if ticker == "NVDA" else quiet)

    monkeypatch.setattr(market, "_fetch_history_raw", fake_fetch)
    monkeypatch.setattr(scanner, "_FETCH_STAGGER_S", 0.0)
    result = await scanner.scan_tickers(["NVDA", "QUIET"], settings=_settings())
    assert set(result) == {"NVDA"}
    assert result["NVDA"][0].direction == "up"


async def test_divergence_runs_when_benchmark_set(monkeypatch):
    # Own series tracks the benchmark for 200 bars, then goes its own way.
    rng = random.Random(9)
    bench = [100.0]
    own = [50.0]
    for i in range(259):
        shared = rng.gauss(0, 0.01)
        bench.append(bench[-1] * math.exp(shared))
        own_shock = shared if i < 200 else rng.gauss(0, 0.01)
        own.append(own[-1] * math.exp(own_shock + rng.gauss(0, 0.001)))

    own_rows, bench_rows = _rows(own), _rows(bench)

    def fake_fetch(ticker, days):
        return bench_rows if ticker == "XIU.TO" else own_rows

    monkeypatch.setattr(market, "_fetch_history_raw", fake_fetch)
    monkeypatch.setattr(scanner, "_FETCH_STAGGER_S", 0.0)
    settings = _settings(
        ANOMALY_BENCHMARK_TICKER="XIU.TO",
        ANOMALY_DIVERGENCE_THRESHOLD="3.0",
    )
    result = await scanner.scan_tickers(["CM.TO"], settings=settings)
    dflags = [f for f in result.get("CM.TO", []) if f.detector == "divergence"]
    assert dflags, "correlation break vs benchmark must flag divergence"
    assert dflags[0].direction == "decoupled"


async def test_benchmark_fetch_failure_disables_divergence_not_scan(monkeypatch):
    spiked = _random_walk(130, seed=10)
    spiked.append(spiked[-1] * 0.90)

    def fake_fetch(ticker, days):
        if ticker == "XIU.TO":
            raise RuntimeError("no benchmark today")
        return _rows(spiked)

    monkeypatch.setattr(market, "_fetch_history_raw", fake_fetch)
    monkeypatch.setattr(scanner, "_FETCH_STAGGER_S", 0.0)
    settings = _settings(ANOMALY_BENCHMARK_TICKER="XIU.TO")
    result = await scanner.scan_tickers(["AAPL"], settings=settings)
    assert "AAPL" in result  # zscore still fired
    assert all(f.detector != "divergence" for f in result["AAPL"])
