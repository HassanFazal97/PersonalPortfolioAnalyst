"""Digest Stage 1 — Plan. One model call (no tools) that decides what to
investigate this morning, returned as strict JSON.

Parsing is defensive: strip code fences, retry once with a corrective message,
then fall back to a single generic investigation so the pipeline never stalls.
"""

from __future__ import annotations

import json
from typing import Any

from app.agent.loop import call_and_log
from app.agent.prompts import PLAN_RETRY_SUFFIX, PLAN_SYSTEM_PROMPT
from app.observability.logging import Observer

FALLBACK_INVESTIGATION = {
    "question": "What notable news affected any of the user's holdings in the last 24 hours?",
    "why": "Planner could not produce a structured plan; scan all holdings for news.",
}


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # drop first fence line and any trailing fence
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def parse_plan(text: str) -> list[dict[str, str]] | None:
    """Parse planner output into 2–4 investigations, or None if unparseable."""
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return None
    investigations = data.get("investigations") if isinstance(data, dict) else None
    if not isinstance(investigations, list) or not investigations:
        return None
    cleaned: list[dict[str, str]] = []
    for item in investigations:
        if isinstance(item, dict) and item.get("question"):
            cleaned.append(
                {"question": str(item["question"]), "why": str(item.get("why", ""))}
            )
    if not cleaned:
        return None
    return cleaned[:4]


async def plan(
    *,
    client: Any,
    model: str,
    observer: Observer,
    budget: Any,
    market_context: str,
) -> list[dict[str, str]]:
    messages = [{"role": "user", "content": market_context}]
    content, _ = await call_and_log(
        client,
        model=model,
        system_prompt=PLAN_SYSTEM_PROMPT,
        messages=messages,
        tools=None,
        observer=observer,
        iteration=1,
        budget=budget,
    )
    text = _join_text(content)
    investigations = parse_plan(text)
    if investigations is not None:
        return investigations

    # Retry once with a corrective message.
    messages.append({"role": "assistant", "content": content})
    messages.append({"role": "user", "content": PLAN_RETRY_SUFFIX})
    content, _ = await call_and_log(
        client,
        model=model,
        system_prompt=PLAN_SYSTEM_PROMPT,
        messages=messages,
        tools=None,
        observer=observer,
        iteration=2,
        budget=budget,
    )
    investigations = parse_plan(_join_text(content))
    if investigations is not None:
        return investigations

    return [FALLBACK_INVESTIGATION]


def _join_text(content: list[dict[str, Any]]) -> str:
    return "\n".join(
        b.get("text", "") for b in content if b.get("type") == "text"
    ).strip()
