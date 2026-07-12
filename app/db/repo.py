"""All database access. No raw SQL or session handling lives outside this module.

``Repo`` wraps an async engine + sessionmaker and exposes typed reader/writer
functions. The agent loop, tools, and API routes depend only on this surface.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, event, func, select, text
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
    NewsItem,
    NotificationChannel,
    OutboundMessage,
    Position,
    SnaptradeCredentials,
    ToolCall,
    Transaction,
    User,
    VerificationCode,
)
from app.delivery.channels import CHANNELS

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
        """Pro users (macro alerts are a Pro feature) with digests enabled."""
        async with self._session() as s:
            result = await s.execute(
                select(User.id).where(
                    User.plan == "pro", User.digest_enabled.is_(True)
                )
            )
            return sorted(result.scalars().all())

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

    async def count_chats_today(self, user_id: uuid.UUID) -> int:
        """This user's chat runs since UTC midnight (Free daily-limit check)."""
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        async with self._session() as s:
            result = await s.execute(
                select(func.count()).where(
                    AgentRun.user_id == user_id,
                    AgentRun.trigger == "chat",
                    AgentRun.created_at >= start,
                )
            )
            return int(result.scalar_one() or 0)

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
    ) -> int:
        """Insert holding news articles; skip duplicates via fingerprint."""
        if not items:
            return 0
        uid = user_id or _OWNER_USER_ID
        inserted = 0
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
                s.add(
                    NewsItem(
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
                )
                inserted += 1
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
        async with self._session() as s:
            q = select(NewsItem).where(NewsItem.user_id == uid)
            if ticker is not None:
                q = q.where(NewsItem.ticker == ticker)
            if since is not None:
                q = q.where(NewsItem.created_at >= since)
            result = await s.execute(
                q.order_by(NewsItem.created_at.desc()).limit(limit)
            )
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
        include_digest = ("all" in kinds or "digest" in kinds) and ticker is None
        include_alert = "all" in kinds or "alert" in kinds
        include_holding = "all" in kinds or "holding" in kinds

        if include_digest:
            for d in await self.list_recent_digests(
                user_id=user_id, since=since, limit=limit
            ):
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

        out.sort(key=lambda x: x["created_at"], reverse=True)
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
    ) -> uuid.UUID:
        """Queue a message for delivery, resolving the user's preferred channel
        now (destination snapshot). No verified, opted-in channel -> the row is
        written as 'skipped' with the reason in last_error, so generation always
        succeeds and delivery state stays auditable."""
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
