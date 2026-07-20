"""The hand-written agent loop — single entrypoint ``run_agent``.

No agent framework: the loop, tool dispatch, budgeting, and message assembly
are explicit here. Design principles enforced:
- tool errors flow into the conversation as ``is_error`` tool_results;
- only infrastructure failures abort a run;
- every model call and tool call is persisted via ``Observer``;
- runs stop gracefully at their budget with a final tools-off summary turn.
"""

from __future__ import annotations

import asyncio
import copy
import json
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.agent.budget import Budget
from app.agent.prompts import BUDGET_SUMMARY_PROMPT, PROMPT_VERSION
from app.auth.context import set_current_user_id
from app.config import get_settings
from app.db.repo import Repo
from app.observability.logging import Observer
from app.tools.registry import DISPATCH, TOOL_TIMEOUTS, ToolContext

_CHARS_PER_TOKEN = 4  # rough; used to convert the token cap to a char cap


@dataclass
class AgentResult:
    run_id: uuid.UUID
    answer: str
    status: str
    iterations: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    tool_summaries: list[dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------
# Anthropic response <-> plain-dict helpers (mock-friendly, JSON-safe)
# --------------------------------------------------------------------------


def _attr(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _block_to_dict(block: Any) -> dict[str, Any]:
    btype = _attr(block, "type")
    if btype == "text":
        return {"type": "text", "text": _attr(block, "text", "")}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": _attr(block, "id"),
            "name": _attr(block, "name"),
            "input": _attr(block, "input", {}) or {},
        }
    # Server-side tool blocks (server_tool_use, web_search_tool_result, …)
    # must replay VERBATIM on the next iteration — a lossy dict breaks the
    # API's block validation. SDK objects expose model_dump(); scripted test
    # doubles are already dicts.
    if isinstance(block, dict):
        return dict(block)
    dump = getattr(block, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    # Truly unknown object: best-effort stringification (last resort).
    return {"type": btype, "raw": str(block)}


def _content_to_dicts(content: Any) -> list[dict[str, Any]]:
    return [_block_to_dict(b) for b in (content or [])]


def _extract_text(content_dicts: list[dict[str, Any]]) -> str:
    return "\n".join(
        b["text"] for b in content_dicts if b.get("type") == "text" and b.get("text")
    ).strip()


# --------------------------------------------------------------------------
# safe_dispatch and its pieces
# --------------------------------------------------------------------------

_JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _validate_input(schema: dict[str, Any], payload: Any) -> str | None:
    """Lightweight schema validation. Returns an error message or None."""
    if not isinstance(payload, dict):
        return "tool input must be a JSON object"
    props = schema.get("properties", {})
    for req in schema.get("required", []):
        if req not in payload:
            return f"missing required field '{req}'"
    for key, val in payload.items():
        spec = props.get(key)
        if not spec or "type" not in spec:
            continue
        expected = _JSON_TYPES.get(spec["type"])
        # bool is a subclass of int; reject it where a number/integer is wanted
        if spec["type"] in ("integer", "number") and isinstance(val, bool):
            return f"field '{key}' must be a {spec['type']}"
        if expected and not isinstance(val, expected):
            return f"field '{key}' must be a {spec['type']}"
    return None


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    kept = text[:max_chars]
    return f"{kept}\n[truncated {len(text) - max_chars} chars]"


_RETRYABLE = (asyncio.TimeoutError, ConnectionError)


async def safe_dispatch(
    name: str,
    payload: dict[str, Any],
    *,
    ctx: ToolContext,
    schemas_by_name: dict[str, dict[str, Any]],
    timeout: float,
    max_output_tokens: int,
) -> tuple[str, str | None]:
    """Execute one tool safely. Returns (result_string, error_message | None).

    Order: schema validation -> timeout -> one retry (timeout/connection only)
    -> truncate -> JSON-serialize. Errors become a returned message, never a
    raised exception (they flow into the conversation as is_error tool_results).
    """
    fn = DISPATCH.get(name)
    if fn is None:
        msg = f"unknown tool '{name}'"
        return msg, msg

    schema = schemas_by_name.get(name)
    if schema is not None:
        err = _validate_input(schema.get("input_schema", {}), payload)
        if err:
            return err, err

    max_chars = max_output_tokens * _CHARS_PER_TOKEN
    attempts = 0
    while True:
        attempts += 1
        try:
            result = await asyncio.wait_for(fn(payload, ctx), timeout=timeout)
            break
        except _RETRYABLE as exc:
            if attempts <= 1:
                await asyncio.sleep(1.0)
                continue
            msg = f"tool '{name}' failed after retry: {exc!r}"
            return msg, msg
        except ValueError as exc:
            msg = f"invalid input for '{name}': {exc}"
            return msg, msg
        except Exception as exc:  # noqa: BLE001 - surfaced to the model
            msg = f"tool '{name}' error: {exc}"
            return msg, msg

    result_str = result if isinstance(result, str) else json.dumps(result, default=str)
    return _truncate(result_str, max_chars), None


# --------------------------------------------------------------------------
# Message assembly (factored seam for a future memory-prepend step)
# --------------------------------------------------------------------------


def build_initial_messages(
    user_message: str, history: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """The new user message, optionally preceded by prior conversation turns
    (plain ``{"role", "content"}`` text pairs — no tool traces)."""
    return [*(history or []), {"role": "user", "content": user_message}]


async def call_and_log(
    client: Any,
    *,
    model: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    observer: Observer,
    iteration: int,
    budget: Budget,
) -> tuple[list[dict[str, Any]], str | None]:
    """One model call: record usage into ``budget`` and persist it.

    Shared by the digest planner/synthesizer stages so their calls are logged
    identically to the main loop. Returns (content_dicts, stop_reason).
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    response = await client.messages.create(**kwargs)

    content_dicts = _content_to_dicts(_attr(response, "content"))
    usage = {
        "input_tokens": _usage(response, "input_tokens"),
        "output_tokens": _usage(response, "output_tokens"),
    }
    budget.record_usage(usage["input_tokens"], usage["output_tokens"])
    await observer.model_call(
        iteration=iteration,
        request=_request_snapshot(model, system_prompt, messages, tools or []),
        response={"stop_reason": _attr(response, "stop_reason"), "content": content_dicts},
        usage=usage,
    )
    return content_dicts, _attr(response, "stop_reason")


# --------------------------------------------------------------------------
# run_agent
# --------------------------------------------------------------------------


def _get_client(client: Any) -> Any:
    if client is not None:
        return client
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=get_settings().anthropic_api_key)


async def run_agent(
    user_message: str,
    *,
    trigger: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    budget: Budget,
    db: Repo,
    client: Any = None,
    ctx: ToolContext | None = None,
    user_id: Any | None = None,
    history: list[dict[str, Any]] | None = None,
) -> AgentResult:
    settings = get_settings()
    client = _get_client(client)
    # Bind the current user so both RLS (via the DB GUC) and the WHERE-filters
    # scope to it. Safe to call again if the request already set it.
    if user_id is not None:
        set_current_user_id(user_id)
    if ctx is None:
        ctx = ToolContext(settings=settings, repo=db)
    ctx.user_id = user_id
    # Let tools that make their own model calls (news classification) log and
    # cost-account against this run.
    ctx.client = client
    ctx.budget = budget
    schemas_by_name = {t["name"]: t for t in tools}

    started = time.monotonic()
    run_id = await db.create_run(
        trigger=trigger,
        user_message=user_message,
        model=settings.model,
        prompt_version=PROMPT_VERSION,
        user_id=user_id,
    )
    ctx.run_id = run_id
    observer = Observer(db, run_id)

    messages = build_initial_messages(user_message, history)
    tool_summaries: list[dict[str, Any]] = []
    answer = ""
    status = "running"

    try:
        while True:
            budget.start_iteration()
            iteration = budget.iterations

            response = await _call_model(
                client, settings.model, system_prompt, messages, tools
            )
            content_dicts = _content_to_dicts(_attr(response, "content"))
            usage = {
                "input_tokens": _usage(response, "input_tokens"),
                "output_tokens": _usage(response, "output_tokens"),
            }
            budget.record_usage(usage["input_tokens"], usage["output_tokens"])
            await observer.model_call(
                iteration=iteration,
                request=_request_snapshot(settings.model, system_prompt, messages, tools),
                response={
                    "stop_reason": _attr(response, "stop_reason"),
                    "content": content_dicts,
                },
                usage=usage,
            )

            messages.append({"role": "assistant", "content": content_dicts})
            stop_reason = _attr(response, "stop_reason")

            if stop_reason == "pause_turn":
                # A server-side tool (web_search) paused mid-turn; re-send the
                # conversation so the server continues where it left off. The
                # iteration/budget caps still bound runaway continuations.
                continue

            if stop_reason != "tool_use":
                answer = _extract_text(content_dicts)
                status = "completed"
                break

            tool_uses = [b for b in content_dicts if b.get("type") == "tool_use"]
            tool_results = await _run_tools(
                tool_uses,
                ctx=ctx,
                schemas_by_name=schemas_by_name,
                settings=settings,
                observer=observer,
                iteration=iteration,
                summaries=tool_summaries,
            )

            if budget.exceeded():
                status = "budget_exceeded" if budget.cost_exceeded() else "max_iterations"
                # Final turn: return tool_results plus a tools-off summary ask.
                messages.append(
                    {
                        "role": "user",
                        "content": [*tool_results, {"type": "text", "text": BUDGET_SUMMARY_PROMPT}],
                    }
                )
                answer = await _summary_turn(
                    client, settings, system_prompt, messages, observer,
                    budget, status_iteration=budget.iterations + 1,
                )
                break

            messages.append({"role": "user", "content": tool_results})

        await db.finalize_run(
            run_id,
            status=status,
            final_answer=answer,
            iterations=budget.iterations,
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            cost_usd=budget.cost_usd,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception:
        await db.finalize_run(
            run_id,
            status="error",
            final_answer=answer or None,
            iterations=budget.iterations,
            input_tokens=budget.input_tokens,
            output_tokens=budget.output_tokens,
            cost_usd=budget.cost_usd,
            latency_ms=int((time.monotonic() - started) * 1000),
            error_detail=traceback.format_exc(),
        )
        raise

    return AgentResult(
        run_id=run_id,
        answer=answer,
        status=status,
        iterations=budget.iterations,
        input_tokens=budget.input_tokens,
        output_tokens=budget.output_tokens,
        cost_usd=round(budget.cost_usd, 6),
        latency_ms=int((time.monotonic() - started) * 1000),
        tool_summaries=tool_summaries,
    )


# --------------------------------------------------------------------------
# internal helpers
# --------------------------------------------------------------------------


async def _call_model(client, model, system_prompt, messages, tools):
    # Cache the static prefix (tool schemas + system prompt): the loop resends
    # the whole request every iteration, so cache reads (0.1x input price)
    # cover everything up to the breakpoint on later iterations.
    system = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    return await client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=messages,
        tools=tools,
    )


def _usage(response: Any, key: str) -> int:
    usage = _attr(response, "usage")
    return int(_attr(usage, key, 0) or 0)


def _request_snapshot(model, system_prompt, messages, tools) -> dict[str, Any]:
    return {
        "model": model,
        "system": system_prompt,
        "messages": copy.deepcopy(messages),
        "tools": [t["name"] for t in tools],
    }


async def _run_tools(
    tool_uses,
    *,
    ctx,
    schemas_by_name,
    settings,
    observer,
    iteration,
    summaries,
) -> list[dict[str, Any]]:
    tool_results: list[dict[str, Any]] = []
    for block in tool_uses:
        name = block["name"]
        payload = block.get("input", {}) or {}
        t0 = time.monotonic()
        result_str, error = await safe_dispatch(
            name,
            payload,
            ctx=ctx,
            schemas_by_name=schemas_by_name,
            timeout=TOOL_TIMEOUTS.get(name, settings.tool_timeout_seconds),
            max_output_tokens=settings.max_tool_output_tokens,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        is_error = error is not None
        await observer.tool_call(
            iteration=iteration,
            tool_name=name,
            input=payload,
            output=result_str,
            is_error=is_error,
            latency_ms=latency_ms,
        )
        summaries.append({"tool_name": name, "input": payload, "is_error": is_error})
        tool_results.append(
            {
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": result_str,
                "is_error": is_error,
            }
        )
    return tool_results


async def _summary_turn(
    client, settings, system_prompt, messages, observer, budget, *, status_iteration
) -> str:
    response = await client.messages.create(
        model=settings.model,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )
    content_dicts = _content_to_dicts(_attr(response, "content"))
    usage = {
        "input_tokens": _usage(response, "input_tokens"),
        "output_tokens": _usage(response, "output_tokens"),
    }
    budget.record_usage(usage["input_tokens"], usage["output_tokens"])
    await observer.model_call(
        iteration=status_iteration,
        request={"model": settings.model, "system": system_prompt, "messages": messages, "tools": []},
        response={"stop_reason": _attr(response, "stop_reason"), "content": content_dicts},
        usage=usage,
    )
    messages.append({"role": "assistant", "content": content_dicts})
    return _extract_text(content_dicts)
