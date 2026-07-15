"""Detector ABC + result schema (ported from Shizen).

The detector interface is single-stream by default: `update(value, timestamp, **context)`.
Multi-stream detectors (e.g. inter-stream divergence) read peer values out of `context`
without changing the signature.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class DetectionResult(BaseModel):
    """One detector's verdict on one observation.

    severity ∈ [0, 1] is normalized so the aggregation layer can combine results
    across detectors with different raw scales. score is the raw statistic
    *before* thresholding — useful for visualization and debugging.
    """

    is_anomaly: bool
    severity: float = Field(ge=0.0, le=1.0)
    score: float
    method: str
    explanation: str
    params: dict[str, Any] = Field(default_factory=dict)


class AnomalyDetector(ABC):
    """Abstract detector. Subclasses set a class-level `name`."""

    name: ClassVar[str] = ""

    @abstractmethod
    def update(
        self, value: float, timestamp: datetime, **context: Any
    ) -> DetectionResult:
        """Ingest one data point and emit a DetectionResult.

        `context` is a free-form dict the caller populates (e.g. peer
        stream values for the divergence detector). Single-stream detectors
        ignore it.
        """

    @abstractmethod
    def explain(self) -> str:
        """Plain-English description of *what this detector does* and its
        current parameters. Feeds the LLM narration prompt."""

    def reset(self) -> None:
        """Optional. Override if the detector holds rolling state and the
        caller needs to clear it."""
