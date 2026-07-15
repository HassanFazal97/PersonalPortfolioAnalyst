"""Page's CUSUM (Cumulative Sum) change-point detector (ported from Shizen).

Recursive form on standardized observations y_t = (x_t − μ₀) / σ:

    S_h^t = max(0, S_h^{t−1} + y_t − δ)        (upper, catches mean shifts up)
    S_l^t = max(0, S_l^{t−1} − y_t − δ)        (lower, catches mean shifts down)

Flag when max(S_h, S_l) > h. After a flag both statistics are reset to 0 so
the detector remains alive (otherwise it would latch on indefinitely).

μ₀ and σ are estimated from a warm-up window of `warmup` observations and then
*frozen*. Adaptive baselines defeat CUSUM's purpose — the whole point is to
detect sustained drift away from a reference distribution. After a regime
change, the caller can `reset()` to re-baseline.

Under a Gaussian null, δ = 0.5 / h = 5.0 give an average run length to a
false alarm (ARL₀) of ≈465 observations, and δ = 0.5 is tuned for a 1σ mean
shift. On daily returns that reads as roughly two years between false alarms
per ticker; validate with scripts/calibrate_detectors.py.
"""

from __future__ import annotations

from datetime import datetime
from statistics import fmean, pstdev
from typing import Any, ClassVar

from .base import AnomalyDetector, DetectionResult


class CUSUMDetector(AnomalyDetector):
    name: ClassVar[str] = "cusum"

    def __init__(
        self,
        warmup: int = 60,
        delta: float = 0.5,
        h: float = 6.0,
        h_saturation: float = 12.0,
    ):
        if warmup < 10:
            raise ValueError("warmup must be >= 10")
        if delta <= 0:
            raise ValueError("delta must be > 0")
        if h <= 0 or h_saturation <= h:
            raise ValueError("require 0 < h < h_saturation")
        self.warmup = warmup
        self.delta = delta
        self.h = h
        self.h_saturation = h_saturation
        self._warmup_buf: list[float] = []
        self.mu: float | None = None
        self.sigma: float | None = None
        self.S_h: float = 0.0
        self.S_l: float = 0.0

    def update(
        self, value: float, timestamp: datetime, **context: Any
    ) -> DetectionResult:
        if self.mu is None:
            self._warmup_buf.append(value)
            n = len(self._warmup_buf)
            if n < self.warmup:
                return DetectionResult(
                    is_anomaly=False,
                    severity=0.0,
                    score=0.0,
                    method=self.name,
                    explanation=f"warming up ({n}/{self.warmup})",
                    params={"n": n, "warmup": self.warmup},
                )
            self.mu = fmean(self._warmup_buf)
            self.sigma = pstdev(self._warmup_buf, mu=self.mu) or 1e-9
            self._warmup_buf = []  # release; baseline now frozen

        assert self.mu is not None and self.sigma is not None
        y = (value - self.mu) / self.sigma
        self.S_h = max(0.0, self.S_h + y - self.delta)
        self.S_l = max(0.0, self.S_l - y - self.delta)
        score = max(self.S_h, self.S_l)
        is_anom = score > self.h
        severity = min(1.0, score / self.h_saturation)

        if is_anom:
            direction = "upward" if self.S_h > self.S_l else "downward"
            explanation = (
                f"CUSUM {direction} shift detected: S={score:.2f} > h={self.h} "
                f"(δ={self.delta}, μ₀={self.mu:.4f}, σ={self.sigma:.4f})"
            )
            self.S_h = 0.0
            self.S_l = 0.0
        else:
            explanation = (
                f"CUSUM in-control: S_h={self.S_h:.2f}, S_l={self.S_l:.2f}, h={self.h}"
            )

        return DetectionResult(
            is_anomaly=is_anom,
            severity=severity,
            score=score,
            method=self.name,
            explanation=explanation,
            params={
                "S_h": self.S_h,
                "S_l": self.S_l,
                "h": self.h,
                "delta": self.delta,
                "mu0": self.mu,
                "sigma0": self.sigma,
            },
        )

    def explain(self) -> str:
        baseline = (
            "uncalibrated" if self.mu is None else f"μ₀={self.mu:.3f}, σ={self.sigma:.3f}"
        )
        return (
            f"CUSUM change-point detector (δ={self.delta}, h={self.h}, "
            f"warmup={self.warmup}, baseline={baseline}). "
            "Accumulates standardized deviations; flags sustained shifts that a "
            "rolling-baseline z-score self-masks."
        )

    def reset(self) -> None:
        self._warmup_buf = []
        self.mu = None
        self.sigma = None
        self.S_h = 0.0
        self.S_l = 0.0
