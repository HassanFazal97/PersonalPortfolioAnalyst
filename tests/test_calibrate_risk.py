"""Guardrails for the VaR-backtest statistics (Kupiec POF + Christoffersen).

Network-free: exercises only the pure statistical helpers on synthetic breach
sequences (the script's data-loading path hits yfinance and is not tested, like
scripts/calibrate_detectors.py)."""

from __future__ import annotations

import numpy as np

from scripts.calibrate_risk import christoffersen_cc, kupiec_pof


def test_kupiec_accepts_correctly_calibrated_series():
    rng = np.random.default_rng(0)
    breaches = (rng.random(2000) < 0.05).astype(int)
    _, p = kupiec_pof(breaches, 0.05)
    assert p > 0.05  # rate matches the claim -> do not reject


def test_kupiec_rejects_understated_risk():
    rng = np.random.default_rng(1)
    # 15% breaches while claiming a 5% VaR -> the model understates risk badly.
    breaches = (rng.random(2000) < 0.15).astype(int)
    _, p = kupiec_pof(breaches, 0.05)
    assert p < 0.01  # strongly rejected


def test_kupiec_handles_zero_breaches():
    breaches = np.zeros(500, dtype=int)
    lr, p = kupiec_pof(breaches, 0.05)
    # Zero breaches is itself evidence against a 5% rate over 500 days.
    assert lr > 0 and 0.0 <= p <= 1.0


def test_christoffersen_accepts_independent_breaches():
    rng = np.random.default_rng(2)
    breaches = (rng.random(2000) < 0.05).astype(int)
    _, p = christoffersen_cc(breaches, 0.05)
    assert p > 0.05


def test_christoffersen_rejects_clustered_breaches():
    # Same total count, but all breaches bunched together -> dependence.
    breaches = np.array([0] * 1900 + [1] * 100)
    _, p = christoffersen_cc(breaches, 0.05)
    assert p < 0.05
