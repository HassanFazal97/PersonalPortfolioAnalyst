"""Pure aggregation math for price-anomaly alerts (app/agent/anomaly/synthesis.py)."""

from datetime import date

import pytest

from app.agent.anomaly.scanner import AnomalyFlag
from app.agent.anomaly.synthesis import (
    best_flag_per_ticker,
    build_fingerprint,
    format_fallback_message,
    noisy_or,
    severity_label,
)


def _flag(ticker="AAPL", detector="zscore", direction="down", severity=0.6,
          score=-3.6, day_change_pct=-4.2):
    return AnomalyFlag(
        ticker=ticker, detector=detector, direction=direction,
        severity=severity, score=score,
        explanation="test", last_close=100.0, day_change_pct=day_change_pct,
    )


def test_noisy_or_empty_is_zero():
    assert noisy_or([]) == 0.0


def test_noisy_or_single_is_identity():
    assert noisy_or([0.7]) == pytest.approx(0.7)


def test_noisy_or_combines_complements():
    # Same check Shizen's synthesis test pins: 1 - (1-0.7)(1-0.6) = 0.88
    assert noisy_or([0.7, 0.6]) == pytest.approx(0.88)


def test_best_flag_per_ticker_keeps_max_severity():
    flags = [
        _flag(detector="zscore", severity=0.55),
        _flag(detector="cusum", severity=0.8),
        _flag(ticker="RY.TO", detector="zscore", severity=0.6),
    ]
    best = best_flag_per_ticker(flags)
    assert set(best) == {"AAPL", "RY.TO"}
    assert best["AAPL"].detector == "cusum"


def test_severity_label_boundaries():
    assert severity_label(0.85) == "high"
    assert severity_label(0.6) == "medium"
    assert severity_label(0.59) == "low"


def test_fingerprint_deterministic_and_order_insensitive():
    d = date(2026, 7, 13)
    a = build_fingerprint(d, [_flag(), _flag(ticker="RY.TO")])
    b = build_fingerprint(d, [_flag(ticker="RY.TO"), _flag()])
    assert a == b
    assert a.startswith("price_anomaly:2026-07-13:")


def test_fingerprint_changes_with_date_and_content():
    flags = [_flag()]
    fp1 = build_fingerprint(date(2026, 7, 13), flags)
    fp2 = build_fingerprint(date(2026, 7, 14), flags)
    fp3 = build_fingerprint(date(2026, 7, 13), [_flag(direction="up")])
    assert len({fp1, fp2, fp3}) == 3


def test_fallback_message_single_ticker():
    headline, body = format_fallback_message([_flag()], 0.6)
    assert headline == "Unusual move in AAPL"
    assert "AAPL" in body
    assert len(body) <= 300


def test_fallback_message_many_tickers_stays_bounded():
    flags = [_flag(ticker=f"TICK{i}.TO", severity=0.6) for i in range(8)]
    headline, body = format_fallback_message(flags, 0.99)
    assert "8 holdings" in headline
    assert len(body) <= 300
    assert "+4 more" in body
