"""LLM-as-judge: rubric-anchored absolute scoring of one answer at a time.

Deliberately NOT in app/agent/prompts.py — judge-prompt changes must never
masquerade as product-prompt changes, so the judge carries its own version.
The judge sees the case's fixture data as ground truth and is instructed to
judge against it only, never its own market knowledge; hallucination detection
(claims unsupported by the fixtures) is its highest-value job.
"""

from __future__ import annotations

import json
from typing import Any

from evals.schema import GoldenCase, Verdict

JUDGE_PROMPT_VERSION = "2026-07-22.2"

JUDGE_SYSTEM_PROMPT = """\
You are a strict evaluation judge for a portfolio-analyst assistant. You are
given: the user's question, the GROUND TRUTH tool data the assistant had
access to, the assistant's answer, and a list of binary criteria.

Judge ONLY against the supplied ground truth — never your own market
knowledge (the data is synthetic; real-world figures are irrelevant). A
criterion is false unless the answer clearly satisfies it.

A hallucination is a SPECIFIC factual claim about the user's portfolio or its
market data — a price, return, ratio, position, or event — that the ground
truth does not support, or a figure presented as fetched that was never
fetched. These are NOT hallucinations:
- general financial rules-of-thumb or benchmark context clearly framed as
  interpretation (e.g. "a PEG under 1 is generally considered cheap");
- the assistant describing its own tools, their limits, or what it could not
  determine;
- restating what a tool's empty/normal result means (e.g. explaining the
  detector types behind a clean anomaly scan).

Respond with STRICT JSON and nothing else — no prose, no code fences:
{"criteria": [{"id": "...", "pass": true, "reasoning": "<=2 sentences citing evidence"}],
 "hallucinations": ["<each unsupported factual claim, verbatim-ish>"],
 "overall_pass": true}
"overall_pass" is true only when every criterion passes AND hallucinations is
empty. Include every criterion id you were given, exactly once."""


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _judge_user_message(case: GoldenCase, answer: str) -> str:
    return "\n\n".join(
        [
            f"QUESTION:\n{case.question}",
            "GROUND TRUTH (context + tool fixtures):\n"
            + json.dumps({"context": case.context, "tools": case.tool_fixtures}, default=str),
            f"ASSISTANT ANSWER:\n{answer}",
            "CRITERIA:\n" + json.dumps(case.rubric.criteria),
        ]
    )


def parse_verdict(text: str, expected_ids: list[str]) -> Verdict | None:
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("criteria"), list):
        return None
    criteria = [
        {"id": str(c.get("id")), "pass": bool(c.get("pass")), "reasoning": str(c.get("reasoning", ""))}
        for c in data["criteria"]
        if isinstance(c, dict)
    ]
    got_ids = {c["id"] for c in criteria}
    if expected_ids and not set(expected_ids) <= got_ids:
        return None  # judge dropped a criterion — retry
    hallucinations = [str(h) for h in data.get("hallucinations") or []]
    overall = (
        bool(data.get("overall_pass"))
        and all(c["pass"] for c in criteria)
        and not hallucinations
    )
    return Verdict(
        criteria=criteria,
        hallucinations=hallucinations,
        overall_pass=overall,
        raw=text,
    )


async def run_judge(
    client: Any, model: str, case: GoldenCase, answer: str, cost_tracker
) -> Verdict:
    """One judge call (+1 retry on parse failure). Never raises: an unusable
    judge yields Verdict(judge_error=True), which the report separates from
    both pass and regression."""
    expected_ids = [c["id"] for c in case.rubric.criteria]
    messages = [{"role": "user", "content": _judge_user_message(case, answer)}]
    for _attempt in range(2):
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=1500,
                system=JUDGE_SYSTEM_PROMPT,
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001 - infra failure -> judge_error
            return Verdict(judge_error=True, raw=f"judge call failed: {exc!r}")
        usage = getattr(response, "usage", None) or {}
        cost_tracker.record(
            model,
            int(getattr(usage, "input_tokens", 0) or (usage.get("input_tokens", 0) if isinstance(usage, dict) else 0)),
            int(getattr(usage, "output_tokens", 0) or (usage.get("output_tokens", 0) if isinstance(usage, dict) else 0)),
        )
        content = getattr(response, "content", None) or []
        text = "\n".join(
            getattr(b, "text", b.get("text", "") if isinstance(b, dict) else "")
            for b in content
        )
        verdict = parse_verdict(text, expected_ids)
        if verdict is not None:
            return verdict
        messages.append({"role": "assistant", "content": text})
        messages.append(
            {"role": "user", "content": "That was not valid JSON of the required shape. Respond with ONLY the JSON object."}
        )
    return Verdict(judge_error=True, raw=text)
