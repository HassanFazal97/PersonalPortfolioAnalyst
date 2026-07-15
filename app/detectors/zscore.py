"""Rolling z-score detector (ported from Shizen).

z_t = (x_t - μ_{t-1}) / σ_{t-1}    where μ, σ are computed over the prior
window of W observations. The new point is tested against history, then
appended — so a single outlier doesn't self-mask in its own baseline.

Flag iff |z_t| > k. Default k = 3.0 gives a per-sample false-positive rate of
≈0.27 % under a Gaussian null. Severity = clip(|z| / k_saturation, 0, 1).

Limitation worth knowing (and motivates CUSUM): for a *sustained* level
shift, the rolling mean follows the new level within W observations and the
signal self-masks. Z-score is best at point/spike anomalies in stationary
signals — feed it daily log returns, not raw prices.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from statistics import fmean, pstdev
from typing import Any, ClassVar

from .base import AnomalyDetector, DetectionResult


class ZScoreDetector(AnomalyDetector):
    name: ClassVar[str] = "zscore"

    def __init__(
        self,
        window: int = 60,
        k: float = 3.0,
        k_saturation: float = 6.0,
        min_samples: int | None = None,
    ):
        if window < 3:
            raise ValueError("window must be >= 3")
        if k <= 0 or k_saturation <= k:
            raise ValueError("require 0 < k < k_saturation")
        self.window = window
        self.k = k
        self.k_saturation = k_saturation
        self.min_samples = min_samples if min_samples is not None else max(10, window // 2)
        self._buf: deque[float] = deque(maxlen=window)

    def update(
        self, value: float, timestamp: datetime, **context: Any
    ) -> DetectionResult:
        n = len(self._buf)
        if n < self.min_samples:
            self._buf.append(value)
            return DetectionResult(
                is_anomaly=False,
                severity=0.0,
                score=0.0,
                method=self.name,
                explanation=f"warming up ({n + 1}/{self.min_samples})",
                params={"n": n + 1, "min_samples": self.min_samples},
            )

        mu = fmean(self._buf)
        sigma = pstdev(self._buf, mu=mu)

        if sigma == 0.0:
            z = 0.0 if value == mu else float("inf")
        else:
            z = (value - mu) / sigma

        abs_z = abs(z)
        is_anom = abs_z > self.k
        if abs_z == float("inf"):
            severity = 1.0
            score_for_result = 1e6 if z > 0 else -1e6
        else:
            severity = min(1.0, abs_z / self.k_saturation)
            score_for_result = z

        relation = ">" if is_anom else "≤"
        explanation = (
            f"|z|={abs_z:.2f} {relation} k={self.k}; "
            f"x={value:.4f} vs μ={mu:.4f}, σ={sigma:.4f} (W={self.window})"
        )

        self._buf.append(value)
        return DetectionResult(
            is_anomaly=is_anom,
            severity=severity,
            score=score_for_result,
            method=self.name,
            explanation=explanation,
            params={"mu": mu, "sigma": sigma, "z": score_for_result, "k": self.k, "n": n},
        )

    def explain(self) -> str:
        return (
            f"Rolling z-score detector (window={self.window}, k={self.k}). "
            "Flags points whose deviation from the recent rolling mean exceeds "
            f"{self.k}σ. Sensitive to point/spike anomalies; less effective "
            "against sustained level shifts (rolling mean follows the shift)."
        )

    def reset(self) -> None:
        self._buf.clear()
