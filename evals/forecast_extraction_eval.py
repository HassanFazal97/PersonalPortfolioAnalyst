"""Forecast-extraction eval: claim-level precision/recall over golden texts.

No LLM judge — matching is deterministic (normalized verbatim claim_text +
claim_type), the ``classifier_eval.py`` posture. Regression-gates extractor
prompt changes: the trust story dies if the ledger scores claims the analyst
never made (precision) or misses the ones it did (recall). Adversarial
cases with zero expected claims exist to punish over-extraction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.agent.forecasts import extract

GOLDEN = Path(__file__).resolve().parent / "golden" / "forecast_extraction.yaml"

PRECISION_FLOOR = 0.70
RECALL_FLOOR = 0.70


def load_cases() -> list[dict[str, Any]]:
    return yaml.safe_load(GOLDEN.read_text())["cases"]


def _norm(text: str) -> str:
    return " ".join(text.split()).rstrip(".").lower()


def score_case(
    predicted: list[dict[str, Any]], expected: list[dict[str, Any]]
) -> dict[str, int]:
    """Greedy match on (normalized claim_text, claim_type); direction
    correctness is scored on matched pairs only."""
    remaining = list(expected)
    matched = 0
    direction_ok = 0
    for p in predicted:
        for e in remaining:
            if _norm(p["claim_text"]) == _norm(e["claim_text"]) and p[
                "claim_type"
            ] == e["claim_type"]:
                matched += 1
                if p.get("direction") == e.get("direction"):
                    direction_ok += 1
                remaining.remove(e)
                break
    return {
        "predicted": len(predicted),
        "expected": len(expected),
        "matched": matched,
        "direction_ok": direction_ok,
    }


async def run_forecast_extraction_eval(
    client: Any, model: str, cost_tracker
) -> dict[str, Any]:
    cases = load_cases()
    totals = {"predicted": 0, "expected": 0, "matched": 0, "direction_ok": 0}
    per_case = []
    for case in cases:
        claims, drops, usage, _log = await extract.extract_claims(
            client, model, case["text"]
        )
        cost_tracker.record(
            model,
            int(usage.get("input_tokens", 0)),
            int(usage.get("output_tokens", 0)),
        )
        scores = score_case(claims, case.get("expected") or [])
        scores["id"] = case["id"]
        scores["drops"] = drops
        per_case.append(scores)
        for k in totals:
            totals[k] += scores[k]

    precision = totals["matched"] / totals["predicted"] if totals["predicted"] else 1.0
    recall = totals["matched"] / totals["expected"] if totals["expected"] else 1.0
    return {
        "cases": len(cases),
        "precision": precision,
        "recall": recall,
        "direction_accuracy": (
            totals["direction_ok"] / totals["matched"] if totals["matched"] else None
        ),
        "precision_floor": PRECISION_FLOOR,
        "recall_floor": RECALL_FLOOR,
        "passed": precision >= PRECISION_FLOOR and recall >= RECALL_FLOOR,
        "per_case": per_case,
        "extractor_version": extract.FORECAST_EXTRACTOR_VERSION,
    }
