"""SQLAlchemy 2.0 models mirroring the schema in ``migrations/001_init.sql``.

The SQL migrations are the source of truth for the schema; these models exist
for typed ORM access via ``repo.py``. Keep them in sync with the migrations.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import DEFAULT_USER_ID


class Base(DeclarativeBase):
    pass


# Every tenant-scoped row defaults to the owner (user #1) until per-user auth
# lands; the DB has the same default (migration 002), so writes need not set it.
_OWNER_DEFAULT = text(f"'{DEFAULT_USER_ID}'")


def _user_id_column() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        server_default=_OWNER_DEFAULT,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    # Supabase Auth uid (JWT sub); NULL for the seeded owner until linked.
    auth_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    # 'free' | 'pro' — gates features and per-user cost caps. Owner is 'pro'.
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'free'"))
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="America/Toronto")
    digest_send_time: Mapped[time] = mapped_column(
        Time, nullable=False, server_default=text("'09:00'")
    )
    digest_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    # 'sms' | 'email' | 'discord' | NULL = none chosen (delivery skipped).
    preferred_channel: Mapped[str | None] = mapped_column(Text)
    # Free-tier ordered watchlist for digest news coverage (max 3 tickers).
    digest_tickers: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    # Investor profile (migration 022). Traits are source of truth; the
    # archetype is a derived label (app/profile.py). All NULL/[] = not
    # profiled — code substitutes DEFAULT_PROFILE.
    investor_archetype: Mapped[str | None] = mapped_column(Text)
    risk_tolerance: Mapped[int | None] = mapped_column(SmallInteger)
    investing_horizon: Mapped[str | None] = mapped_column(Text)
    investing_experience: Mapped[str | None] = mapped_column(Text)
    investing_goals: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    profile_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    profile_prompt_dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Dashboard product tour (migration 031). Set on finish or skip; NULL =
    # never seen. Overlay state only — never consulted for routing.
    tutorial_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # No-card Pro trial (migration 017). Future = trial active (Pro
    # experience); past + plan 'free' = digests paused pending the user's
    # upgrade-or-free decision (bounded by the grace window in app/plans.py);
    # NULL = resolved or not yet started.
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the account's one trial was armed (migration 024) — at the first
    # successful portfolio sync, not signup. Non-NULL = consumed, never re-arm.
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Stripe billing linkage (migration 015). Customer id survives a
    # downgrade so a re-subscribe reuses the same Stripe customer.
    stripe_customer_id: Mapped[str | None] = mapped_column(Text, unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(Text)
    plan_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stripe_current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    stripe_cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StripeEvent(Base):
    """Processed-webhook ledger for idempotent Stripe delivery (migration 015)."""

    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # evt_...
    type: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PushDevice(Base):
    """One registered device token for native push (migration 030).

    ``expo_token`` is unique on its own, not per user: a device that signs
    into a second account moves rather than duplicates, so one phone can never
    receive two accounts' notifications.
    """

    __tablename__ = "push_devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    expo_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False, default="ios")
    # JSONB rather than text[], matching users.digest_tickers — the fan-out
    # filters in Python, so array containment buys nothing here.
    kinds: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text('\'["digest","alert","deep_dive"]\'')
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NotificationChannel(Base):
    """A user's registered destination for one channel (migration 007)."""

    __tablename__ = "notification_channels"
    __table_args__ = (UniqueConstraint("user_id", "channel"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VerificationCode(Base):
    """One-time destination-ownership code, hashed at rest (migration 007)."""

    __tablename__ = "verification_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "ticker", "account"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="CAD")
    account: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WatchlistItem(Base):
    """A ticker the user opted to follow (need not be held) — migration 021.

    Presence = subscribed: watched tickers get news-refresh coverage, a digest
    WATCHLIST section, and anomaly-scan coverage. Plan-capped at write time.
    """

    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "ticker"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (CheckConstraint("side IN ('buy','sell')", name="transactions_side_check"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    fees: Mapped[Decimal | None] = mapped_column(Numeric, default=0)
    account: Mapped[str] = mapped_column(Text, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    iterations: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ModelCall(Base):
    __tablename__ = "model_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    request: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    usage: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSONB)
    is_error: Mapped[bool | None] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Digest(Base):
    __tablename__ = "digests"
    __table_args__ = (UniqueConstraint("user_id", "digest_date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivered: Mapped[bool | None] = mapped_column(Boolean, default=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_channel: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MemoryChunk(Base):
    """Semantic-memory row: one embedded chunk of something the product told
    this user (digest, news item, chat answer). A pure derived cache of those
    source tables — safe to truncate and re-backfill on embedding-model
    changes. ``content_date`` is the content's semantic date (digest date,
    published_at, chat time), which recall filters on."""

    __tablename__ = "memory_chunks"
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_id", "chunk_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    # digest | news | chat | alert (CHECK-constrained in migration 019)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tickers: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    content_date: Mapped[date] = mapped_column(Date, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(1024), nullable=False)
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeepDiveReport(Base):
    """One multi-agent deep-dive research run (see app/agent/deep_dive/).

    ``report`` is the structured JSON the dashboard renders; ``summary`` the
    short deliverable text; ``progress`` a stage snapshot for reconnecting
    progress UIs. ``run_id`` is the anchor agent_runs row that owns cost/
    observability for the whole pipeline."""

    __tablename__ = "deep_dive_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False
    )
    # running | completed | partial | error
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    report: Mapped[dict | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # queued | sent | failed | skipped (no verified channel at enqueue time)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    attempts: Mapped[int | None] = mapped_column(Integer, default=0)
    # sms | email | discord; resolved at enqueue time (NULL on skipped rows).
    channel: Mapped[str | None] = mapped_column(Text)
    destination: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SnaptradeCredentials(Base):
    __tablename__ = "snaptrade_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    snaptrade_user_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_secret_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id")
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tickers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NewsItem(Base):
    """Holding-specific news articles surfaced during digest runs."""

    __tablename__ = "news_items"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id")
    )
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JobHeartbeat(Base):
    """Per-scheduled-job liveness accounting (system table, not tenant data).

    Written by the heartbeat wrapper in ``app/jobs.py``; read by GET /health
    to derive live/degraded/offline from staleness."""

    __tablename__ = "job_heartbeats"

    job_name: Mapped[str] = mapped_column(Text, primary_key=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TickerFundamentals(Base):
    """Global per-ticker fundamentals cache (system table, not tenant data).

    One yfinance ``.info`` snapshot per ticker shared across all users,
    written by ``app/tools/fundamentals.py`` (nightly refresh job + lazy
    stale-while-revalidate on read). ``data`` holds the normalized payload —
    JSONB so adding a metric is a code change, not a migration."""

    __tablename__ = "ticker_fundamentals"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    quote_type: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fetch_error: Mapped[str | None] = mapped_column(Text)


class TickerValuation(Base):
    """Global per-ticker "cheap or expensive" verdict cache (migration 028).

    Latest-only, like ``TickerFundamentals`` -- not point-in-time like
    ``FundamentalsSnapshot``. Written once daily by
    ``app/tools/valuation_refresh.py`` from
    ``app/quant/valuation.py::compute_valuations()``; read as a flat row by
    both ``GET /stocks/valuations`` (public) and the ``verdict`` block on
    ``GET /stocks/{ticker}`` (evidence field-gated to Pro plans).

    ``sector`` is always the ticker's actual GICS sector -- shown as company
    metadata on the free grid -- and is *not* necessarily the group the
    verdict was computed against, since scoring is industry-first (see
    ``app/quant/screener.py``'s ``MIN_INDUSTRY_SIZE``/``MIN_SECTOR_SIZE``
    fallback chain). ``sector_comparison`` says which tier actually fired
    ("industry" / "sector" / "universe (too small)"); the actual industry
    label used, when that tier is "industry", lives in
    ``evidence["industry"]`` rather than a dedicated column -- no migration
    needed, same JSONB-extensibility posture as ``TickerFundamentals.data``.
    ``sector_z`` is named for history but is the peer-relative z regardless
    of which tier produced it."""

    __tablename__ = "ticker_valuations"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    sector_z: Mapped[Decimal | None] = mapped_column(Numeric)
    metrics_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    sector: Mapped[str | None] = mapped_column(Text)
    sector_comparison: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric)
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    not_scored_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DailyPrice(Base):
    """Global per-ticker daily adjusted-close cache (system table, not tenant
    data). The quant engine's return-history source; one row per (ticker, date),
    shared across users. ``adj_close`` is split/dividend-adjusted — the only
    series safe for returns. Written by ``app/tools/price_store.py`` (lazy
    fill-on-miss + the daily_prices_sync job)."""

    __tablename__ = "daily_prices"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    price_date: Mapped[date] = mapped_column(Date, primary_key=True)
    adj_close: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    close: Mapped[Decimal | None] = mapped_column(Numeric)
    currency: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StockPicksRun(Base):
    """One daily Best Stocks pipeline run (global — market data, not tenant
    data; generated once per day under the owner service context and served
    to every Pro user). ``payload`` is the dashboard document; ``stats``
    carries coverage/exclusion/verification counts; ``run_id`` anchors the
    agent_runs audit trail."""

    __tablename__ = "stock_picks_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    # running | completed | partial | error
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    universe: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    stats: Mapped[dict | None] = mapped_column(JSONB)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id")
    )
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric)
    methodology_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockPickEntry(Base):
    """Track-record row: one pick, frozen at pick time. No outcome columns —
    realized returns are computed at read time against daily_prices, so the
    record is point-in-time honest with no evaluation job."""

    __tablename__ = "stock_pick_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    picks_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_picks_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    composite_score: Mapped[Decimal | None] = mapped_column(Numeric)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric)
    factors: Mapped[dict | None] = mapped_column(JSONB)
    thesis_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FundamentalsSnapshot(Base):
    """Append-only dated copy of a ticker's fundamentals payload (migration
    026) — point-in-time by construction. Never updated, never deleted; the
    screener "as it would have run on date D" resolves to the latest snapshot
    ≤ D."""

    __tablename__ = "fundamentals_snapshots"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UniverseMembership(Base):
    """Dated membership interval for a screening universe (migration 027).
    removed_at NULL = current member; closed intervals are history and are
    never deleted."""

    __tablename__ = "universe_membership"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    universe: Mapped[str] = mapped_column(Text, primary_key=True)
    added_at: Mapped[date] = mapped_column(Date, primary_key=True)
    removed_at: Mapped[date | None] = mapped_column(Date)


class FunnelEvent(Base):
    """Once-per-account funnel milestone (migration 025): signup → connected
    → trial → decision. The composite PK makes recording idempotent; anything
    repeatable belongs in agent_runs/digests, not here."""

    __tablename__ = "funnel_events"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    event: Mapped[str] = mapped_column(Text, primary_key=True)
    meta: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeletedAuthId(Base):
    """Account-deletion tombstone (migration 029). A deleted account's JWT stays
    valid until its own exp, so provisioning checks this table and refuses to
    re-create a user from a token issued at or before ``deleted_at``. A later
    sign-in carries a newer iat and clears the row."""

    __tablename__ = "deleted_auth_ids"

    auth_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NotableInvestor(Base):
    """Directory of trackable people/funds for the Notable Investor Trades
    feature (migration 034) — global, not tenant data. An insider is scoped
    per-issuer (sec_cik + company_cik) rather than per-person, since Form 4
    reporting relationships are issuer-scoped; a cross-company person view
    can be built at read time by grouping on sec_cik if ever needed."""

    __tablename__ = "notable_investors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # congress | insider | institution
    investor_type: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    chamber: Mapped[str | None] = mapped_column(Text)
    party: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    bioguide_id: Mapped[str | None] = mapped_column(Text)
    company_name: Mapped[str | None] = mapped_column(Text)
    company_cik: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    fund_name: Mapped[str | None] = mapped_column(Text)
    manager_cik: Mapped[str | None] = mapped_column(Text)
    sec_cik: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "investor_type IN ('congress','insider','institution')",
            name="notable_investors_type_check",
        ),
    )


class NotableInvestorTrade(Base):
    """One disclosed transaction/holding-line from Congress, an insider's
    Form 4, or a fund's 13F (migration 034) — global, not tenant data.
    ``raw_payload`` keeps the full original record so a mapping bug can be
    fixed and replayed without re-fetching from the network. ``ticker`` is
    nullable: a filing that fails ticker/CUSIP resolution is still stored,
    never dropped, and can be re-resolved later as the ticker cache grows."""

    __tablename__ = "notable_investor_trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    investor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notable_investors.id", ondelete="CASCADE"),
        nullable=False,
    )
    # senate_stock_watcher | house_stock_watcher | sec_form4 | sec_13f
    source: Mapped[str] = mapped_column(Text, nullable=False)
    ticker: Mapped[str | None] = mapped_column(Text)
    raw_issuer_name: Mapped[str | None] = mapped_column(Text)
    cusip: Mapped[str | None] = mapped_column(Text)
    issuer_cik: Mapped[str | None] = mapped_column(Text)
    # buy | sell | exchange | other
    transaction_type: Mapped[str] = mapped_column(Text, nullable=False)
    transaction_code: Mapped[str | None] = mapped_column(Text)
    amount_range_min: Mapped[Decimal | None] = mapped_column(Numeric)
    amount_range_max: Mapped[Decimal | None] = mapped_column(Numeric)
    shares: Mapped[Decimal | None] = mapped_column(Numeric)
    price_per_share: Mapped[Decimal | None] = mapped_column(Numeric)
    value_usd: Mapped[Decimal | None] = mapped_column(Numeric)
    transaction_date: Mapped[date | None] = mapped_column(Date)
    filed_date: Mapped[date] = mapped_column(Date, nullable=False)
    quarter_end_date: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('buy','sell','exchange','other')",
            name="notable_investor_trades_type_check",
        ),
    )


class NotableInvestorSyncState(Base):
    """Per-(source, external key) incremental sync watermark (migration 034)
    so Form 4 / 13F polling parses only new accessions each run instead of
    re-crawling a filer's full filing history."""

    __tablename__ = "notable_investor_sync_state"

    source: Mapped[str] = mapped_column(Text, primary_key=True)
    external_key: Mapped[str] = mapped_column(Text, primary_key=True)
    last_seen_at: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SecCompanyTicker(Base):
    """Cache of SEC's company_tickers.json (migration 034), refreshed weekly,
    backing the notable-trades ticker/CIK resolver with a DB lookup instead
    of a live HTTP call per filing."""

    __tablename__ = "sec_company_tickers"

    cik: Mapped[str] = mapped_column(Text, primary_key=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NotableInvestorFollow(Base):
    """A notable investor (Congress member/insider/fund) the user opted to
    follow (migration 034) — mirrors WatchlistItem's shape exactly."""

    __tablename__ = "notable_investor_follows"
    __table_args__ = (UniqueConstraint("user_id", "investor_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = _user_id_column()
    investor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notable_investors.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NotableTradeDigestMention(Base):
    """Once-per-(user, trade) digest mention marker (migration 034), same
    composite-PK idiom as FunnelEvent: a trade is a discrete historical event
    that should never be re-surfaced in a later digest once mentioned."""

    __tablename__ = "notable_trade_digest_mentions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notable_investor_trades.id", ondelete="CASCADE"),
        primary_key=True,
    )
    surfaced_on: Mapped[date] = mapped_column(Date, nullable=False)


class SchemaMigration(Base):
    """Tracks which numbered migration files have been applied."""

    __tablename__ = "schema_migrations"

    version: Mapped[str] = mapped_column(String, primary_key=True)
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
