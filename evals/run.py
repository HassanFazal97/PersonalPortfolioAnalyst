"""Eval runner: real model + real agent loop + fake tools + FakeRepo.

  python -m evals.run --suite all                 # chat + classifier
  python -m evals.run --suite chat --case <id>    # one case
  python -m evals.run --update-baseline           # after a reviewed change

Regression = a case that passed in the baseline fails now; flipped cases are
re-run at N=3 and must fail 2/3 to confirm (bounds model nondeterminism
without tripling the whole run's cost). See evals/report.py for exit codes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import AsyncAnthropic  # noqa: E402

from app.agent.budget import Budget  # noqa: E402
from app.agent.chat_context import compose_chat_system_prompt  # noqa: E402
from app.agent.loop import run_agent  # noqa: E402
from app.agent.prompts import CHAT_SYSTEM_PROMPT, PROMPT_VERSION  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.tools.registry import CHAT_TOOLS, ToolContext  # noqa: E402
from evals.classifier_eval import run_classifier_eval  # noqa: E402
from evals.fake_tools import build_fake_dispatch  # noqa: E402
from evals.judge import JUDGE_PROMPT_VERSION, run_judge  # noqa: E402
from evals.report import (  # noqa: E402
    EXIT_INFRA,
    EXIT_OK,
    EXIT_REGRESSION,
    CostTracker,
    load_baseline,
    regressions,
    save_baseline,
    write_reports,
)
from evals.schema import CaseResult, GoldenCase  # noqa: E402
from tests.fakes import FakeRepo  # noqa: E402  (deliberate reuse of the test double;

#                                     it satisfies the Repo interface without Postgres)

GOLDEN_CHAT = Path(__file__).resolve().parent / "golden" / "chat_cases.yaml"


def load_cases() -> list[GoldenCase]:
    data = yaml.safe_load(GOLDEN_CHAT.read_text())
    return [GoldenCase.model_validate(c) for c in data]


def _deterministic_checks(case: GoldenCase, answer: str) -> list[str]:
    failures = []
    for needle in case.rubric.must_mention:
        if not re.search(re.escape(needle), answer, re.IGNORECASE):
            failures.append(f"missing required mention '{needle}'")
    for needle in case.rubric.must_not_mention:
        if re.search(rf"\b{re.escape(needle)}\b", answer, re.IGNORECASE):
            failures.append(f"forbidden mention '{needle}'")
    return failures


async def run_case(
    case: GoldenCase,
    *,
    client: AsyncAnthropic,
    judge_model: str,
    cost: CostTracker,
    settings,
) -> CaseResult:
    if cost.exhausted:
        return CaseResult(case_id=case.id, error="skipped_budget")
    misses: list[str] = []
    dispatch = build_fake_dispatch(case.tool_fixtures, misses)
    repo = FakeRepo()
    ctx = ToolContext(settings=settings, repo=repo)
    budget = Budget(
        max_iterations=settings.chat_max_iterations,
        max_cost_usd=case.max_cost_usd,
        model=settings.model,
    )
    system_prompt = compose_chat_system_prompt(
        CHAT_SYSTEM_PROMPT, json.dumps(case.context, default=str)
    )
    try:
        result = await run_agent(
            case.question,
            trigger="eval",
            system_prompt=system_prompt,
            tools=CHAT_TOOLS,  # never WEB_SEARCH_TOOL: unfakeable + nondeterministic
            budget=budget,
            db=repo,
            client=client,
            ctx=ctx,
            dispatch=dispatch,
        )
    except Exception as exc:  # noqa: BLE001 - one dead case shouldn't kill the run
        return CaseResult(case_id=case.id, error=f"run failed: {exc!r}")
    cost.record_flat(result.cost_usd)

    tools_used = [t["tool_name"] for t in result.tool_summaries]
    out = CaseResult(
        case_id=case.id,
        answer=result.answer,
        status=result.status,
        tools_used=tools_used,
        fixture_misses=misses,
        deterministic_failures=_deterministic_checks(case, result.answer),
        expected_tools_missing=[
            t for t in case.expected_tools if t not in tools_used
        ],
        cost_usd=result.cost_usd,
    )
    if case.rubric.criteria and not cost.exhausted:
        out.verdict = await run_judge(client, judge_model, case, result.answer, cost)
    return out


async def run_chat_suite(
    cases: list[GoldenCase], *, client, judge_model, cost, settings, parallel: int
) -> list[CaseResult]:
    sem = asyncio.Semaphore(parallel)

    async def guarded(case: GoldenCase) -> CaseResult:
        async with sem:
            r = await run_case(
                case, client=client, judge_model=judge_model, cost=cost, settings=settings
            )
            mark = "PASS" if r.passed else ("SKIP" if r.error == "skipped_budget" else "FAIL")
            print(f"  [{mark}] {case.id} (${r.cost_usd:.3f})")
            return r

    return list(await asyncio.gather(*[guarded(c) for c in cases]))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["chat", "classifier", "all"], default="all")
    parser.add_argument("--case", default=None, help="run a single chat case id")
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--max-cost", type=float, default=5.00)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return EXIT_INFRA
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    judge_model = args.judge_model or settings.eval_judge_model
    cost = CostTracker(args.max_cost)

    chat_results: list[CaseResult] = []
    classifier: dict | None = None

    if args.suite in ("chat", "all"):
        cases = load_cases()
        if args.case:
            cases = [c for c in cases if c.id == args.case]
            if not cases:
                print(f"no case with id '{args.case}'", file=sys.stderr)
                return EXIT_INFRA
        print(f"chat suite: {len(cases)} cases (model {settings.model}, judge {judge_model})")
        chat_results = await run_chat_suite(
            cases, client=client, judge_model=judge_model,
            cost=cost, settings=settings, parallel=args.parallel,
        )

    if args.suite in ("classifier", "all"):
        print(f"classifier suite (model {settings.classifier_model})")
        classifier = await run_classifier_eval(client, settings.classifier_model, cost)
        print(f"  accuracy {classifier['accuracy']:.2%} on {classifier['total']} headlines")

    # ---- regression gate --------------------------------------------------
    baseline = load_baseline("chat")
    regressed = regressions(chat_results, baseline)
    if regressed and not args.case:
        # Confirm at N=3: a flip must fail 2/3 to count (nondeterminism guard).
        print(f"possible regressions: {regressed} — confirming at N=3")
        confirmed = []
        by_id = {c.id: c for c in load_cases()}
        for case_id in regressed:
            fails = 1  # the original failure counts as run 1 of 3
            for _ in range(2):
                rerun = await run_case(
                    by_id[case_id], client=client, judge_model=judge_model,
                    cost=cost, settings=settings,
                )
                if not rerun.passed:
                    fails += 1
            if fails >= 2:
                confirmed.append(case_id)
            else:
                print(f"  {case_id}: flaky (1/3), not a regression")
        regressed = confirmed

    report_path = write_reports(
        prompt_version=PROMPT_VERSION,
        judge_prompt_version=JUDGE_PROMPT_VERSION,
        model=settings.model,
        judge_model=judge_model,
        chat_results=chat_results,
        classifier=classifier,
        total_cost_usd=cost.cost_usd,
        baseline=baseline,
        regressed=regressed,
    )
    print(f"report: {report_path}  (total ${cost.cost_usd:.3f})")

    if args.update_baseline and chat_results and not args.case:
        save_baseline(
            "chat",
            {
                "prompt_version": PROMPT_VERSION,
                "cases": {r.case_id: r.passed for r in chat_results},
            },
        )
        print("baseline updated")

    infra = any(r.error == "skipped_budget" for r in chat_results) or (
        chat_results
        and sum(1 for r in chat_results if r.verdict and r.verdict.judge_error)
        > len(chat_results) / 2
    )
    if infra:
        return EXIT_INFRA
    if regressed or (classifier and not classifier["passed"]):
        return EXIT_REGRESSION
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
