"""All database access. No raw SQL or session handling lives outside this module.

``Repo`` wraps an async engine + sessionmaker and exposes typed reader/writer
functions. The agent loop, tools, and API routes depend only on this surface.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import (
    AgentRun,
    Digest,
    ModelCall,
    OutboundMessage,
    Position,
    ToolCall,
)


def resolve_ack_status(status: str, attempts: int, max_attempts: int) -> str:
    """Decide an outbound message's status after a worker ack.

    'sent' is terminal; 'failed' stays 'queued' for retry until attempts reach
    ``max_attempts``, then becomes 'failed'. ``attempts`` is the post-increment
    count (i.e. including this attempt).
    """
    if status == "sent":
        return "sent"
    if status == "failed":
        return "failed" if attempts >= max_attempts else "queued"
    return status


class Repo:
    def __init__(
        self, database_url: str, *, echo: bool = False, ssl: bool = False
    ) -> None:
        connect_args = {"ssl": "require"} if ssl else {}
        self._engine: AsyncEngine = create_async_engine(
            database_url, echo=echo, connect_args=connect_args
        )
        self._session: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def ping(self) -> bool:
        """Liveness check used by ``GET /health``."""
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    # ---- positions -------------------------------------------------------

    async def list_positions(self) -> list[Position]:
        async with self._session() as s:
            result = await s.execute(select(Position))
            return list(result.scalars().all())

    async def upsert_position(
        self,
        *,
        ticker: str,
        quantity: Decimal,
        avg_cost: Decimal,
        currency: str,
        account: str,
    ) -> None:
        """Insert or update a position keyed by (ticker, account)."""
        async with self._session() as s:
            existing = await s.execute(
                select(Position).where(
                    Position.ticker == ticker, Position.account == account
                )
            )
            row = existing.scalar_one_or_none()
            if row is None:
                s.add(
                    Position(
                        ticker=ticker,
                        quantity=quantity,
                        avg_cost=avg_cost,
                        currency=currency,
                        account=account,
                    )
                )
            else:
                row.quantity = quantity
                row.avg_cost = avg_cost
                row.currency = currency
                row.updated_at = datetime.now()
            await s.commit()

    # ---- agent runs & observability -------------------------------------

    async def create_run(
        self,
        *,
        trigger: str,
        user_message: str,
        model: str,
        prompt_version: str,
    ) -> uuid.UUID:
        async with self._session() as s:
            run = AgentRun(
                trigger=trigger,
                user_message=user_message,
                model=model,
                prompt_version=prompt_version,
                status="running",
            )
            s.add(run)
            await s.commit()
            return run.id

    async def finalize_run(
        self,
        run_id: uuid.UUID,
        *,
        status: str,
        final_answer: str | None,
        iterations: int,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        error_detail: str | None = None,
    ) -> None:
        async with self._session() as s:
            run = await s.get(AgentRun, run_id)
            if run is None:
                return
            run.status = status
            run.final_answer = final_answer
            run.iterations = iterations
            run.input_tokens = input_tokens
            run.output_tokens = output_tokens
            run.cost_usd = Decimal(str(cost_usd))
            run.latency_ms = latency_ms
            run.error_detail = error_detail
            await s.commit()

    async def log_model_call(
        self,
        *,
        run_id: uuid.UUID,
        iteration: int,
        request: dict[str, Any],
        response: dict[str, Any],
        usage: dict[str, Any],
    ) -> None:
        async with self._session() as s:
            s.add(
                ModelCall(
                    run_id=run_id,
                    iteration=iteration,
                    request=request,
                    response=response,
                    usage=usage,
                )
            )
            await s.commit()

    async def log_tool_call(
        self,
        *,
        run_id: uuid.UUID,
        iteration: int,
        tool_name: str,
        input: dict[str, Any],
        output: Any,
        is_error: bool,
        latency_ms: int,
    ) -> None:
        async with self._session() as s:
            s.add(
                ToolCall(
                    run_id=run_id,
                    iteration=iteration,
                    tool_name=tool_name,
                    input=input,
                    output=output,
                    is_error=is_error,
                    latency_ms=latency_ms,
                )
            )
            await s.commit()

    async def get_run(self, run_id: uuid.UUID) -> AgentRun | None:
        async with self._session() as s:
            return await s.get(AgentRun, run_id)

    async def get_run_trajectory(
        self, run_id: uuid.UUID
    ) -> tuple[AgentRun | None, list[ModelCall], list[ToolCall]]:
        async with self._session() as s:
            run = await s.get(AgentRun, run_id)
            model_calls = list(
                (
                    await s.execute(
                        select(ModelCall)
                        .where(ModelCall.run_id == run_id)
                        .order_by(ModelCall.iteration, ModelCall.created_at)
                    )
                )
                .scalars()
                .all()
            )
            tool_calls = list(
                (
                    await s.execute(
                        select(ToolCall)
                        .where(ToolCall.run_id == run_id)
                        .order_by(ToolCall.iteration, ToolCall.created_at)
                    )
                )
                .scalars()
                .all()
            )
            return run, model_calls, tool_calls

    async def list_runs(
        self, *, trigger: str | None = None, limit: int = 50
    ) -> list[AgentRun]:
        async with self._session() as s:
            stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
            if trigger:
                stmt = stmt.where(AgentRun.trigger == trigger)
            return list((await s.execute(stmt)).scalars().all())

    # ---- digests ---------------------------------------------------------

    async def upsert_digest(
        self, *, run_id: uuid.UUID, body: str, digest_date: date
    ) -> None:
        async with self._session() as s:
            existing = await s.execute(
                select(Digest).where(Digest.digest_date == digest_date)
            )
            row = existing.scalar_one_or_none()
            if row is None:
                s.add(Digest(run_id=run_id, body=body, digest_date=digest_date))
            else:
                row.body = body
                row.run_id = run_id
            await s.commit()

    async def get_digest(self, digest_date: date) -> Digest | None:
        async with self._session() as s:
            result = await s.execute(
                select(Digest).where(Digest.digest_date == digest_date)
            )
            return result.scalar_one_or_none()

    # ---- outbound messages (Phase B) ------------------------------------

    async def enqueue_outbound(self, body: str) -> uuid.UUID:
        async with self._session() as s:
            msg = OutboundMessage(body=body)
            s.add(msg)
            await s.commit()
            return msg.id

    async def pending_outbound(self, limit: int = 20) -> list[OutboundMessage]:
        async with self._session() as s:
            result = await s.execute(
                select(OutboundMessage)
                .where(OutboundMessage.status == "queued")
                .order_by(OutboundMessage.created_at)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def ack_outbound(
        self, msg_id: uuid.UUID, *, status: str, max_attempts: int = 3
    ) -> str | None:
        """Record a worker ack. Returns the resulting message status, or None
        if the message does not exist. A 'failed' ack stays 'queued' for retry
        until ``max_attempts`` is reached, then becomes 'failed'."""
        async with self._session() as s:
            msg = await s.get(OutboundMessage, msg_id)
            if msg is None:
                return None
            msg.attempts = (msg.attempts or 0) + 1
            msg.status = resolve_ack_status(status, msg.attempts, max_attempts)
            if msg.status == "sent":
                msg.sent_at = datetime.now()
            await s.commit()
            return msg.status
