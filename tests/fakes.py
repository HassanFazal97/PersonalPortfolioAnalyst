"""Shared test doubles: an in-memory Repo and a scripted Anthropic client.

The FakeRepo records the same rows the real Repo would write, so the loop's
observability behavior is asserted without a live Postgres. When a DATABASE_URL
is available, the same assertions can be re-run against the real Repo.
"""

from __future__ import annotations

import uuid
from typing import Any


class FakeRepo:
    def __init__(self) -> None:
        self.runs: dict[uuid.UUID, dict[str, Any]] = {}
        self.model_calls: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []

    async def create_run(self, *, trigger, user_message, model, prompt_version):
        run_id = uuid.uuid4()
        self.runs[run_id] = {
            "trigger": trigger,
            "user_message": user_message,
            "model": model,
            "prompt_version": prompt_version,
            "status": "running",
        }
        return run_id

    async def finalize_run(self, run_id, **kwargs):
        self.runs[run_id].update(kwargs)

    async def log_model_call(self, *, run_id, iteration, request, response, usage):
        self.model_calls.append(
            {"run_id": run_id, "iteration": iteration, "request": request,
             "response": response, "usage": usage}
        )

    async def log_tool_call(self, *, run_id, iteration, tool_name, input, output,
                            is_error, latency_ms):
        self.tool_calls.append(
            {"run_id": run_id, "iteration": iteration, "tool_name": tool_name,
             "input": input, "output": output, "is_error": is_error,
             "latency_ms": latency_ms}
        )

    async def list_positions(self):
        return []


class ScriptedAnthropic:
    """Returns pre-canned responses from ``messages.create`` in sequence."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    @property
    def messages(self):
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def tool_use_turn(tool_id, name, tool_input, *, in_tok=100, out_tok=20):
    return {
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}],
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }


def text_turn(text, *, in_tok=100, out_tok=20):
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }
