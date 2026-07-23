"""Result reporting, baseline compare, cost governor, and exit codes.

Exit codes: 0 clean / 1 confirmed regression or classifier below floor /
2 infra error (API failure, majority judge_error, budget-skipped cases).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import price_for
from evals.schema import CaseResult

EVALS_DIR = Path(__file__).resolve().parent
BASELINES_DIR = EVALS_DIR / "baselines"
RESULTS_DIR = EVALS_DIR / "results"

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_INFRA = 2


class CostTracker:
    """Asyncio-safe-enough (single loop, no awaits inside) global governor."""

    def __init__(self, max_cost_usd: float) -> None:
        self.max_cost_usd = max_cost_usd
        self.cost_usd = 0.0

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.cost_usd += price_for(model).cost(input_tokens, output_tokens)

    def record_flat(self, usd: float) -> None:
        self.cost_usd += usd

    @property
    def exhausted(self) -> bool:
        return self.cost_usd >= self.max_cost_usd


def load_baseline(name: str) -> dict:
    path = BASELINES_DIR / f"{name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_baseline(name: str, data: dict) -> None:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    (BASELINES_DIR / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")


def regressions(
    results: list[CaseResult], baseline: dict
) -> list[str]:
    """Case ids that were passing in the baseline but fail now."""
    base_pass = baseline.get("cases", {})
    return [
        r.case_id
        for r in results
        if base_pass.get(r.case_id) is True and not r.passed
    ]


def write_reports(
    *,
    prompt_version: str,
    judge_prompt_version: str,
    model: str,
    judge_model: str,
    chat_results: list[CaseResult],
    classifier: dict | None,
    total_cost_usd: float,
    baseline: dict,
    regressed: list[str],
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Not Path.with_suffix: prompt versions contain dots ("2026-07-22.5")
    # and with_suffix would eat the last segment.
    base = RESULTS_DIR / f"{stamp}_{prompt_version}"
    json_path = base.parent / (base.name + ".json")
    md_path = base.parent / (base.name + ".md")

    payload = {
        "prompt_version": prompt_version,
        "judge_prompt_version": judge_prompt_version,
        "model": model,
        "judge_model": judge_model,
        "total_cost_usd": round(total_cost_usd, 4),
        "baseline_prompt_version": baseline.get("prompt_version"),
        "regressions": regressed,
        "chat": [r.model_dump() for r in chat_results],
        "classifier": classifier,
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str))

    lines = [
        f"# Eval report — {stamp}",
        "",
        f"- prompt_version: `{prompt_version}` (baseline: `{baseline.get('prompt_version', 'none')}`)",
        f"- model: `{model}` · judge: `{judge_model}` (judge prompt `{judge_prompt_version}`)",
        f"- total cost: ${total_cost_usd:.3f}",
        "",
    ]
    if chat_results:
        passed = sum(1 for r in chat_results if r.passed)
        lines += [f"## Chat — {passed}/{len(chat_results)} passed", ""]
        lines += ["| case | pass | tools | notes |", "|---|---|---|---|"]
        for r in chat_results:
            notes = []
            if r.error:
                notes.append(f"error: {r.error}")
            notes += [f"det-fail: {d}" for d in r.deterministic_failures]
            if r.expected_tools_missing:
                notes.append("missing tools: " + ",".join(r.expected_tools_missing))
            if r.fixture_misses:
                notes.append("fixture miss: " + ",".join(sorted(set(r.fixture_misses))))
            if r.verdict:
                if r.verdict.judge_error:
                    notes.append("JUDGE ERROR")
                notes += [f"hallucination: {h}" for h in r.verdict.hallucinations]
                notes += [
                    f"criterion '{c['id']}' failed: {c['reasoning']}"
                    for c in r.verdict.criteria
                    if not c["pass"]
                ]
            mark = "✅" if r.passed else "❌"
            if r.case_id in regressed:
                mark = "❌ REGRESSION"
            lines.append(
                f"| {r.case_id} | {mark} | {', '.join(r.tools_used)} | {'; '.join(notes)[:400]} |"
            )
        lines.append("")
    if classifier:
        lines += [
            f"## Classifier — accuracy {classifier['accuracy']:.2%} "
            f"(floor {classifier['floor']:.2%})",
            "",
            "confusion (rows=expected, cols=predicted):",
            "```",
            classifier["confusion_text"],
            "```",
            "",
        ]
    md_path.write_text("\n".join(lines))
    return md_path
