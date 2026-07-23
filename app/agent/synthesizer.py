"""Digest Stage 3 — Synthesize + send.

A focused loop that exposes only ``send_digest``. The model must deliver the
digest by calling it; an over-long body comes back as an is_error tool_result
(the length-enforcement mechanism) and the model shortens and retries. All
calls are logged under the anchor digest run. Returns the delivered body.
"""

from __future__ import annotations

from typing import Any

from app.agent.loop import call_and_log, safe_dispatch
from app.agent.prompts import SYNTHESIZE_HOLDINGS_SUFFIX, SYNTHESIZE_SYSTEM_PROMPT
from app.observability.logging import Observer
from app.tools.digest import SEND_DIGEST_SCHEMA
from app.tools.registry import DIGEST_TOOLS, ToolContext


class DigestNotSent(Exception):
    """Raised when the synthesize stage ends without delivering a digest."""


_SCHEMAS = {"send_digest": SEND_DIGEST_SCHEMA}
_NUDGE = "You must deliver the digest now by calling send_digest."
# A Pro digest sends the short body plus a per-holding breakdown (up to
# DIGEST_HOLDINGS_MAX_CHARS) in one send_digest call; 1024 output tokens
# truncates that mid tool_use, so give the synthesize call real headroom.
_SYNTHESIZE_MAX_TOKENS = 4096


async def synthesize_and_send(
    *,
    client: Any,
    model: str,
    observer: Observer,
    budget: Any,
    ctx: ToolContext,
    findings_text: str,
    iteration_start: int,
    holdings_scaffold: str | None = None,
) -> str:
    settings = ctx.settings
    system_prompt = SYNTHESIZE_SYSTEM_PROMPT
    user_content = findings_text
    if holdings_scaffold:
        system_prompt += SYNTHESIZE_HOLDINGS_SUFFIX
        user_content = f"{findings_text}\n\n{holdings_scaffold}"
    messages = [{"role": "user", "content": user_content}]
    iteration = iteration_start

    while not budget.exceeded():
        iteration += 1
        content, stop_reason = await call_and_log(
            client,
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            tools=DIGEST_TOOLS,
            observer=observer,
            iteration=iteration,
            budget=budget,
            max_tokens=_SYNTHESIZE_MAX_TOKENS,
        )
        messages.append({"role": "assistant", "content": content})

        # Branch on whether the turn actually contains tool_use blocks, not on
        # stop_reason: a tool_use truncated by max_tokens reports "max_tokens"
        # but still MUST be answered with tool_results, or the next request is
        # a malformed (tool_use without tool_result) sequence.
        tool_use_blocks = [b for b in content if b.get("type") == "tool_use"]
        if not tool_use_blocks:
            messages.append({"role": "user", "content": _NUDGE})
            continue

        tool_results: list[dict[str, Any]] = []
        sent_body: str | None = None
        for block in tool_use_blocks:
            payload = block.get("input", {}) or {}
            result_str, error = await safe_dispatch(
                block["name"],
                payload,
                ctx=ctx,
                schemas_by_name=_SCHEMAS,
                timeout=settings.tool_timeout_seconds,
                max_output_tokens=settings.max_tool_output_tokens,
            )
            await observer.tool_call(
                iteration=iteration,
                tool_name=block["name"],
                input=payload,
                output=result_str,
                is_error=error is not None,
                latency_ms=0,
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result_str,
                    "is_error": error is not None,
                }
            )
            if error is None and block["name"] == "send_digest":
                sent_body = payload.get("body")

        if sent_body is not None:
            return sent_body

        messages.append({"role": "user", "content": tool_results})

    raise DigestNotSent("synthesize stage exhausted its budget without sending")
