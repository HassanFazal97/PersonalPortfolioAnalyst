"""Ported from Shizen backend/tests/test_zscore.py (import path swap only)."""

import random
from datetime import datetime, timezone

import pytest

from app.detectors.zscore import ZScoreDetector


def _ts():
    return datetime.now(timezone.utc)


def test_warmup_does_not_flag():
    d = ZScoreDetector(window=20, k=3.0, min_samples=10)
    rng = random.Random(0)
    flagged = 0
    for _ in range(9):
        r = d.update(rng.gauss(0, 1), _ts())
        assert r.is_anomaly is False
        assert "warming up" in r.explanation
        flagged += int(r.is_anomaly)
    assert flagged == 0


def test_quiet_series_does_not_flag():
    d = ZScoreDetector(window=60, k=3.0)
    rng = random.Random(1)
    fps = 0
    for _ in range(2000):
        r = d.update(rng.gauss(0, 1), _ts())
        fps += int(r.is_anomaly)
    # Under a Gaussian null at k=3 we expect ~0.27% FPR. With 2000 samples that's ~5 FPs.
    # Allow generous slack — this is a sanity check, not a calibration test.
    assert fps < 30, f"unexpectedly high FPR: {fps}/2000"


def test_spike_after_warmup_flags_with_high_severity():
    d = ZScoreDetector(window=30, k=3.0, k_saturation=6.0)
    rng = random.Random(2)
    for _ in range(50):
        d.update(rng.gauss(0, 1), _ts())
    r = d.update(8.0, _ts())
    assert r.is_anomaly
    assert r.severity >= 0.8
    assert r.score > 3.0


def test_constant_series_flags_inf_z_on_deviation():
    d = ZScoreDetector(window=20, k=3.0)
    for _ in range(25):
        d.update(5.0, _ts())
    r = d.update(5.0001, _ts())
    # σ is exactly 0 in the prior window; any deviation is "infinite z"
    assert r.is_anomaly
    assert r.severity == 1.0


def test_reset_clears_window():
    d = ZScoreDetector(window=10, k=3.0)
    for _ in range(20):
        d.update(0.0, _ts())
    d.reset()
    r = d.update(0.0, _ts())
    assert "warming up" in r.explanation


def test_method_name_set_without_registry():
    # Shizen set `name` via its @register decorator; the port sets it on the
    # class directly. An empty method string means the port regressed.
    d = ZScoreDetector(window=20, k=3.0, min_samples=10)
    r = d.update(0.0, _ts())
    assert r.method == "zscore"


def test_invalid_params_rejected():
    with pytest.raises(ValueError):
        ZScoreDetector(window=2)
    with pytest.raises(ValueError):
        ZScoreDetector(k=0)
    with pytest.raises(ValueError):
        ZScoreDetector(k=3.0, k_saturation=2.0)
