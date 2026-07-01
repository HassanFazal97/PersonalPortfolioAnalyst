"""Observability writers: persist every model call and tool call.

The loop hands raw (already JSON-safe) request/response/usage dicts here; this
module is the single place that writes them to Postgres via ``Repo`` so a run
is fully reconstructable from the DB alone. ``Observer`` binds a run_id so call
sites don't repeat it.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.db.repo import Repo


class Observer:
    def __init__(self, repo: Repo, run_id: uuid.UUID) -> None:
        self._repo = repo
        self._run_id = run_id

    async def model_call(
        self,
        *,
        iteration: int,
        request: dict[str, Any],
        response: dict[str, Any],
        usage: dict[str, Any],
    ) -> None:
        await self._repo.log_model_call(
            run_id=self._run_id,
            iteration=iteration,
            request=request,
            response=response,
            usage=usage,
        )

    async def tool_call(
        self,
        *,
        iteration: int,
        tool_name: str,
        input: dict[str, Any],
        output: Any,
        is_error: bool,
        latency_ms: int,
    ) -> None:
        await self._repo.log_tool_call(
            run_id=self._run_id,
            iteration=iteration,
            tool_name=tool_name,
            input=input,
            output={"result": output} if not isinstance(output, dict) else output,
            is_error=is_error,
            latency_ms=latency_ms,
        )
