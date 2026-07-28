"""Deterministic evidence verification for pick analyses. Pure functions.

The analyst prompt requires every ``valuation_evidence`` entry to reference a
fact-sheet metric name verbatim with the fact sheet's value. This module is
the machine check behind that rule: unknown metrics are dropped, drifted
values are repaired to the canonical fact-sheet number, and every action is
recorded — so the numbers rendered on the dashboard are provably from source
data, with no LLM in the loop.
"""

from __future__ import annotations

from typing import Any

# An evidence value within this relative tolerance of the fact sheet passes
# untouched (covers benign rounding); beyond it, the entry is repaired.
RELATIVE_TOLERANCE = 0.02


def _close(a: float, b: float) -> bool:
    scale = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / scale <= RELATIVE_TOLERANCE


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def verify_evidence(
    evidence: list[Any] | None, fact_metrics: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Check analyst ``valuation_evidence`` against the fact sheet's
    ``metrics`` block (``{name: {value, sector_median}}``).

    Returns (verified entries, notes). Unknown metric names are dropped;
    values/medians that drift beyond tolerance are replaced with the
    canonical fact-sheet numbers and noted as repaired.
    """
    verified: list[dict[str, Any]] = []
    notes: list[str] = []
    for entry in evidence or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("metric")
        fact = fact_metrics.get(name) if isinstance(name, str) else None
        if fact is None:
            notes.append(f"dropped unknown metric {name!r}")
            continue
        fact_value = _num(fact.get("value"))
        fact_median = _num(fact.get("sector_median"))
        if fact_value is None:
            notes.append(f"dropped {name}: no fact-sheet value")
            continue

        claimed_value = _num(entry.get("value"))
        claimed_median = _num(entry.get("sector_median"))
        repaired = False
        if claimed_value is None or not _close(claimed_value, fact_value):
            repaired = True
        if fact_median is not None and (
            claimed_median is None or not _close(claimed_median, fact_median)
        ):
            repaired = True

        out = {"metric": name, "value": fact_value, "sector_median": fact_median}
        if repaired:
            out["repaired"] = True
            notes.append(f"repaired {name} to fact-sheet values")
        verified.append(out)
    return verified, notes
