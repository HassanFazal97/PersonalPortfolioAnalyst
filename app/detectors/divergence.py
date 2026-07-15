"""Inter-stream divergence detector (ported from Shizen).

Watches the rolling Pearson correlation ρ_t between two streams that were
historically correlated — e.g. a holding's returns vs a benchmark ETF's.
Flags when the *current* correlation has dropped significantly below a
frozen baseline ρ̄.

Why Fisher's z-transform: raw ρ ∈ (−1, 1) is *not* normally distributed —
its sampling distribution is heavily skewed near ±1, which makes a
straight z-test on ρ misbehave. Fisher's transformation

    z(ρ) = ½ ln((1 + ρ) / (1 − ρ))   =   atanh(ρ)

maps ρ to an approximately Gaussian variable with standard error
SE = 1 / √(W − 3), making the test statistic

    T = (z(ρ̄) − z(ρ_t)) / SE

approximately N(0, 1) under the null of unchanged correlation. Flag when
T > `threshold` (one-sided — we only care about correlation *dropping*).

The peer stream's latest value is supplied by the caller via
`context["peer_value"]`. Calibration window establishes the baseline once;
after that ρ̄ is frozen, mirroring CUSUM's frozen-baseline approach. The
detector explicitly does not flag during the calibration phase.

The Fisher-z test assumes iid samples; autocorrelated series over-disperse
the statistic, so the operating threshold must be validated empirically
(scripts/calibrate_detectors.py) rather than read off the Gaussian table.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from math import atanh, sqrt, tanh
from typing import Any, ClassVar

from .base import AnomalyDetector, DetectionResult


class DivergenceDetector(AnomalyDetector):
    name: ClassVar[str] = "divergence"

    def __init__(
        self,
        peer: str,
        window: int = 60,
        calibration: int = 200,
        threshold: float = 5.0,
        threshold_saturation: float = 10.0,
    ):
        if not peer:
            raise ValueError("peer stream name required")
        if window < 10:
            raise ValueError("window must be >= 10")
        if calibration < window:
            raise ValueError("calibration must be >= window")
        if threshold <= 0 or threshold_saturation <= threshold:
            raise ValueError("require 0 < threshold < threshold_saturation")
        self.peer = peer
        self.window = window
        self.calibration = calibration
        self.threshold = threshold
        self.threshold_saturation = threshold_saturation
        cap = max(window, calibration)
        self._own: deque[float] = deque(maxlen=cap)
        self._peer: deque[float] = deque(maxlen=cap)
        self.baseline_z: float | None = None

    @staticmethod
    def _pearson(xs: list[float], ys: list[float]) -> float | None:
        n = len(xs)
        if n < 2:
            return None
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        sx = sum((x - mx) ** 2 for x in xs) ** 0.5
        sy = sum((y - my) ** 2 for y in ys) ** 0.5
        if sx == 0.0 or sy == 0.0:
            return None
        return num / (sx * sy)

    @staticmethod
    def _fisher_z(rho: float) -> float:
        # clamp to avoid infinity at ρ = ±1
        rho = max(-0.999999, min(0.999999, rho))
        return atanh(rho)

    def update(
        self, value: float, timestamp: datetime, **context: Any
    ) -> DetectionResult:
        # Callers may pass a dict of all known peer stream values, or the
        # single-value form (tests, calibration script, scanner).
        peer_values = context.get("peer_values")
        if isinstance(peer_values, dict):
            peer_val = peer_values.get(self.peer)
        else:
            peer_val = context.get("peer_value")
        if peer_val is None:
            return DetectionResult(
                is_anomaly=False,
                severity=0.0,
                score=0.0,
                method=self.name,
                explanation=f"awaiting peer {self.peer!r}",
                params={"peer": self.peer},
            )

        self._own.append(value)
        self._peer.append(float(peer_val))
        n = len(self._own)

        # Calibration phase: collect samples, then freeze baseline ρ̄ and z(ρ̄).
        if self.baseline_z is None:
            if n < self.calibration:
                return DetectionResult(
                    is_anomaly=False,
                    severity=0.0,
                    score=0.0,
                    method=self.name,
                    explanation=f"calibrating baseline ρ ({n}/{self.calibration})",
                    params={"n": n, "calibration": self.calibration, "peer": self.peer},
                )
            rho_base = self._pearson(list(self._own), list(self._peer))
            if rho_base is None:
                return DetectionResult(
                    is_anomaly=False,
                    severity=0.0,
                    score=0.0,
                    method=self.name,
                    explanation="calibration failed: zero-variance series",
                    params={"peer": self.peer},
                )
            self.baseline_z = self._fisher_z(rho_base)
            return DetectionResult(
                is_anomaly=False,
                severity=0.0,
                score=0.0,
                method=self.name,
                explanation=f"baseline calibrated: ρ̄={rho_base:.3f} (peer={self.peer})",
                params={"rho_baseline": rho_base, "peer": self.peer},
            )

        # Test phase: rolling Pearson over last `window` samples
        own_w = list(self._own)[-self.window :]
        peer_w = list(self._peer)[-self.window :]
        rho_t = self._pearson(own_w, peer_w)
        if rho_t is None:
            return DetectionResult(
                is_anomaly=False,
                severity=0.0,
                score=0.0,
                method=self.name,
                explanation="ρ_t undefined (zero variance in window)",
                params={"peer": self.peer},
            )
        z_t = self._fisher_z(rho_t)
        se = 1.0 / sqrt(self.window - 3)
        T = (self.baseline_z - z_t) / se  # positive => correlation dropped
        is_anom = T > self.threshold
        severity = max(0.0, min(1.0, T / self.threshold_saturation))
        rho_base = tanh(self.baseline_z)
        relation = ">" if is_anom else "≤"
        explanation = (
            f"divergence T={T:.2f} {relation} {self.threshold}; "
            f"ρ_t={rho_t:.3f} vs ρ̄={rho_base:.3f} (peer={self.peer}, W={self.window})"
        )
        return DetectionResult(
            is_anomaly=is_anom,
            severity=severity,
            score=T,
            method=self.name,
            explanation=explanation,
            params={
                "rho_t": rho_t,
                "rho_baseline": rho_base,
                "T": T,
                "SE": se,
                "peer": self.peer,
            },
        )

    def explain(self) -> str:
        baseline = (
            "uncalibrated"
            if self.baseline_z is None
            else f"ρ̄={tanh(self.baseline_z):.3f}"
        )
        return (
            f"Inter-stream divergence detector vs peer={self.peer!r} "
            f"(window={self.window}, threshold={self.threshold}, baseline={baseline}). "
            "Fisher-transformed correlation test; flags when rolling ρ falls "
            "significantly below its historical baseline."
        )

    def reset(self) -> None:
        self._own.clear()
        self._peer.clear()
        self.baseline_z = None
