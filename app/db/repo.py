"""All database access. No raw SQL or session handling lives outside this module.

``Repo`` wraps an async engine + sessionmaker and exposes typed reader/writer
functions. The agent loop, tools, and API routes depend only on this surface.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, event, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    DailyPrice,
    DeepDiveReport,
    Digest,
    JobHeartbeat,
    MemoryChunk,
    ModelCall,
    NewsItem,
    NotificationChannel,
    OutboundMessage,
    Position,
    SnaptradeCredentials,
    StripeEvent,
    TickerFundamentals,
    ToolCall,
    Transaction,
    User,
    VerificationCode,
)
from app.delivery.channels import CHANNELS

# Owner (user #1) attribution until per-user auth lands. Every tenant-scoped
# read/write defaults to this user; pass user_id to scope to another.
_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)


def digest_mentions_ticker(body: str | None, ticker: str) -> bool:
    """Whether a digest's prose mentions a ticker. Digests aren't ticker-tagged
    rows, so the ticker-filtered news feed (the stock detail page) matches on
    the text: the full Yahoo symbol or its exchange-less root (SHOP.TO → SHOP),
    case-sensitive with word boundaries so a ticker like TE doesn't match
    'tech'."""
    if not body:
        return False
    root = ticker.split(".")[0]
    pattern = rf"\b({re.escape(ticker)}|{re.escape(root)})\b"
    return re.search(pattern, body) is not None


@event.listens_for(Session, "after_begin")
def _apply_rls_user(session: Session, transaction, connection) -> None:
    """Set the per-transaction ``app.current_user_id`` GUC that RLS policies
    filter on, from the request's ContextVar. Background jobs (ContextVar unset)
    fall back to the owner id, which the policies treat as the service context
    (cross-tenant; see migration 012). This is load-bearing in production:
    DATABASE_URL there is a restricted non-owner role, so RLS is enforced on
    every app query. The value is always a uuid, so inlining it is
    injection-safe."""
    uid = get_current_user_id() or _OWNER_USER_ID
    connection.exec_driver_sql(
        f"SELECT set_config('app.current_user_id', '{uid}', true)"
    )


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

    async def update_user_preferences(
        self,
        user_id: uuid.UUID,
        *,
        timezone: str | None = None,
        digest_send_time: Any = None,
        digest_enabled: bool | None = None,
        digest_tickers: list[str] | None = None,
    ) -> None:
        """Update only the provided preference fields on the user's row."""
        async with self._session() as s:
            user = await s.get(User, user_id)
            if user is None:
                return
            if timezone is not None:
                user.timezone = timezone
            if digest_send_time is not None:
                user.digest_send_time = digest_send_time
            if digest_enabled is not None:
                user.digest_enabled = digest_enabled
            if digest_tickers is not None:
                user.digest_tickers = digest_tickers
            await s.commit()

    async def get_digest_tickers(self, user_id: uuid.UUID) -> list[str]:
        user = await self.get_user(user_id)
        if user is None:
            return []
        raw = getattr(user, "digest_tickers", None) or []
        return [str(t) for t in raw]

    async def set_digest_tickers(
        self, user_id: uuid.UUID, tickers: list[str]
    ) -> None:
        async with self._session() as s:
            user = await s.get(User, user_id)
            if user is None:
                return
            user.digest_tickers = tickers
            await s.commit()

    async def get_or_create_user(
        self, *, auth_id: uuid.UUID, email: str | None = None, trial_days: int = 0
    ) -> uuid.UUID:
        """Resolve the app user for a Supabase auth uid, provisioning on first
        sight (with a no-card Pro trial when ``trial_days`` > 0). Returns the
        app ``users.id`` (distinct from the auth uid)."""
        async with self._session() as s:
            existing = await s.execute(select(User.id).where(User.auth_id == auth_id))
            row = existing.scalar_one_or_none()
            if row is not None:
                return row
            trial_ends_at = (
                datetime.now(timezone.utc) + timedelta(days=trial_days)
                if trial_days > 0
                else None
            )
            user = User(auth_id=auth_id, email=email, trial_ends_at=trial_ends_at)
            s.add(user)
            await s.commit()
            return user.id

    async def resolve_trial(self, user_id: uuid.UUID) -> None:
        """The user chose to continue on Free (or the trial state is otherwise
        settled): clear the trial marker so digests resume on the Free cadence."""
        async with self._session() as s:
            user = await s.get(User, user_id)
            if user is None:
                return
            user.trial_ends_at = None
            await s.commit()

    async def list_active_user_ids(self) -> list[uuid.UUID]:
        """Users who should receive scheduled digests.

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

    async def list_digest_recipients(self) -> list[uuid.UUID]:
        """Users eligible for scheduled digests: enabled and holding at least one position."""
        async with self._session() as s:
            enabled = await s.execute(
                select(User.id).where(User.digest_enabled.is_(True))
            )
            ids = list(enabled.scalars().all())
            if not ids:
                return [_OWNER_USER_ID]
            out: list[uuid.UUID] = []
            for uid in ids:
                pos = await s.execute(
                    select(Position.id).where(Position.user_id == uid).limit(1)
                )
                if pos.scalar_one_or_none() is not None:
                    out.append(uid)
            return sorted(out) if out else [_OWNER_USER_ID]

    async def list_macro_recipients(self) -> list[uuid.UUID]:
        """Users on the Pro experience (paid, or an active no-card trial) with
        digests enabled — macro alerts are a Pro feature."""
        async with self._session() as s:
            result = await s.execute(
                select(User.id).where(
                    or_(
                        User.plan == "pro",
                        User.trial_ends_at > datetime.now(timezone.utc),
                    ),
                    User.digest_enabled.is_(True),
                )
            )
            return sorted(result.scalars().all())

    async def list_anomaly_recipients(self) -> list[uuid.UUID]:
        """Recipients for scheduled price-anomaly alerts: the macro (Pro)
        audience."""
        return sorted(await self.list_macro_recipients())

    async def monthly_cost_usd(self, user_id: uuid.UUID) -> float:
        """Sum of this user's agent-run cost so far this calendar month (UTC)."""
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        async with self._session() as s:
            result = await s.execute(
                select(func.coalesce(func.sum(AgentRun.cost_usd), 0)).where(
                    AgentRun.user_id == user_id, AgentRun.created_at >= start
                )
            )
            return float(result.scalar_one() or 0)

    async def chat_usage_since(
        self, user_id: uuid.UUID, since: datetime
    ) -> tuple[int, datetime | None]:
        """(count, oldest created_at) of this user's chat runs since ``since``.

        Quota contract: rows with trigger='chat' count unless status='error'
        (infrastructure failures don't burn questions; delivered answers —
        completed/budget_exceeded/max_iterations — and in-flight runs do).
        The oldest timestamp is when the next question unlocks (+ window)."""
        async with self._session() as s:
            result = await s.execute(
                select(func.count(), func.min(AgentRun.created_at)).where(
                    AgentRun.user_id == user_id,
                    AgentRun.trigger == "chat",
                    AgentRun.status != "error",
                    AgentRun.created_at >= since,
                )
            )
            count, oldest = result.one()
            return int(count or 0), oldest

    # ---- billing (Stripe) --------------------------------------------------

    async def get_user_by_stripe_customer_id(self, customer_id: str) -> User | None:
        async with self._session() as s:
            result = await s.execute(
                select(User).where(User.stripe_customer_id == customer_id)
            )
            return result.scalar_one_or_none()

    async def set_stripe_customer_id(
        self, user_id: uuid.UUID, customer_id: str
    ) -> str:
        """Link a Stripe customer to a user, first-writer-wins.

        Only fills a NULL slot and returns whichever id is stored afterwards,
        so a retried checkout can't clobber an existing link."""
        async with self._session() as s:
            user = await s.get(User, user_id)
            if user is None:
                return customer_id
            if user.stripe_customer_id is None:
                user.stripe_customer_id = customer_id
                await s.commit()
            return user.stripe_customer_id

    async def apply_subscription_state(
        self,
        user_id: uuid.UUID,
        *,
        plan: str,
        subscription_id: str | None,
        current_period_end: datetime | None,
        cancel_at_period_end: bool,
    ) -> None:
        """Single writer the Stripe webhook syncs subscription state through.

        Flipping to 'free' clears the subscription fields but keeps
        ``stripe_customer_id`` so a re-subscribe reuses the same customer."""
        async with self._session() as s:
            user = await s.get(User, user_id)
            if user is None:
                return
            if plan == "pro" and user.plan != "pro":
                user.plan_since = datetime.now(timezone.utc)
            user.plan = plan
            if plan == "pro":
                # Paying settles any trial state (active or decision-pending).
                user.trial_ends_at = None
                user.stripe_subscription_id = subscription_id
                user.stripe_current_period_end = current_period_end
                user.stripe_cancel_at_period_end = cancel_at_period_end
            else:
                user.stripe_subscription_id = None
                user.stripe_current_period_end = None
                user.stripe_cancel_at_period_end = False
            await s.commit()

    async def stripe_event_seen(self, event_id: str) -> bool:
        """Whether this webhook event id was already processed successfully."""
        async with self._session() as s:
            return await s.get(StripeEvent, event_id) is not None

    async def record_stripe_event(self, event_id: str, event_type: str) -> bool:
        """Mark a webhook event as processed. Called only AFTER successful
        handling so a failed event stays unrecorded and Stripe's retry gets
        processed instead of short-circuiting as a duplicate. False = another
        delivery won the race (harmless: event handling re-fetches current
        Stripe state, so double-processing is idempotent)."""
        async with self._session() as s:
            result = await s.execute(
                pg_insert(StripeEvent)
                .values(id=event_id, type=event_type)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await s.commit()
            return bool(result.rowcount)

    async def delete_user_data(self, user_id: uuid.UUID) -> None:
        """Delete everything this user owns, then the user row itself.

        Ordered children-first so plain (non-CASCADE) FKs never block:
        model/tool calls hang off agent_runs; digests, alerts, and news_items
        reference agent_runs via run_id so they go before the runs."""
        async with self._session() as s:
            run_ids = select(AgentRun.id).where(AgentRun.user_id == user_id)
            await s.execute(delete(ModelCall).where(ModelCall.run_id.in_(run_ids)))
            await s.execute(delete(ToolCall).where(ToolCall.run_id.in_(run_ids)))
            await s.execute(delete(Digest).where(Digest.user_id == user_id))
            await s.execute(delete(Alert).where(Alert.user_id == user_id))
            await s.execute(delete(NewsItem).where(NewsItem.user_id == user_id))
            await s.execute(
                delete(DeepDiveReport).where(DeepDiveReport.user_id == user_id)
            )
            await s.execute(
                delete(MemoryChunk).where(MemoryChunk.user_id == user_id)
            )
            await s.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
            await s.execute(
                delete(OutboundMessage).where(OutboundMessage.user_id == user_id)
            )
            await s.execute(
                delete(NotificationChannel).where(
                    NotificationChannel.user_id == user_id
                )
            )
            await s.execute(
                delete(VerificationCode).where(VerificationCode.user_id == user_id)
            )
            await s.execute(delete(Position).where(Position.user_id == user_id))
            await s.execute(delete(Transaction).where(Transaction.user_id == user_id))
            await s.execute(
                delete(SnaptradeCredentials).where(
                    SnaptradeCredentials.user_id == user_id
                )
            )
            await s.execute(delete(User).where(User.id == user_id))
            await s.commit()

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

    async def delete_snaptrade_credentials(self, user_id: uuid.UUID) -> bool:
        """Remove the stored SnapTrade identity. Returns False if none existed."""
        async with self._session() as s:
            row = await s.get(SnaptradeCredentials, user_id)
            if row is None:
                return False
            await s.delete(row)
            await s.commit()
            return True

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

    async def list_chat_runs(
        self, user_id: uuid.UUID, *, limit: int = 10
    ) -> list[AgentRun]:
        """This user's most recent chat runs, newest first (chat history)."""
        async with self._session() as s:
            result = await s.execute(
                select(AgentRun)
                .where(AgentRun.user_id == user_id, AgentRun.trigger == "chat")
                .order_by(AgentRun.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def list_runs(
        self,
        *,
        trigger: str | None = None,
        limit: int = 50,
        user_id: uuid.UUID | None = None,
    ) -> list[AgentRun]:
        """Recent runs, newest first. ``user_id=None`` means unscoped — only
        the owner/service caller may use that."""
        async with self._session() as s:
            stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
            if trigger:
                stmt = stmt.where(AgentRun.trigger == trigger)
            if user_id is not None:
                stmt = stmt.where(AgentRun.user_id == user_id)
            return list((await s.execute(stmt)).scalars().all())

    # ---- digests ---------------------------------------------------------

    async def upsert_digest(
        self,
        *,
        run_id: uuid.UUID,
        body: str,
        digest_date: date,
        user_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Returns the digest row id (memory ingestion references it)."""
        uid = user_id or _OWNER_USER_ID
        async with self._session() as s:
            existing = await s.execute(
                select(Digest).where(
                    Digest.user_id == uid, Digest.digest_date == digest_date
                )
            )
            row = existing.scalar_one_or_none()
            if row is None:
                row = Digest(
                    user_id=uid, run_id=run_id, body=body, digest_date=digest_date
                )
                s.add(row)
            else:
                row.body = body
                row.run_id = run_id
            await s.commit()
            return row.id

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

    # ---- semantic memory (pgvector) ----------------------------------------

    async def upsert_memory_chunks(self, rows: list[dict[str, Any]]) -> int:
        """Insert embedded chunks; the (user_id, source_type, source_id,
        chunk_index) unique key makes re-ingestion/backfill idempotent.
        Returns the number of rows actually inserted."""
        if not rows:
            return 0
        async with self._session() as s:
            stmt = (
                pg_insert(MemoryChunk)
                .values(rows)
                .on_conflict_do_nothing(
                    index_elements=["user_id", "source_type", "source_id", "chunk_index"]
                )
            )
            result = await s.execute(stmt)
            await s.commit()
            return result.rowcount or 0

    async def search_memory(
        self,
        *,
        user_id: uuid.UUID,
        embedding: list[float],
        k: int = 6,
        tickers: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        source_types: list[str] | None = None,
    ) -> list[tuple[MemoryChunk, float]]:
        """Cosine-nearest chunks for this user, optionally filtered by ticker
        (jsonb containment), date window, and source type. Returns
        (chunk, cosine_distance) pairs, nearest first. The explicit user_id
        filter is defense-in-depth alongside the RLS policy."""
        async with self._session() as s:
            dist = MemoryChunk.embedding.cosine_distance(embedding).label("dist")
            stmt = (
                select(MemoryChunk, dist)
                .where(MemoryChunk.user_id == user_id)
                .order_by(dist)
                .limit(max(1, k))
            )
            if tickers:
                stmt = stmt.where(
                    or_(*[MemoryChunk.tickers.contains([t]) for t in tickers])
                )
            if date_from is not None:
                stmt = stmt.where(MemoryChunk.content_date >= date_from)
            if date_to is not None:
                stmt = stmt.where(MemoryChunk.content_date <= date_to)
            if source_types:
                stmt = stmt.where(MemoryChunk.source_type.in_(source_types))
            result = await s.execute(stmt)
            return [(row[0], float(row[1])) for row in result.all()]

    # ---- deep-dive reports -------------------------------------------------

    async def create_deep_dive_report(
        self, *, run_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> uuid.UUID:
        async with self._session() as s:
            row = DeepDiveReport(
                user_id=user_id or _OWNER_USER_ID, run_id=run_id, status="running"
            )
            s.add(row)
            await s.commit()
            return row.id

    async def update_deep_dive_report(
        self,
        report_id: uuid.UUID,
        *,
        status: str | None = None,
        report: dict | None = None,
        summary: str | None = None,
        progress: dict | None = None,
        cost_usd: float | None = None,
    ) -> None:
        async with self._session() as s:
            row = await s.get(DeepDiveReport, report_id)
            if row is None:
                return
            if status is not None:
                row.status = status
                if status in ("completed", "partial", "error"):
                    row.completed_at = datetime.now(timezone.utc)
            if report is not None:
                row.report = report
            if summary is not None:
                row.summary = summary
            if progress is not None:
                row.progress = progress
            if cost_usd is not None:
                row.cost_usd = Decimal(str(cost_usd))
            await s.commit()

    async def get_deep_dive_report(
        self, report_id: uuid.UUID
    ) -> DeepDiveReport | None:
        async with self._session() as s:
            return await s.get(DeepDiveReport, report_id)

    async def list_deep_dive_reports(
        self, user_id: uuid.UUID, *, limit: int = 10
    ) -> list[DeepDiveReport]:
        """This user's reports, newest first (dashboard history)."""
        async with self._session() as s:
            result = await s.execute(
                select(DeepDiveReport)
                .where(DeepDiveReport.user_id == user_id)
                .order_by(DeepDiveReport.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def deep_dive_usage_since(
        self, user_id: uuid.UUID, since: datetime
    ) -> tuple[int, datetime | None]:
        """(count, oldest created_at) of deep dives in the window — quota is
        counted on report rows, not agent_runs, so the pipeline's specialist
        sub-runs don't inflate it."""
        async with self._session() as s:
            result = await s.execute(
                select(
                    func.count(DeepDiveReport.id), func.min(DeepDiveReport.created_at)
                ).where(
                    DeepDiveReport.user_id == user_id,
                    DeepDiveReport.created_at >= since,
                )
            )
            count, oldest = result.one()
            return int(count or 0), oldest

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

    async def recent_alerts_by_category(
        self, user_id: uuid.UUID, *, category: str, since: datetime
    ) -> list[Alert]:
        """This user's alerts of one category created since ``since``.

        Powers the anomaly cooldown: a ticker appearing in a recent
        price_anomaly alert stays quiet for the cooldown window."""
        async with self._session() as s:
            result = await s.execute(
                select(Alert).where(
                    Alert.user_id == user_id,
                    Alert.category == category,
                    Alert.created_at >= since,
                )
            )
            return list(result.scalars().all())

    async def list_distinct_tickers(
        self, user_ids: list[uuid.UUID] | None = None
    ) -> list[str]:
        """Distinct tickers across positions (optionally limited to some
        users) — the global anomaly scan runs once per ticker, not per user."""
        async with self._session() as s:
            q = select(Position.ticker).distinct()
            if user_ids is not None:
                q = q.where(Position.user_id.in_(user_ids))
            result = await s.execute(q)
            return sorted(result.scalars().all())

    async def list_recent_digests(
        self,
        *,
        user_id: uuid.UUID | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[Digest]:
        uid = user_id or _OWNER_USER_ID
        async with self._session() as s:
            q = select(Digest).where(Digest.user_id == uid)
            if since is not None:
                q = q.where(Digest.created_at >= since)
            result = await s.execute(
                q.order_by(Digest.created_at.desc()).limit(limit)
            )
            return list(result.scalars().all())

    @staticmethod
    def news_fingerprint(url: str | None, headline: str) -> str:
        key = f"{url or ''}|{headline}".encode()
        return hashlib.sha256(key).hexdigest()

    async def insert_news_items_if_new(
        self,
        user_id: uuid.UUID,
        items: list[dict[str, Any]],
        *,
        run_id: uuid.UUID | None = None,
    ) -> list[NewsItem]:
        """Insert holding news articles; skip duplicates via fingerprint.
        Returns the rows actually inserted (memory ingestion embeds them;
        callers wanting a count use ``len()``)."""
        if not items:
            return []
        uid = user_id or _OWNER_USER_ID
        inserted: list[NewsItem] = []
        async with self._session() as s:
            for item in items:
                fp = item.get("fingerprint") or self.news_fingerprint(
                    item.get("url"), item["headline"]
                )
                existing = await s.execute(
                    select(NewsItem.id).where(
                        NewsItem.user_id == uid, NewsItem.fingerprint == fp
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    continue
                pub = item.get("published_at")
                if isinstance(pub, str):
                    pub = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                row = NewsItem(
                    user_id=uid,
                    ticker=item["ticker"],
                    headline=item["headline"],
                    source=item.get("source"),
                    url=item.get("url"),
                    published_at=pub,
                    summary=item.get("summary"),
                    run_id=run_id,
                    fingerprint=fp,
                )
                s.add(row)
                inserted.append(row)
            await s.commit()
        return inserted

    async def list_news_items(
        self,
        *,
        user_id: uuid.UUID | None = None,
        ticker: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        uid = user_id or _OWNER_USER_ID
        # The feed lives on publish time; created_at (insertion time) only
        # backfills rows without one, so a batch inserted Monday still reads
        # as Friday/Saturday/Sunday news.
        effective = func.coalesce(NewsItem.published_at, NewsItem.created_at)
        async with self._session() as s:
            q = select(NewsItem).where(NewsItem.user_id == uid)
            if ticker is not None:
                q = q.where(NewsItem.ticker == ticker)
            if since is not None:
                q = q.where(effective >= since)
            result = await s.execute(q.order_by(effective.desc()).limit(limit))
            return list(result.scalars().all())

    async def list_stored_news(
        self,
        user_id: uuid.UUID,
        *,
        ticker: str | None = None,
        kind: str = "all",
        since: datetime | None = None,
        severity: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Merge digests, alerts, and news_items into a normalized feed."""
        kinds = {k.strip() for k in kind.split(",") if k.strip()} or {"all"}
        if "all" in kinds:
            kinds = {"all"}
        out: list[dict[str, Any]] = []
        include_digest = "all" in kinds or "digest" in kinds
        include_alert = "all" in kinds or "alert" in kinds
        include_holding = "all" in kinds or "holding" in kinds

        if include_digest:
            for d in await self.list_recent_digests(
                user_id=user_id, since=since, limit=limit
            ):
                # Ticker-filtered feeds keep only digests whose prose mentions
                # the ticker (digests aren't ticker-tagged rows).
                if ticker is not None and not digest_mentions_ticker(d.body, ticker):
                    continue
                created = d.created_at or datetime.now(timezone.utc)
                out.append(
                    {
                        "id": str(d.id),
                        "kind": "digest",
                        "ticker": None,
                        "tickers": [],
                        "headline": f"Morning digest — {d.digest_date.isoformat()}",
                        "body": d.body,
                        "source": None,
                        "url": None,
                        "severity": None,
                        "category": None,
                        "published_at": None,
                        "created_at": created.isoformat(),
                    }
                )

        if include_alert:
            alerts = await self.recent_alerts(limit=limit * 2, user_id=user_id)
            for a in alerts:
                if since is not None and a.created_at and a.created_at < since:
                    continue
                if severity and a.severity != severity:
                    continue
                if category and a.category != category:
                    continue
                tickers = a.tickers if isinstance(a.tickers, list) else []
                if ticker is not None and ticker not in tickers:
                    continue
                created = a.created_at or datetime.now(timezone.utc)
                out.append(
                    {
                        "id": str(a.id),
                        "kind": "alert",
                        "ticker": tickers[0] if len(tickers) == 1 else None,
                        "tickers": tickers,
                        "headline": a.headline,
                        "body": a.body,
                        "source": None,
                        "url": None,
                        "severity": a.severity,
                        "category": a.category,
                        "published_at": None,
                        "created_at": created.isoformat(),
                    }
                )

        if include_holding:
            for n in await self.list_news_items(
                user_id=user_id, ticker=ticker, since=since, limit=limit
            ):
                created = n.created_at or datetime.now(timezone.utc)
                pub = n.published_at.isoformat() if n.published_at else None
                out.append(
                    {
                        "id": str(n.id),
                        "kind": "holding",
                        "ticker": n.ticker,
                        "tickers": [n.ticker],
                        "headline": n.headline,
                        "body": n.summary or "",
                        "source": n.source,
                        "url": n.url,
                        "severity": None,
                        "category": None,
                        "published_at": pub,
                        "created_at": created.isoformat(),
                    }
                )

        # Feed order is publish time when known (holding articles), insertion
        # time otherwise (digests, alerts). Parse rather than compare strings:
        # mixed UTC offsets would break lexicographic ordering.
        def _effective_ts(x: dict[str, Any]) -> datetime:
            return datetime.fromisoformat(x["published_at"] or x["created_at"])

        out.sort(key=_effective_ts, reverse=True)
        return out[:limit]

    async def mark_alert_delivered(self, alert_id: uuid.UUID) -> None:
        async with self._session() as s:
            alert = await s.get(Alert, alert_id)
            if alert is not None:
                alert.delivered = True
                alert.delivered_at = datetime.now()
                await s.commit()

    # ---- outbound messages (delivery queue) ------------------------------

    async def enqueue_outbound(
        self,
        body: str,
        *,
        user_id: uuid.UUID | None = None,
        kind: str = "message",
        subject: str | None = None,
        sms_body: str | None = None,
    ) -> uuid.UUID:
        """Queue a message for delivery, resolving the user's preferred channel
        now (destination snapshot). No verified, opted-in channel -> the row is
        written as 'skipped' with the reason in last_error, so generation always
        succeeds and delivery state stays auditable.

        ``sms_body`` is a channel-aware override: when the resolved channel is
        SMS, the shorter ``sms_body`` is delivered instead of ``body`` (which is
        the richer version kept for email/Discord/web). Skipped rows retain the
        full ``body`` for the audit trail."""
        uid = user_id or _OWNER_USER_ID
        payload: dict[str, Any] = {"kind": kind}
        if subject:
            payload["subject"] = subject
        async with self._session() as s:
            user = await s.get(User, uid)
            preferred = user.preferred_channel if user else None
            msg = OutboundMessage(body=body, user_id=uid, payload=payload)
            if preferred is None:
                msg.status = "skipped"
                msg.last_error = "no preferred notification channel"
            else:
                ch = await s.execute(
                    select(NotificationChannel).where(
                        NotificationChannel.user_id == uid,
                        NotificationChannel.channel == preferred,
                    )
                )
                row = ch.scalar_one_or_none()
                if row is None or row.verified_at is None:
                    msg.status = "skipped"
                    msg.last_error = f"preferred channel '{preferred}' not verified"
                elif row.opted_out_at is not None:
                    msg.status = "skipped"
                    msg.last_error = f"preferred channel '{preferred}' opted out"
                else:
                    msg.channel = preferred
                    msg.destination = row.destination
                    if preferred == "sms" and sms_body:
                        msg.body = sms_body
            s.add(msg)
            await s.commit()
            return msg.id

    async def claim_due_outbound(
        self, limit: int = 25, *, lease_seconds: int = 120
    ) -> list[OutboundMessage]:
        """Claim due queued rows for the dispatcher. FOR UPDATE SKIP LOCKED keeps
        concurrent workers disjoint; pushing next_attempt_at out by
        ``lease_seconds`` means a crash mid-send just retries after the lease."""
        async with self._session() as s:
            result = await s.execute(
                select(OutboundMessage)
                .where(
                    OutboundMessage.status == "queued",
                    OutboundMessage.channel.in_(CHANNELS),
                    OutboundMessage.next_attempt_at <= func.now(),
                )
                .order_by(OutboundMessage.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            msgs = list(result.scalars().all())
            lease = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
            for m in msgs:
                m.next_attempt_at = lease
            await s.commit()
            return msgs

    async def record_send_result(
        self,
        msg_id: uuid.UUID,
        *,
        ok: bool,
        provider_message_id: str | None = None,
        error: str | None = None,
        permanent: bool = False,
        max_attempts: int = 5,
        retry_delay_seconds: int = 60,
    ) -> str | None:
        """Finalize a dispatcher send attempt. Transient failures requeue with
        ``retry_delay_seconds`` backoff until ``max_attempts``; permanent ones
        fail immediately. Returns the resulting status, or None if missing."""
        async with self._session() as s:
            msg = await s.get(OutboundMessage, msg_id)
            if msg is None:
                return None
            msg.attempts = (msg.attempts or 0) + 1
            if ok:
                msg.status = "sent"
                msg.sent_at = datetime.now(timezone.utc)
                msg.provider_message_id = provider_message_id
                msg.last_error = None
            else:
                msg.last_error = error
                if permanent or msg.attempts >= max_attempts:
                    msg.status = "failed"
                else:
                    msg.status = "queued"
                    msg.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                        seconds=retry_delay_seconds
                    )
            await s.commit()
            return msg.status

    # ---- notification channels -------------------------------------------

    async def get_notification_channels(
        self, user_id: uuid.UUID
    ) -> list[NotificationChannel]:
        async with self._session() as s:
            result = await s.execute(
                select(NotificationChannel)
                .where(NotificationChannel.user_id == user_id)
                .order_by(NotificationChannel.channel)
            )
            return list(result.scalars().all())

    async def get_notification_channel(
        self, user_id: uuid.UUID, channel: str
    ) -> NotificationChannel | None:
        async with self._session() as s:
            result = await s.execute(
                select(NotificationChannel).where(
                    NotificationChannel.user_id == user_id,
                    NotificationChannel.channel == channel,
                )
            )
            return result.scalar_one_or_none()

    async def upsert_notification_channel(
        self,
        user_id: uuid.UUID,
        *,
        channel: str,
        destination: str,
        consent: bool = False,
    ) -> NotificationChannel:
        """Register (or re-register) a destination for a channel. A changed
        destination resets verification; consent is timestamped when given."""
        now = datetime.now(timezone.utc)
        async with self._session() as s:
            result = await s.execute(
                select(NotificationChannel).where(
                    NotificationChannel.user_id == user_id,
                    NotificationChannel.channel == channel,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = NotificationChannel(
                    user_id=user_id, channel=channel, destination=destination
                )
                s.add(row)
            elif row.destination != destination:
                row.destination = destination
                row.verified_at = None
                row.opted_out_at = None
            if consent:
                row.consent_at = now
            row.updated_at = now
            await s.commit()
            return row

    async def mark_channel_verified(self, user_id: uuid.UUID, channel: str) -> bool:
        """Set verified_at and clear any opt-out. Returns False if unregistered."""
        async with self._session() as s:
            result = await s.execute(
                select(NotificationChannel).where(
                    NotificationChannel.user_id == user_id,
                    NotificationChannel.channel == channel,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            now = datetime.now(timezone.utc)
            row.verified_at = now
            row.opted_out_at = None
            row.updated_at = now
            await s.commit()
            return True

    async def set_preferred_channel(
        self, user_id: uuid.UUID, channel: str | None
    ) -> bool:
        """Switch the user's preferred channel. Non-null channels must already
        be verified and not opted out. Returns False if that doesn't hold."""
        async with self._session() as s:
            user = await s.get(User, user_id)
            if user is None:
                return False
            if channel is not None:
                result = await s.execute(
                    select(NotificationChannel).where(
                        NotificationChannel.user_id == user_id,
                        NotificationChannel.channel == channel,
                    )
                )
                row = result.scalar_one_or_none()
                if row is None or row.verified_at is None or row.opted_out_at is not None:
                    return False
            user.preferred_channel = channel
            await s.commit()
            return True

    async def set_opt_out_by_destination(
        self, *, channel: str, destination: str, opted_out: bool
    ) -> int:
        """Set/clear opt-out for every registration of a destination (used by
        the Twilio STOP/START webhook, where only the phone number is known).
        Returns the number of rows updated."""
        now = datetime.now(timezone.utc)
        async with self._session() as s:
            result = await s.execute(
                select(NotificationChannel).where(
                    NotificationChannel.channel == channel,
                    NotificationChannel.destination == destination,
                )
            )
            rows = list(result.scalars().all())
            for row in rows:
                row.opted_out_at = now if opted_out else None
                row.updated_at = now
            await s.commit()
            return len(rows)

    # ---- verification codes ----------------------------------------------

    async def create_verification_code(
        self,
        user_id: uuid.UUID,
        *,
        channel: str,
        destination: str,
        code_hash: str,
        ttl_seconds: int = 600,
    ) -> uuid.UUID:
        """Store a hashed one-time code, invalidating any live one for the same
        channel so only the latest code checks out."""
        now = datetime.now(timezone.utc)
        async with self._session() as s:
            result = await s.execute(
                select(VerificationCode).where(
                    VerificationCode.user_id == user_id,
                    VerificationCode.channel == channel,
                    VerificationCode.consumed_at.is_(None),
                    VerificationCode.expires_at > now,
                )
            )
            for stale in result.scalars().all():
                stale.consumed_at = now
            code = VerificationCode(
                user_id=user_id,
                channel=channel,
                destination=destination,
                code_hash=code_hash,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            s.add(code)
            await s.commit()
            return code.id

    async def latest_verification_code(
        self, user_id: uuid.UUID, channel: str
    ) -> VerificationCode | None:
        """The live (unconsumed, unexpired) code for a channel, if any."""
        async with self._session() as s:
            result = await s.execute(
                select(VerificationCode)
                .where(
                    VerificationCode.user_id == user_id,
                    VerificationCode.channel == channel,
                    VerificationCode.consumed_at.is_(None),
                    VerificationCode.expires_at > datetime.now(timezone.utc),
                )
                .order_by(VerificationCode.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def record_code_attempt(self, code_id: uuid.UUID) -> int:
        """Increment failed-check attempts; returns the new count."""
        async with self._session() as s:
            code = await s.get(VerificationCode, code_id)
            if code is None:
                return 0
            code.attempts = (code.attempts or 0) + 1
            await s.commit()
            return code.attempts

    async def consume_verification_code(self, code_id: uuid.UUID) -> None:
        async with self._session() as s:
            code = await s.get(VerificationCode, code_id)
            if code is not None:
                code.consumed_at = datetime.now(timezone.utc)
                await s.commit()

    async def count_verification_codes_since(
        self,
        since: datetime,
        *,
        destination: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> int:
        """Issued-code count for rate limiting (per destination or per user)."""
        async with self._session() as s:
            query = select(func.count()).where(VerificationCode.created_at >= since)
            if destination is not None:
                query = query.where(VerificationCode.destination == destination)
            if user_id is not None:
                query = query.where(VerificationCode.user_id == user_id)
            result = await s.execute(query)
            return int(result.scalar_one() or 0)

    # ---- job heartbeats (scheduled-job liveness, read by /health) ---------

    async def record_job_attempt(self, job_name: str) -> None:
        now = datetime.now(timezone.utc)
        async with self._session() as s:
            stmt = pg_insert(JobHeartbeat).values(
                job_name=job_name, last_attempt_at=now, updated_at=now
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[JobHeartbeat.job_name],
                set_={"last_attempt_at": now, "updated_at": now},
            )
            await s.execute(stmt)
            await s.commit()

    async def record_job_result(
        self, job_name: str, *, ok: bool, error: str | None = None
    ) -> None:
        now = datetime.now(timezone.utc)
        async with self._session() as s:
            if ok:
                values = {
                    "last_success_at": now,
                    "last_error": None,
                    "consecutive_failures": 0,
                    "updated_at": now,
                }
                update = dict(values)
            else:
                values = {
                    "last_error": error,
                    "consecutive_failures": 1,
                    "updated_at": now,
                }
                update = {
                    "last_error": error,
                    "consecutive_failures": JobHeartbeat.consecutive_failures + 1,
                    "updated_at": now,
                }
            stmt = pg_insert(JobHeartbeat).values(job_name=job_name, **values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[JobHeartbeat.job_name], set_=update
            )
            await s.execute(stmt)
            await s.commit()

    async def get_job_heartbeats(self) -> list[JobHeartbeat]:
        async with self._session() as s:
            result = await s.execute(select(JobHeartbeat))
            return list(result.scalars().all())

    # ---- ticker fundamentals (global per-ticker cache, all tenants) -------

    async def get_ticker_fundamentals(
        self, tickers: list[str]
    ) -> dict[str, TickerFundamentals]:
        async with self._session() as s:
            result = await s.execute(
                select(TickerFundamentals).where(TickerFundamentals.ticker.in_(tickers))
            )
            return {row.ticker: row for row in result.scalars().all()}

    async def upsert_ticker_fundamentals(
        self,
        *,
        ticker: str,
        quote_type: str | None,
        data: dict,
        fetch_error: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with self._session() as s:
            stmt = pg_insert(TickerFundamentals).values(
                ticker=ticker,
                quote_type=quote_type,
                data=data,
                fetched_at=now,
                fetch_error=fetch_error,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[TickerFundamentals.ticker],
                set_={
                    "quote_type": quote_type,
                    "data": data,
                    "fetched_at": now,
                    "fetch_error": fetch_error,
                },
            )
            await s.execute(stmt)
            await s.commit()

    # ---- daily prices (global per-ticker adjusted-close cache) ------------

    async def get_daily_prices(
        self, ticker: str, *, since: date | None = None
    ) -> list[DailyPrice]:
        """Stored adjusted closes for one ticker, oldest first, on/after
        ``since`` (all history when ``since`` is None)."""
        async with self._session() as s:
            q = select(DailyPrice).where(DailyPrice.ticker == ticker)
            if since is not None:
                q = q.where(DailyPrice.price_date >= since)
            q = q.order_by(DailyPrice.price_date)
            result = await s.execute(q)
            return list(result.scalars().all())

    async def upsert_daily_prices(
        self, ticker: str, rows: list[dict[str, Any]]
    ) -> int:
        """Bulk-upsert ``{date, adj_close[, close, currency]}`` rows for one
        ticker. ``date`` is an ISO string or a ``date``. Returns the count."""
        if not rows:
            return 0
        now = datetime.now(timezone.utc)
        values = []
        for r in rows:
            d = r.get("date") if r.get("date") is not None else r.get("price_date")
            if isinstance(d, str):
                d = date.fromisoformat(d)
            adj = r.get("adj_close")
            if d is None or adj is None:
                continue
            values.append(
                {
                    "ticker": ticker,
                    "price_date": d,
                    "adj_close": adj,
                    "close": r.get("close"),
                    "currency": r.get("currency"),
                    "updated_at": now,
                }
            )
        if not values:
            return 0
        async with self._session() as s:
            stmt = pg_insert(DailyPrice).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[DailyPrice.ticker, DailyPrice.price_date],
                set_={
                    "adj_close": stmt.excluded.adj_close,
                    "close": stmt.excluded.close,
                    "currency": stmt.excluded.currency,
                    "updated_at": now,
                },
            )
            await s.execute(stmt)
            await s.commit()
        return len(values)
