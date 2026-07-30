"""Hand-computed fixtures for the cohort track record and top-N replay NAV."""

from __future__ import annotations

import datetime as dt

from app.quant import trackrecord as tr


def _d(day: int, month: int = 1, year: int = 2026) -> dt.date:
    return dt.date(year, month, day)


# ---------------------------------------------------------------------------
# cohort_returns
# ---------------------------------------------------------------------------


def test_cohort_returns_empty_entries():
    out = tr.cohort_returns([], {}, [(_d(2), 100.0), (_d(30), 110.0)])
    assert out["cohorts"] == []
    assert out["horizon_summary"] == {"7": None, "30": None, "91": None, "182": None}


def test_cohort_returns_two_cohort_fixture_exact():
    # Cohort 1 (run 01-10): AAA 100 -> 108 (+8%), BBB 50 -> 60 (+20%) => 14%.
    # Cohort 2 (run 01-20): CCC 200 -> 210 (+5%), DDD has no prices at all.
    entries = [
        {"run_date": _d(10), "ticker": "AAA", "rank": 1},
        {"run_date": _d(10), "ticker": "BBB", "rank": 2},
        {"run_date": _d(20), "ticker": "CCC", "rank": 1},
        {"run_date": _d(20), "ticker": "DDD", "rank": 1},  # rank tie with CCC
    ]
    prices = {
        "AAA": [(_d(9), 100.0), (_d(15), 110.0), (_d(17), 108.0)],
        "BBB": [(_d(8), 50.0), (_d(16), 55.0), (_d(17), 60.0)],
        "CCC": [(_d(19), 200.0), (_d(27), 210.0)],
    }
    benchmark = [
        (_d(8), 400.0),
        (_d(9), 402.0),
        (_d(17), 410.0),
        (_d(19), 405.0),
        (_d(27), 415.0),
        (_d(1, month=2), 420.0),
    ]
    out = tr.cohort_returns(entries, prices, benchmark, horizons_days=(7, 30))

    assert [c["run_date"] for c in out["cohorts"]] == ["2026-01-20", "2026-01-10"]

    newest, oldest = out["cohorts"]
    assert newest["members"] == 2 and newest["measured"] == 1
    # Benchmark span for cohort 2 at H=7: 405 (01-19) -> 415 (01-27) = +2.47%.
    assert newest["horizons"]["7"] == {
        "return_pct": 5.0,
        "benchmark_return_pct": 2.47,
        "beat": True,
        "measured": 1,
    }
    # run_date + 30d = 02-19 > latest benchmark date 02-01: not yet elapsed.
    assert newest["horizons"]["30"] is None

    assert oldest["members"] == 2 and oldest["measured"] == 2
    # Benchmark span for cohort 1 at H=7: 402 (01-09) -> 410 (01-17) = +1.99%.
    assert oldest["horizons"]["7"] == {
        "return_pct": 14.0,
        "benchmark_return_pct": 1.99,
        "beat": True,
        "measured": 2,
    }
    assert oldest["horizons"]["30"] is None

    assert out["horizon_summary"]["7"] == {
        "cohorts": 2,
        "avg_return_pct": 9.5,
        "avg_benchmark_return_pct": 2.23,
        "beat_rate_pct": 100.0,
    }
    assert out["horizon_summary"]["30"] is None


def test_cohort_returns_single_cohort():
    entries = [{"run_date": _d(10), "ticker": "AAA", "rank": 1}]
    prices = {"AAA": [(_d(9), 100.0), (_d(16), 110.0)]}
    benchmark = [(_d(9), 200.0), (_d(16), 202.0), (_d(20), 203.0)]
    out = tr.cohort_returns(entries, prices, benchmark, horizons_days=(7,))
    (cohort,) = out["cohorts"]
    assert cohort["horizons"]["7"] == {
        "return_pct": 10.0,
        "benchmark_return_pct": 1.0,
        "beat": True,
        "measured": 1,
    }
    assert out["horizon_summary"]["7"]["cohorts"] == 1


def test_cohort_returns_every_member_lacks_entry_bar():
    # Prices start only AFTER the run date: no entry bar, nothing measured,
    # even though the 7-day horizon has fully elapsed.
    entries = [{"run_date": _d(10), "ticker": "IPO", "rank": 1}]
    prices = {"IPO": [(_d(12), 10.0), (_d(15), 11.0)]}
    benchmark = [(_d(2), 100.0), (_d(20), 101.0)]
    out = tr.cohort_returns(entries, prices, benchmark, horizons_days=(7,))
    (cohort,) = out["cohorts"]
    assert cohort["members"] == 1
    assert cohort["measured"] == 0
    assert cohort["horizons"]["7"] is None
    assert out["horizon_summary"]["7"] is None


# ---------------------------------------------------------------------------
# simulate_top_picks
# ---------------------------------------------------------------------------


def test_simulate_empty_entries():
    out = tr.simulate_top_picks([], {}, [(_d(2), 100.0)])
    assert out == {"nav": [], "stats": None}


def test_simulate_single_cohort_equal_weight_and_benchmark_normalization():
    # Two picks, +10% and +20% => equal-weight +15%. Benchmark 400 -> 440
    # normalizes to 1.0 -> 1.1 at the same dates.
    entries = [
        {"run_date": _d(10), "ticker": "AAA", "rank": 1},
        {"run_date": _d(10), "ticker": "BBB", "rank": 2},
    ]
    prices = {
        "AAA": [(_d(9), 100.0), (_d(16), 110.0)],
        "BBB": [(_d(9), 50.0), (_d(16), 60.0)],
    }
    benchmark = [(_d(9), 400.0), (_d(16), 440.0)]
    out = tr.simulate_top_picks(entries, prices, benchmark)
    assert out["nav"] == [
        {"date": "2026-01-09", "nav": 1.0, "benchmark_nav": 1.0},
        {"date": "2026-01-16", "nav": 1.15, "benchmark_nav": 1.1},
    ]
    stats = out["stats"]
    assert stats["total_return_pct"] == 15.0
    assert stats["benchmark_return_pct"] == 10.0
    assert stats["max_drawdown_pct"] == 0.0
    assert stats["sharpe"] is None  # a single daily return has no dispersion
    assert stats["tracking_error_pct"] is None
    assert stats["days"] == 1


def test_simulate_rebalances_into_new_top_n_at_second_run():
    # Cohort 1 (run 01-05) holds AAA+BBB: 01-02 -> 01-08 gives
    # 0.5*1.1 + 0.5*1.2 = 1.15. Cohort 2 (run 01-09) rebalances into BBB+CCC
    # at the 01-08 bar: 01-08 -> 01-15 gives 0.5*1.2 + 0.5*1.2 = 1.2,
    # so NAV = 1.15 * 1.2 = 1.38. AAA's later print must not matter.
    entries = [
        {"run_date": _d(5), "ticker": "AAA", "rank": 1},
        {"run_date": _d(5), "ticker": "BBB", "rank": 2},
        {"run_date": _d(9), "ticker": "BBB", "rank": 1},
        {"run_date": _d(9), "ticker": "CCC", "rank": 2},
    ]
    prices = {
        "AAA": [(_d(2), 100.0), (_d(8), 110.0), (_d(15), 999.0)],
        "BBB": [(_d(2), 100.0), (_d(8), 120.0), (_d(15), 144.0)],
        "CCC": [(_d(8), 10.0), (_d(15), 12.0)],
    }
    benchmark = [(_d(2), 400.0), (_d(8), 410.0), (_d(15), 420.0)]
    out = tr.simulate_top_picks(entries, prices, benchmark, top_n=2)
    assert out["nav"] == [
        {"date": "2026-01-02", "nav": 1.0, "benchmark_nav": 1.0},
        {"date": "2026-01-08", "nav": 1.15, "benchmark_nav": 1.025},
        {"date": "2026-01-15", "nav": 1.38, "benchmark_nav": 1.05},
    ]
    stats = out["stats"]
    assert stats["total_return_pct"] == 38.0
    assert stats["benchmark_return_pct"] == 5.0
    assert stats["max_drawdown_pct"] == 0.0
    assert stats["sharpe"] is not None
    assert stats["days"] == 2


def test_simulate_member_missing_interior_date_carries_last_close():
    # BBB has no 01-08 print: it is carried at 200 (0% that step) and its
    # move lands on 01-15. Buy-and-hold check: 0.5*1.21 + 0.5*1.1 = 1.155.
    entries = [
        {"run_date": _d(5), "ticker": "AAA", "rank": 1},
        {"run_date": _d(5), "ticker": "BBB", "rank": 2},
    ]
    prices = {
        "AAA": [(_d(2), 100.0), (_d(8), 110.0), (_d(15), 121.0)],
        "BBB": [(_d(2), 200.0), (_d(15), 220.0)],
    }
    # Benchmark has no 01-08 print either: its NAV is carried flat there.
    benchmark = [(_d(2), 50.0), (_d(15), 55.0)]
    out = tr.simulate_top_picks(entries, prices, benchmark)
    assert out["nav"] == [
        {"date": "2026-01-02", "nav": 1.0, "benchmark_nav": 1.0},
        {"date": "2026-01-08", "nav": 1.05, "benchmark_nav": 1.0},
        {"date": "2026-01-15", "nav": 1.155, "benchmark_nav": 1.1},
    ]


def test_simulate_rank_tie_broken_by_ticker():
    # Both rank 1: top_n=1 must take "AAA" (ticker tiebreak), not "ZZZ".
    entries = [
        {"run_date": _d(5), "ticker": "ZZZ", "rank": 1},
        {"run_date": _d(5), "ticker": "AAA", "rank": 1},
    ]
    prices = {
        "AAA": [(_d(2), 100.0), (_d(9), 120.0)],
        "ZZZ": [(_d(2), 100.0), (_d(9), 100.0)],
    }
    benchmark = [(_d(2), 100.0), (_d(9), 100.0)]
    out = tr.simulate_top_picks(entries, prices, benchmark, top_n=1)
    assert out["nav"][-1]["nav"] == 1.2


def test_simulate_flat_carry_when_basket_has_no_coverage_then_resumes():
    # Cohort 2's only pick has no prices: the position is marked at the last
    # bar before that run (01-08) and the NAV sits flat. Cohort 3 rebalances
    # back into AAA at the same 01-08 bar, so growth resumes 01-08 -> 01-15.
    entries = [
        {"run_date": _d(5), "ticker": "AAA", "rank": 1},
        {"run_date": _d(9), "ticker": "GHOST", "rank": 1},
        {"run_date": _d(14), "ticker": "AAA", "rank": 1},
    ]
    prices = {"AAA": [(_d(2), 100.0), (_d(8), 110.0), (_d(15), 121.0)]}
    benchmark = [(_d(2), 100.0), (_d(8), 100.0), (_d(15), 100.0)]
    out = tr.simulate_top_picks(entries, prices, benchmark)
    assert [(p["date"], p["nav"]) for p in out["nav"]] == [
        ("2026-01-02", 1.0),
        ("2026-01-08", 1.1),
        ("2026-01-15", 1.21),
    ]
    stats = out["stats"]
    assert stats["total_return_pct"] == 21.0
    assert stats["benchmark_return_pct"] == 0.0


def test_simulate_single_nav_point_returns_empty():
    # Only one bar exists before/at the horizon: fewer than 2 NAV points.
    entries = [{"run_date": _d(5), "ticker": "AAA", "rank": 1}]
    prices = {"AAA": [(_d(2), 100.0)]}
    benchmark = [(_d(2), 100.0)]
    out = tr.simulate_top_picks(entries, prices, benchmark)
    assert out == {"nav": [], "stats": None}
