"""Shared test doubles: an in-memory Repo and a scripted Anthropic client.

The FakeRepo records the same rows the real Repo would write, so the loop's
observability behavior is asserted without a live Postgres. When a DATABASE_URL
is available, the same assertions can be re-run against the real Repo.
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from typing import Any


class FakeRepo:
    def __init__(self, positions: list[Any] | None = None) -> None:
        self.runs: dict[uuid.UUID, dict[str, Any]] = {}
        self.model_calls: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.digests: dict[date, SimpleNamespace] = {}
        self.outbound: list[str] = []
        self._outbox: dict[uuid.UUID, SimpleNamespace] = {}
        self._positions = positions or []

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

    async def upsert_position(self, *, ticker, quantity, avg_cost, currency, account):
        from decimal import Decimal

        key = (ticker, account)
        if not hasattr(self, "_position_rows"):
            self._position_rows: dict[tuple[str, str], Any] = {}
        self._position_rows[key] = SimpleNamespace(
            ticker=ticker,
            quantity=Decimal(str(quantity)),
            avg_cost=Decimal(str(avg_cost)),
            currency=currency,
            account=account,
        )

    async def prune_positions_except(self, keep: set[tuple[str, str]]) -> int:
        if not hasattr(self, "_position_rows"):
            self._position_rows = {}
        stale = [k for k in self._position_rows if k not in keep]
        for k in stale:
            del self._position_rows[k]
        return len(stale)

    async def list_positions(self):
        if hasattr(self, "_position_rows"):
            return list(self._position_rows.values())
        return self._positions

    async def upsert_digest(self, *, run_id, body, digest_date):
        self.digests[digest_date] = SimpleNamespace(
            run_id=run_id, body=body, digest_date=digest_date, created_at=None
        )

    async def get_digest(self, digest_date):
        return self.digests.get(digest_date)

    async def enqueue_outbound(self, body):
        msg_id = uuid.uuid4()
        self.outbound.append(body)
        self._outbox[msg_id] = SimpleNamespace(
            id=msg_id, body=body, status="queued", attempts=0
        )
        return msg_id

    async def pending_outbound(self, limit=20):
        return [m for m in self._outbox.values() if m.status == "queued"][:limit]

    async def ack_outbound(self, msg_id, *, status, max_attempts=3):
        from app.db.repo import resolve_ack_status

        msg = self._outbox.get(msg_id)
        if msg is None:
            return None
        msg.attempts += 1
        msg.status = resolve_ack_status(status, msg.attempts, max_attempts)
        return msg.status


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
