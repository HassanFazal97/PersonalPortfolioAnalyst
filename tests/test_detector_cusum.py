"""Ported from Shizen backend/tests/test_cusum.py (import path swap only)."""

import random
from datetime import datetime, timezone

import pytest

from app.detectors.cusum import CUSUMDetector


def _ts():
    return datetime.now(timezone.utc)


def test_warmup_no_flag_and_baseline_freezes():
    d = CUSUMDetector(warmup=50, delta=0.5, h=5.0)
    rng = random.Random(0)
    for i in range(49):
        r = d.update(rng.gauss(0, 1), _ts())
        assert not r.is_anomaly
        assert d.mu is None
    # last warmup sample triggers freeze
    d.update(rng.gauss(0, 1), _ts())
    assert d.mu is not None
    assert d.sigma is not None and d.sigma > 0


def test_in_control_low_false_positive_rate():
    d = CUSUMDetector(warmup=60, delta=0.5, h=5.0)
    rng = random.Random(1)
    # warmup
    for _ in range(60):
        d.update(rng.gauss(0, 1), _ts())
    fps = 0
    for _ in range(2000):
        r = d.update(rng.gauss(0, 1), _ts())
        fps += int(r.is_anomaly)
    # ARL₀ ≈ 465 means ~4 flags per 2000 in-control points; allow generous margin
    assert fps < 15, f"in-control FPR too high: {fps}/2000"


def test_sustained_shift_detected_within_reasonable_lag():
    d = CUSUMDetector(warmup=60, delta=0.5, h=5.0)
    rng = random.Random(2)
    for _ in range(60):
        d.update(rng.gauss(0, 1), _ts())
    # sustained +1σ shift — CUSUM should detect well before z-score's rolling mean catches up
    lag = None
    for i in range(200):
        r = d.update(rng.gauss(1.0, 1), _ts())
        if r.is_anomaly:
            lag = i + 1
            break
    assert lag is not None and lag < 40, f"shift detected too late or not at all: lag={lag}"


def test_flag_resets_cumulative_statistics():
    d = CUSUMDetector(warmup=30, delta=0.5, h=4.0)
    rng = random.Random(3)
    for _ in range(30):
        d.update(rng.gauss(0, 1), _ts())
    # force a flag with a big sustained shift
    flagged = False
    for _ in range(60):
        r = d.update(rng.gauss(3.0, 1), _ts())
        if r.is_anomaly:
            flagged = True
            assert d.S_h == 0.0 and d.S_l == 0.0
            break
    assert flagged


def test_direction_encoded_in_explanation():
    # The scanner derives direction from the explanation string because params
    # are written post-reset (S_h/S_l zeroed on flag) — pin that contract.
    d = CUSUMDetector(warmup=30, delta=0.5, h=4.0)
    rng = random.Random(4)
    for _ in range(30):
        d.update(rng.gauss(0, 1), _ts())
    for _ in range(60):
        r = d.update(rng.gauss(-3.0, 1), _ts())
        if r.is_anomaly:
            assert "downward" in r.explanation
            break
    else:
        pytest.fail("sustained downward shift never flagged")


def test_invalid_params_rejected():
    with pytest.raises(ValueError):
        CUSUMDetector(warmup=5)
    with pytest.raises(ValueError):
        CUSUMDetector(delta=-0.1)
    with pytest.raises(ValueError):
        CUSUMDetector(h=5.0, h_saturation=4.0)
