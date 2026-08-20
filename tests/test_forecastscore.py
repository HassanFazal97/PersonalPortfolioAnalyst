"""Hand-computed fixtures for forecast resolution and calibration scoring."""

from __future__ import annotations

import datetime as dt

from app.quant import forecastscore as fs


def _d(day: int, month: int = 1, year: int = 2026) -> dt.date:
    return dt.date(year, month, day)


def _claim(**overrides):
    base = {
        "claim_type": "direction",
        "primary_ticker": "AAA",
        "direction": "up",
        "horizon_days": 7,
        "as_of_date": _d(10),
        "due_date": _d(17),
        "probability": 0.75,
        "magnitude_min_pct": None,
    }
    base.update(overrides)
    return base


# Benchmark spanning well past every due date used below.
BENCH = [(_d(8), 400.0), (_d(12), 404.0), (_d(17), 408.0), (_d(28), 410.0)]


# ---------------------------------------------------------------------------
# snap_horizon / brier
# ---------------------------------------------------------------------------


def test_snap_horizon_exact_nearest_and_defaults():
    assert fs.snap_horizon(7, "direction") == 7
    assert fs.snap_horizon(10, "direction") == 7
    assert fs.snap_horizon(21, "direction") == 30
    assert fs.snap_horizon(60, "direction") == 30
    assert fs.snap_horizon(61, "direction") == 91
    assert fs.snap_horizon(365, "direction") == 182
    assert fs.snap_horizon(None, "direction") == 30
    assert fs.snap_horizon(None, "risk_warning") == 91
    assert fs.snap_horizon(0, "relative_performance") == 91


def test_brier_identities():
    assert fs.brier(1.0, True) == 0.0
    assert fs.brier(1.0, False) == 1.0
    assert fs.brier(0.5, True) == 0.25
    assert fs.brier(0.5, False) == 0.25
    assert round(fs.brier(0.75, False), 4) == 0.5625


# ---------------------------------------------------------------------------
# resolve_forecast: gating
# ---------------------------------------------------------------------------


def test_not_resolvable_before_horizon_elapses():
    # Latest benchmark bar (01-28) is before the due date -> stays open.
    claim = _claim(due_date=_d(30), horizon_days=30)
    assert fs.resolve_forecast(claim, {"AAA": [(_d(9), 100.0)]}, BENCH) is None


def test_unresolvable_claim_types_return_none():
    for claim_type in ("event", "volatility"):
        assert (
            fs.resolve_forecast(_claim(claim_type=claim_type), {"AAA": []}, BENCH)
            is None
        )


def test_entry_bar_strictly_before_as_of():
    # Only bar on/after as_of: no entry bar exists -> indeterminate, never a
    # hindsight entry at the as_of close itself.
    prices = {"AAA": [(_d(10), 100.0), (_d(15), 120.0)]}
    out = fs.resolve_forecast(_claim(), prices, BENCH)
    assert out["outcome"] == "indeterminate"
    assert out["resolution_detail"]["reason"] == "no_measurable_span"
    assert out["brier"] is None


# ---------------------------------------------------------------------------
# resolve_forecast: direction
# ---------------------------------------------------------------------------


def test_direction_up_hit_exact_numbers():
    # Entry = 01-09 close 100 (last strictly before 01-10); exit = 01-16
    # close 110 (last on/before 01-17): +10%.
    prices = {"AAA": [(_d(9), 100.0), (_d(12), 104.0), (_d(16), 110.0)]}
    out = fs.resolve_forecast(_claim(), prices, BENCH)
    assert out["outcome"] == "hit"
    assert out["realized_value"] == 10.0
    # Benchmark 400 (01-08) -> 408 (01-17): +2%.
    assert out["benchmark_value"] == 2.0
    assert out["brier"] == round((0.75 - 1.0) ** 2, 4)
    assert out["resolution_detail"]["entry_bar_date"] == "2026-01-09"
    assert out["resolution_detail"]["exit_bar_date"] == "2026-01-16"


def test_direction_down_and_flat_bands():
    prices = {"AAA": [(_d(9), 100.0), (_d(16), 99.5)]}  # -0.5%
    down = fs.resolve_forecast(_claim(direction="down"), prices, BENCH)
    assert down["outcome"] == "hit" and down["realized_value"] == -0.5
    # |−0.5%| < 1.0 band at 7d -> flat also hits on this tape.
    flat = fs.resolve_forecast(_claim(direction="flat"), prices, BENCH)
    assert flat["outcome"] == "hit"
    # Exactly at the band edge is NOT flat (strict <).
    prices_edge = {"AAA": [(_d(9), 100.0), (_d(16), 101.0)]}  # +1.0%
    edge = fs.resolve_forecast(_claim(direction="flat"), prices_edge, BENCH)
    assert edge["outcome"] == "miss"


def test_direction_stated_magnitude_tightens():
    prices = {"AAA": [(_d(9), 100.0), (_d(16), 103.0)]}  # +3%
    plain = fs.resolve_forecast(_claim(), prices, BENCH)
    assert plain["outcome"] == "hit"
    tightened = fs.resolve_forecast(_claim(magnitude_min_pct=5.0), prices, BENCH)
    assert tightened["outcome"] == "miss"  # +3% < stated +5%


# ---------------------------------------------------------------------------
# resolve_forecast: relative_performance / risk_warning
# ---------------------------------------------------------------------------


def test_relative_performance_vs_benchmark_same_span():
    # AAA +1% vs benchmark +2% -> outperform misses, underperform hits.
    prices = {"AAA": [(_d(9), 100.0), (_d(16), 101.0)]}
    out = fs.resolve_forecast(
        _claim(claim_type="relative_performance", direction="outperform"),
        prices,
        BENCH,
    )
    assert out["outcome"] == "miss"
    assert out["realized_value"] == 1.0 and out["benchmark_value"] == 2.0
    under = fs.resolve_forecast(
        _claim(claim_type="relative_performance", direction="underperform"),
        prices,
        BENCH,
    )
    assert under["outcome"] == "hit"


def test_risk_warning_drawdown_band():
    # Peak 110 on 01-12, trough 99 on 01-15: drawdown -10% from the peak
    # (entry 100 seeds the peak; 110 replaces it). 7d band = 5% -> hit.
    prices = {"AAA": [(_d(9), 100.0), (_d(12), 110.0), (_d(15), 99.0), (_d(16), 105.0)]}
    out = fs.resolve_forecast(_claim(claim_type="risk_warning"), prices, BENCH)
    assert out["outcome"] == "hit"
    assert out["realized_value"] == -10.0
    assert out["resolution_detail"]["drawdown_threshold_pct"] == 5.0
    # A gentle tape (max dd -2%) misses the warning.
    calm = {"AAA": [(_d(9), 100.0), (_d(12), 98.0), (_d(16), 103.0)]}
    out2 = fs.resolve_forecast(_claim(claim_type="risk_warning"), calm, BENCH)
    assert out2["outcome"] == "miss"
    assert out2["realized_value"] == -2.0


# ---------------------------------------------------------------------------
# calibration_summary
# ---------------------------------------------------------------------------


def _row(family: str, outcome: str, *, conf: str = "high", brier_v=0.0625, p=0.75):
    return {
        "family_key": family,
        "source": "digest",
        "claim_type": "direction",
        "confidence_verbal": conf,
        "outcome": outcome,
        "brier": brier_v,
        "probability": p,
    }


def test_calibration_family_dedup_exact():
    # Family A restated 3 times (2 hits, 1 miss -> 2/3), family B one miss.
    rows = [
        _row("A", "hit"),
        _row("A", "hit"),
        _row("A", "miss"),
        _row("B", "miss"),
    ]
    out = fs.calibration_summary(rows, min_families=1)
    overall = out["overall"]
    assert overall["families"] == 2 and overall["rows"] == 4
    # (2/3 + 0) / 2 = 1/3.
    assert overall["hit_rate_pct"] == 33.33


def test_calibration_gate_at_min_families():
    rows29 = [_row(f"F{i}", "hit") for i in range(29)]
    gated = fs.calibration_summary(rows29, min_families=30)
    assert gated["buckets"][0]["gated"] is True
    assert "hit_rate_pct" not in gated["buckets"][0]
    rows30 = rows29 + [_row("F29", "hit")]
    open_ = fs.calibration_summary(rows30, min_families=30)
    assert open_["buckets"][0]["gated"] is False
    assert open_["buckets"][0]["hit_rate_pct"] == 100.0


def test_calibration_ignores_unscored_rows():
    rows = [_row("A", "hit"), _row("B", "indeterminate"), _row("C", "expired")]
    out = fs.calibration_summary(rows, min_families=1)
    assert out["overall"]["families"] == 1
