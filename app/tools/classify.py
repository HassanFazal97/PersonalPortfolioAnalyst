"""News signal classification — tag each item risk / opportunity / neutral.

One cheap, batched Haiku call labels a set of headlines. This is *informational*
salience labeling, never a buy/sell instruction (the agent informs, it does not
advise). Per-headline results are cached so a headline seen by several digest
investigations is classified once. When a run context is present the model call
is logged through the observability layer, so its cost lands in
``agent_runs.cost_usd`` / ``model_calls`` and the run stays replayable.
"""

from __future__ import annotations

import json
from typing import Any

from app.agent.prompts import CLASSIFY_SYSTEM_PROMPT
from app.config import get_settings
from app.observability.logging import Observer

_VALID_SIGNALS = frozenset({"warning", "opportunity", "neutral"})
_SUMMARY_MAX_CHARS = 300
_RATIONALE_MAX_CHARS = 200

# canonical headline -> {"signal", "salience", "rationale"}
_signal_cache: dict[str, dict[str, Any]] = {}


def cache_clear() -> None:
    """Test/utility helper to reset the classification cache."""
    _signal_cache.clear()


def _canonical(headline: str) -> str:
    return " ".join(headline.lower().split())


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _coerce(entry: Any) -> dict[str, Any]:
    """Normalize one model label into a safe {signal, salience, rationale}."""
    signal = entry.get("signal") if isinstance(entry, dict) else None
    if signal not in _VALID_SIGNALS:
        signal = "neutral"
    try:
        salience = float(entry.get("salience")) if isinstance(entry, dict) else 0.0
    except (TypeError, ValueError):
        salience = 0.0
    salience = max(0.0, min(1.0, salience))
    rationale = ""
    if isinstance(entry, dict):
        rationale = str(entry.get("rationale", ""))[:_RATIONALE_MAX_CHARS]
    return {"signal": signal, "salience": round(salience, 2), "rationale": rationale}


def _prompt_payload(items: list[dict[str, Any]]) -> str:
    lines = []
    for i, it in enumerate(items):
        lines.append(
            json.dumps(
                {
                    "i": i,
                    "headline": it.get("headline", ""),
                    "summary": (it.get("summary") or "")[:_SUMMARY_MAX_CHARS],
                }
            )
        )
    return "\n".join(lines)


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


def _response_text(response: Any) -> str:
    parts = []
    for block in _get(response, "content", []) or []:
        if _get(block, "type") == "text":
            parts.append(_get(block, "text", "") or "")
    return "\n".join(parts).strip()


def _parse_labels(text: str, n: int) -> list[dict[str, Any]]:
    """Parse model output into ``n`` labels, index-aligned, neutral on gaps."""
    labels: list[dict[str, Any]] = [_coerce(None) for _ in range(n)]
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return labels
    rows = data.get("labels") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return labels
    for row in rows:
        if not isinstance(row, dict):
            continue
        idx = row.get("i")
        if isinstance(idx, int) and 0 <= idx < n:
            labels[idx] = _coerce(row)
    return labels


async def _classify_batch(
    client: Any, model: str, items: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """One Haiku call. Returns (labels, usage, log) for the given items."""
    messages = [{"role": "user", "content": _prompt_payload(items)}]
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=CLASSIFY_SYSTEM_PROMPT,
        messages=messages,
    )
    text = _response_text(response)
    labels = _parse_labels(text, len(items))
    usage_obj = _get(response, "usage", {}) or {}
    usage = {
        "input_tokens": int(_get(usage_obj, "input_tokens", 0) or 0),
        "output_tokens": int(_get(usage_obj, "output_tokens", 0) or 0),
    }
    log = {
        "request": {"model": model, "system": CLASSIFY_SYSTEM_PROMPT, "messages": messages},
        "response": {"labels": labels},
    }
    return labels, usage, log


async def _record(ctx: Any, usage: dict[str, Any], log: dict[str, Any]) -> None:
    """Best-effort: count the classify call against the run's budget + logs."""
    budget = getattr(ctx, "budget", None)
    if budget is not None:
        try:
            budget.record_usage(usage["input_tokens"], usage["output_tokens"])
        except Exception:  # noqa: BLE001 - accounting must never break a tool
            pass
    repo = getattr(ctx, "repo", None)
    run_id = getattr(ctx, "run_id", None)
    if repo is not None and run_id is not None:
        observer = Observer(repo, run_id)
        iteration = getattr(budget, "iterations", 0) or 0
        await observer.model_call(
            iteration=iteration,
            request=log["request"],
            response=log["response"],
            usage=usage,
        )


async def classify_news(
    items: list[dict[str, Any]], ctx: Any = None
) -> list[dict[str, Any]]:
    """Attach {signal, salience, rationale} to each item.

    No-op (items returned unchanged) when there is no client to call — e.g. unit
    tests or the digest prefetch. Failures degrade to leaving items untagged
    rather than breaking the search_news tool.
    """
    if not items:
        return items

    client = getattr(ctx, "client", None) if ctx is not None else None

    if client is not None:
        pending = [
            it
            for it in items
            if (key := _canonical(it.get("headline") or "")) and key not in _signal_cache
        ]
        if pending:
            try:
                labels, usage, log = await _classify_batch(
                    client, get_settings().classifier_model, pending
                )
            except Exception:  # noqa: BLE001 - degrade to untagged
                labels = None
            if labels is not None:
                for it, label in zip(pending, labels):
                    _signal_cache[_canonical(it.get("headline") or "")] = label
                await _record(ctx, usage, log)

    out: list[dict[str, Any]] = []
    for it in items:
        label = _signal_cache.get(_canonical(it.get("headline") or ""))
        enriched = dict(it)
        if label:
            enriched.update(label)
        out.append(enriched)
    return out
