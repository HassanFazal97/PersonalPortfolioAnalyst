"""News-classifier eval: exact-match signal accuracy over labeled headlines.

No judge needed — labels are categorical. Salience is checked only as a loose
band and reported, never gated (it's inherently fuzzy).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.tools import classify

GOLDEN = Path(__file__).resolve().parent / "golden" / "classifier_headlines.jsonl"

_SIGNALS = ("warning", "opportunity", "neutral")
_BATCH = 10
ACCURACY_FLOOR = 0.85


def load_headlines() -> list[dict[str, Any]]:
    rows = []
    for line in GOLDEN.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


async def run_classifier_eval(client: Any, model: str, cost_tracker) -> dict[str, Any]:
    rows = load_headlines()
    classify.cache_clear()  # module-global headline cache would mask calls
    predictions: list[str] = []
    for start in range(0, len(rows), _BATCH):
        batch = rows[start : start + _BATCH]
        items = [
            {"headline": r["headline"], "summary": r.get("summary", "")} for r in batch
        ]
        labels, usage, _log = await classify._classify_batch(client, model, items)
        cost_tracker.record(
            model,
            int(usage.get("input_tokens", 0)),
            int(usage.get("output_tokens", 0)),
        )
        for label in labels:  # index-aligned list, neutral on gaps
            predictions.append((label or {}).get("signal", "neutral"))

    correct = sum(
        1 for r, p in zip(rows, predictions) if r["expected_signal"] == p
    )
    accuracy = correct / len(rows) if rows else 0.0

    confusion = {e: {p: 0 for p in _SIGNALS} for e in _SIGNALS}
    for r, p in zip(rows, predictions):
        confusion[r["expected_signal"]][p if p in _SIGNALS else "neutral"] += 1
    header = f"{'':>12}" + "".join(f"{p:>12}" for p in _SIGNALS)
    body = "\n".join(
        f"{e:>12}" + "".join(f"{confusion[e][p]:>12}" for p in _SIGNALS)
        for e in _SIGNALS
    )
    return {
        "total": len(rows),
        "correct": correct,
        "accuracy": accuracy,
        "floor": ACCURACY_FLOOR,
        "passed": accuracy >= ACCURACY_FLOOR,
        "confusion": confusion,
        "confusion_text": f"{header}\n{body}",
    }
