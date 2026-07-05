"""Macro specialists — one per domain (geopolitical, monetary, energy,
regulatory/climate). Each scans its area with Anthropic's server-side web search
and returns material events as strict JSON. They do not see the portfolio;
mapping events to holdings happens in the orchestrator's synthesis stage.

Web search is a *server* tool: the API runs the search loop and returns the
results inline. Our only job is to handle ``stop_reason == "pause_turn"`` by
re-sending the accumulated turn (never adding a "continue" message), bounded by
a continuation cap. Each model call is logged through the Observer and counted
against the run budget.
"""

from __future__ import annotations

import json
from typing import Any

from app.agent.prompts import MACRO_SPECIALIST_OUTPUT, MACRO_SPECIALIST_PROMPTS
from app.observability.logging import Observer

# Dynamic-filtering web search; supported on the configured macro model
# (Sonnet 4.6 / Opus 4.6+). Older models would need web_search_20250305.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}

CATEGORIES: list[str] = list(MACRO_SPECIALIST_PROMPTS)

_MAX_CONTINUATIONS = 4
_MAX_TOKENS = 2048


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _text_of(content: Any) -> str:
    parts = []
    for block in content or []:
        if _get(block, "type") == "text":
            parts.append(_get(block, "text", "") or "")
    return "\n".join(parts).strip()


def _usage_of(response: Any) -> dict[str, int]:
    u = _get(response, "usage", {}) or {}
    return {
        "input_tokens": int(_get(u, "input_tokens", 0) or 0),
        "output_tokens": int(_get(u, "output_tokens", 0) or 0),
    }


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def parse_events(text: str, category: str) -> list[dict[str, Any]]:
    """Parse specialist output into a clean, tagged event list (never raises)."""
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return []
    rows = data.get("events") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows[:4]:
        if not isinstance(row, dict) or not row.get("title"):
            continue
        severity = row.get("severity")
        out.append(
            {
                "category": category,
                "title": str(row["title"]),
                "summary": str(row.get("summary", "")),
                "themes": [str(t) for t in row.get("themes", []) if isinstance(t, str)],
                "severity": severity if severity in ("low", "medium", "high") else "medium",
            }
        )
    return out


async def run_specialist(
    *,
    client: Any,
    model: str,
    observer: Observer,
    budget: Any,
    category: str,
    today: str,
    iteration_base: int,
) -> list[dict[str, Any]]:
    """Run one specialist end-to-end and return its material events."""
    system = f"{MACRO_SPECIALIST_PROMPTS[category]}\n\n{MACRO_SPECIALIST_OUTPUT}"
    kickoff = (
        f"Today is {today}. Search for material developments in your domain from "
        "roughly the last 24 hours and report them in the required JSON format."
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": kickoff}]

    response: Any = None
    for i in range(_MAX_CONTINUATIONS + 1):
        response = await client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=messages,
            tools=[WEB_SEARCH_TOOL],
        )
        usage = _usage_of(response)
        if budget is not None:
            budget.record_usage(usage["input_tokens"], usage["output_tokens"])
        await observer.model_call(
            iteration=iteration_base + i,
            request={"model": model, "system": system, "category": category,
                     "tools": ["web_search"]},
            response={"stop_reason": _get(response, "stop_reason"),
                      "text": _text_of(_get(response, "content"))},
            usage=usage,
        )
        if _get(response, "stop_reason") == "pause_turn":
            # Re-send the accumulated turn verbatim so the server resumes its
            # search loop; do NOT append a "continue" message.
            messages.append({"role": "assistant", "content": _get(response, "content")})
            continue
        break

    return parse_events(_text_of(_get(response, "content")), category)
