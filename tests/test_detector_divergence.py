"""Ported from Shizen backend/tests/test_divergence.py.

Shizen's tests drove this detector with its multi-stream Simulator;
``_CorrelatedPair`` below is a minimal stand-in reproducing the relevant
structure: two series driven by a shared AR(1) latent factor (so they are
correlated by construction), with a ``break_correlation()`` that forks one
series onto its own independent latent — severing the correlation without
changing the marginal distribution.
"""

import random
from datetime import datetime, timezone

import pytest

from app.detectors.divergence import DivergenceDetector


def _ts():
    return datetime.now(timezone.utc)


class _CorrelatedPair:
    def __init__(self, seed: int, phi: float = 0.95, latent_sigma: float = 0.2):
        self.rng = random.Random(seed)
        self.phi = phi
        self.latent_sigma = latent_sigma
        self.latent = 0.0
        self.broken = False
        self.broken_latent = 0.0

    def break_correlation(self) -> None:
        self.broken = True
        # seed independent latent at current shared value to avoid a step
        self.broken_latent = self.latent

    def step(self) -> tuple[float, float]:
        """Return (own, peer) — correlated until break_correlation()."""
        self.latent = self.phi * self.latent + self.rng.gauss(0.0, self.latent_sigma)
        if self.broken:
            self.broken_latent = (
                self.phi * self.broken_latent + self.rng.gauss(0.0, self.latent_sigma)
            )
        own_latent = self.broken_latent if self.broken else self.latent
        own = 150.0 + 10.0 * own_latent + self.rng.gauss(0.0, 2.0)
        peer = 15.0 + 2.0 * self.latent + self.rng.gauss(0.0, 0.5)
        return own, peer


def test_returns_no_flag_without_peer_value():
    d = DivergenceDetector(peer="vol", window=20, calibration=20)
    r = d.update(1.0, _ts())
    assert not r.is_anomaly
    assert "awaiting peer" in r.explanation


def test_calibration_phase_never_flags():
    """Calibration-phase results must never claim is_anomaly=True regardless of data."""
    d = DivergenceDetector(peer="vol", window=60, calibration=200)
    pair = _CorrelatedPair(seed=10)
    for _ in range(200):
        own, peer = pair.step()
        r = d.update(own, _ts(), peer_value=peer)
        assert not r.is_anomaly
    assert d.baseline_z is not None


def test_baseline_quiet_run_fpr_within_empirical_bound():
    """Series are AR(1)-autocorrelated, so FPR exceeds the iid-Fisher prediction.
    Default threshold is empirically calibrated; this guards the upper bound."""
    d = DivergenceDetector(peer="vol", window=60, calibration=200)
    pair = _CorrelatedPair(seed=10)
    flags_post_calib = 0
    for t in range(700):
        own, peer = pair.step()
        r = d.update(own, _ts(), peer_value=peer)
        if t >= 200:
            flags_post_calib += int(r.is_anomaly)
    # Empirical FPR at threshold=5.0 averages ~5% on AR(1) streams; allow up to 12% per single-seed run.
    assert flags_post_calib < 60


def test_correlation_break_triggers_divergence():
    d = DivergenceDetector(peer="vol", window=60, calibration=200, threshold=3.0)
    pair = _CorrelatedPair(seed=11)
    break_at = 300
    first_flag = None
    for t in range(700):
        if t == break_at:
            pair.break_correlation()
        own, peer = pair.step()
        r = d.update(own, _ts(), peer_value=peer)
        if r.is_anomaly and first_flag is None and t > break_at:
            first_flag = t
    assert first_flag is not None, "divergence detector failed to fire after correlation break"
    lag = first_flag - break_at
    # Window is 60, so theoretically possible to detect within ~window/2 ticks
    assert lag < 80, f"divergence detected too late: lag={lag}"


def test_peer_values_dict_form_supported():
    d = DivergenceDetector(peer="vol", window=20, calibration=20)
    r = d.update(1.0, _ts(), peer_values={"other": 2.0})
    assert "awaiting peer" in r.explanation
    r = d.update(1.0, _ts(), peer_values={"vol": 2.0})
    assert "calibrating" in r.explanation


def test_invalid_params_rejected():
    with pytest.raises(ValueError):
        DivergenceDetector(peer="")
    with pytest.raises(ValueError):
        DivergenceDetector(peer="vol", window=5)
    with pytest.raises(ValueError):
        DivergenceDetector(peer="vol", window=60, calibration=30)
    with pytest.raises(ValueError):
        DivergenceDetector(peer="vol", threshold=0)


def test_reset_clears_baseline_and_buffers():
    d = DivergenceDetector(peer="vol", window=20, calibration=20)
    for i in range(25):
        d.update(float(i), _ts(), peer_value=float(i) * 1.1)
    assert d.baseline_z is not None
    d.reset()
    assert d.baseline_z is None
    assert len(d._own) == 0
