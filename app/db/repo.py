"""All database access. No raw SQL or session handling lives outside this module.

``Repo`` wraps an async engine + sessionmaker and exposes typed reader/writer
functions. The agent loop, tools, and API routes depend only on this surface.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session

from app.auth.context import get_current_user_id
from app.config import DEFAULT_USER_ID
from app.db.models import (
    AgentRun,
    Alert,
    Digest,
    ModelCall,
    OutboundMessage,
    Position,
    SnaptradeCredentials,
    ToolCall,
    User,
)

# Owner (user #1) attribution until per-user auth lands. Every tenant-scoped
# read/write defaults to this user; pass user_id to scope to another.
_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)


@event.listens_for(Session, "after_begin")
def _apply_rls_user(session: Session, transaction, connection) -> None:
    """Set the per-transaction ``app.current_user_id`` GUC that RLS policies
    filter on, from the request's ContextVar. Background jobs (ContextVar unset)
    fall back to the owner. Under the table-owner DB role this is a harmless
    no-op (RLS is bypassed); it takes effect once DATABASE_URL points at a
    non-owner role (roadmap Phase 2 deploy step). The value is always a uuid, so
    inlining it is injection-safe."""
    uid = get_current_user_id() or _OWNER_USER_ID
    connection.exec_driver_sql(
        f"SELECT set_config('app.current_user_id', '{uid}', true)"
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

    # ---- users -----------------------------------------------------------

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        async with self._session() as s:
            return await s.get(User, user_id)

    async def get_or_create_user(
        self, *, auth_id: uuid.UUID, email: str | None = None
    ) -> uuid.UUID:
        """Resolve the app user for a Supabase auth uid, provisioning on first
        sight. Returns the app ``users.id`` (distinct from the auth uid)."""
        async with self._session() as s:
            existing = await s.execute(select(User.id).where(User.auth_id == auth_id))
            row = existing.scalar_one_or_none()
            if row is not None:
                return row
            user = User(auth_id=auth_id, email=email)
            s.add(user)
            await s.commit()
            return user.id

    async def list_active_user_ids(self) -> list[uuid.UUID]:
        """Users who should receive scheduled macro scans.

        Includes anyone with digest enabled or any synced position."""
        async with self._session() as s:
            enabled = await s.execute(
                select(User.id).where(User.digest_enabled.is_(True))
            )
            ids = {row for row in enabled.scalars().all()}
            positioned = await s.execute(select(Position.user_id).distinct())
            ids.update(positioned.scalars().all())
            if not ids:
                return [_OWNER_USER_ID]
            return sorted(ids)

    # ---- snaptrade credentials -------------------------------------------

    async def get_snaptrade_credentials(
        self, user_id: uuid.UUID
    ) -> SnaptradeCredentials | None:
        async with self._session() as s:
            return await s.get(SnaptradeCredentials, user_id)

    async def save_snaptrade_credentials(
        self,
        *,
        user_id: uuid.UUID,
        snaptrade_user_id: str,
        user_secret_enc: bytes,
    ) -> None:
        async with self._session() as s:
            row = await s.get(SnaptradeCredentials, user_id)
            if row is None:
                s.add(
                    SnaptradeCredentials(
                        user_id=user_id,
                        snaptrade_user_id=snaptrade_user_id,
                        user_secret_enc=user_secret_enc,
                    )
                )
            else:
                row.snaptrade_user_id = snaptrade_user_id
                row.user_secret_enc = user_secret_enc
            await s.commit()

    async def update_snaptrade_status(
        self,
        user_id: uuid.UUID,
        *,
        connected_at: datetime | None = None,
        last_sync_at: datetime | None = None,
        last_sync_error: str | None = None,
    ) -> None:
        async with self._session() as s:
            row = await s.get(SnaptradeCredentials, user_id)
            if row is None:
                return
            if connected_at is not None:
                row.connected_at = connected_at
            if last_sync_at is not None:
                row.last_sync_at = last_sync_at
            row.last_sync_error = last_sync_error
            await s.commit()

    # ---- positions -------------------------------------------------------

    async def list_positions(self, *, user_id: uuid.UUID | None = None) -> list[Position]:
        uid = user_id or _OWNER_USER_ID
        async with self._session() as s:
            result = await s.execute(select(Position).where(Position.user_id == uid))
            return list(result.scalars().all())

    async def upsert_position(
        self,
        *,
        ticker: str,
        quantity: Decimal,
        avg_cost: Decimal,
        currency: str,
        account: str,
        user_id: uuid.UUID | None = None,
    ) -> None:
        """Insert or update a position keyed by (user_id, ticker, account)."""
        uid = user_id or _OWNER_USER_ID
        async with self._session() as s:
            existing = await s.execute(
                select(Position).where(
                    Position.user_id == uid,
                    Position.ticker == ticker,
                    Position.account == account,
                )
            )
            row = existing.scalar_one_or_none()
            if row is None:
                s.add(
                    Position(
                        user_id=uid,
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

    async def prune_positions_except(
        self, keep: set[tuple[str, str]], *, user_id: uuid.UUID | None = None
    ) -> int:
        """Delete this user's positions whose (ticker, account) is not in ``keep``."""
        uid = user_id or _OWNER_USER_ID
        async with self._session() as s:
            result = await s.execute(select(Position).where(Position.user_id == uid))
            rows = list(result.scalars().all())
            removed = 0
            for row in rows:
                if (row.ticker, row.account) not in keep:
                    await s.delete(row)
                    removed += 1
            if removed:
                await s.commit()
            return removed

    # ---- agent runs & observability -------------------------------------

    async def create_run(
        self,
        *,
        trigger: str,
        user_message: str,
        model: str,
        prompt_version: str,
        user_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        async with self._session() as s:
            run = AgentRun(
                user_id=user_id or _OWNER_USER_ID,
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
        self,
        *,
        run_id: uuid.UUID,
        body: str,
        digest_date: date,
        user_id: uuid.UUID | None = None,
    ) -> None:
        uid = user_id or _OWNER_USER_ID
        async with self._session() as s:
            existing = await s.execute(
                select(Digest).where(
                    Digest.user_id == uid, Digest.digest_date == digest_date
                )
            )
            row = existing.scalar_one_or_none()
            if row is None:
                s.add(Digest(user_id=uid, run_id=run_id, body=body, digest_date=digest_date))
            else:
                row.body = body
                row.run_id = run_id
            await s.commit()

    async def get_digest(
        self, digest_date: date, *, user_id: uuid.UUID | None = None
    ) -> Digest | None:
        uid = user_id or _OWNER_USER_ID
        async with self._session() as s:
            result = await s.execute(
                select(Digest).where(
                    Digest.user_id == uid, Digest.digest_date == digest_date
                )
            )
            return result.scalar_one_or_none()

    # ---- macro alerts ----------------------------------------------------

    async def create_alert_if_new(
        self,
        *,
        run_id: uuid.UUID | None,
        category: str,
        severity: str,
        headline: str,
        body: str,
        tickers: list[str],
        fingerprint: str,
        user_id: uuid.UUID | None = None,
    ) -> uuid.UUID | None:
        """Insert an alert unless (user_id, fingerprint) already exists.

        Returns the new alert id, or None when this event was already alerted
        (dedup is enforced by the unique constraint — this is the happy path
        for a recurring scan re-seeing the same story)."""
        uid = user_id or _OWNER_USER_ID
        async with self._session() as s:
            existing = await s.execute(
                select(Alert.id).where(
                    Alert.user_id == uid, Alert.fingerprint == fingerprint
                )
            )
            if existing.scalar_one_or_none() is not None:
                return None
            alert = Alert(
                user_id=uid,
                run_id=run_id,
                category=category,
                severity=severity,
                headline=headline,
                body=body,
                tickers=tickers,
                fingerprint=fingerprint,
            )
            s.add(alert)
            try:
                await s.commit()
            except IntegrityError:
                await s.rollback()
                return None
            return alert.id

    async def recent_alerts(
        self, *, limit: int = 20, user_id: uuid.UUID | None = None
    ) -> list[Alert]:
        uid = user_id or _OWNER_USER_ID
        async with self._session() as s:
            result = await s.execute(
                select(Alert)
                .where(Alert.user_id == uid)
                .order_by(Alert.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def mark_alert_delivered(self, alert_id: uuid.UUID) -> None:
        async with self._session() as s:
            alert = await s.get(Alert, alert_id)
            if alert is not None:
                alert.delivered = True
                alert.delivered_at = datetime.now()
                await s.commit()

    # ---- outbound messages (Phase B) ------------------------------------

    async def enqueue_outbound(
        self, body: str, *, user_id: uuid.UUID | None = None
    ) -> uuid.UUID:
        async with self._session() as s:
            msg = OutboundMessage(body=body, user_id=user_id or _OWNER_USER_ID)
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
