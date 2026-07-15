"""Statistical anomaly detectors (ported from Shizen).

Pure Python + stdlib; no LLM involvement. Math decides whether something is
anomalous — the LLM only narrates afterward (app/agent/anomaly/).
"""

from .base import AnomalyDetector, DetectionResult
from .cusum import CUSUMDetector
from .divergence import DivergenceDetector
from .zscore import ZScoreDetector

__all__ = [
    "AnomalyDetector",
    "DetectionResult",
    "ZScoreDetector",
    "CUSUMDetector",
    "DivergenceDetector",
]
