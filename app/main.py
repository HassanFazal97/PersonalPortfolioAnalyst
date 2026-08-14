"""FastAPI app factory, routes, and scheduler startup.

Routes are added milestone by milestone. The ``Repo`` and scheduler are created
in the lifespan and stored on ``app.state`` so routes and the scheduler share
one connection pool.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from time import perf_counter
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import billing
from app.agent.anomaly.orchestrator import run_anomaly_scan, run_anomaly_scans_for_all
from app.agent.budget import Budget
from app.agent.chat_context import build_chat_context, compose_chat_system_prompt
from app.agent.deep_dive import run_deep_dive, run_deep_dives_for_all
from app.agent.digest_pipeline import run_digest_pipeline, run_digests_for_all
from app.agent.loop import run_agent
from app.agent.macro.orchestrator import run_macro_scan, run_macro_scans_for_all
from app.agent.news_refresh import refresh_news_for_user, run_news_refresh_for_all
from app.agent.picks.pipeline import run_stock_picks
from app.agent.prompts import (
    CHAT_ANALYZE_RISK_SUFFIX,
    CHAT_MEMORY_SUFFIX,
    CHAT_SYSTEM_PROMPT,
    CHAT_WEB_SEARCH_SUFFIX,
    PROMPT_VERSION,
)
from app.auth.context import set_current_user_id
from app.auth.jwt import AuthError, jwks_url_for, verify_supabase_jwt
from app.config import (
    DEFAULT_USER_ID,
    chat_run_budget,
    get_settings,
    monthly_cost_cap,
)
from app.db.repo import DeletedAccountError, Repo
from app.delivery import discord_connect, twilio_inbound, unsubscribe, verification
from app.delivery.adapters import build_adapters
from app.delivery.channels import PUSH_CHANNEL, mask_destination
from app.delivery.dispatcher import Dispatcher
from app.delivery.shortcuts import get_latest_digest
from app.integrations.snaptrade.client import SnapTradeError
from app.integrations.snaptrade.onboarding import (
    portfolio_status,
    register_snaptrade_user,
    service_for_user,
)
from app.integrations.snaptrade.sync import sync_brokerage_positions
from app.jobs import heartbeat_wrapped, job_health
from app.landing import (
    CONTACT_HTML,
    LANDING_HTML,
    METHODOLOGY_HTML,
    PRICING_HTML,
    PRIVACY_HTML,
    SAMPLE_DIGEST_HTML,
    TERMS_HTML,
    robots_txt,
    screener_html,
    sitemap_xml,
    track_record_html,
)
from app.memory import ingest as memory_ingest
from app.memory.embeddings import memory_enabled
from app.perf import authcache, snapshot
from app.plans import (
    effective_plan,
    max_digest_holdings,
    max_watchlist,
    trial_active,
    trial_decision_pending,
)
from app.profile import (
    EXPERIENCE_LEVELS,
    GOALS,
    HORIZONS,
    POSTURES,
    build_profile_context,
    derive_archetype,
    profile_from_user,
    profile_payload,
    resolve_risk_tolerance,
)
from app.quant import trackrecord
from app.scheduler import DeliveryScheduler, DigestScheduler, IntervalScheduler
from app.streaming import SENTINEL, ProgressBroker, sse_response
from app.tools import (
    fundamentals,
    logos,
    market,
    portfolio,
    portfolio_risk,
    price_store,
    symbol_search,
    universe,
    valuation_refresh,
)
from app.tools.registry import (
    CHAT_TOOLS,
    PRO_CHAT_TOOLS,
    RECALL_MEMORY_SCHEMA,
    WEB_SEARCH_TOOL,
    ToolContext,
)
from app.tools.tickers import normalize_ticker
from app.trial_notices import run_trial_notices
from app.webapp import (
    NOT_CONFIGURED_HTML,
    dashboard_page,
    deep_dives_page,
    login_page,
    onboarding_page,
    picks_page,
    reset_page,
    risk_lab_page,
    settings_page,
    stock_page,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    repo = (
        Repo(settings.database_url, ssl=settings.db_ssl)
        if settings.database_url
        else None
    )
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    app.state.anomaly_scheduler = None
    app.state.fundamentals_scheduler = None
    app.state.daily_prices_scheduler = None
    app.state.news_scheduler = None
    app.state.deep_dive_scheduler = None
    app.state.picks_sync_scheduler = None
    app.state.valuation_refresh_scheduler = None
    app.state.picks_scheduler = None
    app.state.trial_notices_scheduler = None
    app.state.delivery_scheduler = None
    app.state.quote_warm_scheduler = None
    app.state.positions_refresh_scheduler = None
    # Which channels this deployment can send (drives verification + UI).
    app.state.delivery_adapters = build_adapters(settings)

    if not (settings.supabase_url or settings.supabase_jwt_secret):
        logging.getLogger(__name__).warning(
            "Supabase auth is not configured — running in single-owner mode. "
            "Browser sign-in is disabled; only API_TOKEN auth works. "
            "Do not expose this deployment publicly in this state."
        )

    if repo is not None:
        async def _run_digest() -> None:
            await run_digests_for_all(repo)
            snapshot.store.clear()

        scheduler = DigestScheduler(
            heartbeat_wrapped("morning_digest", repo, _run_digest),
            cron=settings.digest_cron,
            timezone=settings.tz,
            misfire_grace_seconds=settings.digest_misfire_grace_seconds,
        )
        scheduler.start()
        app.state.scheduler = scheduler

        if settings.macro_scan_interval_minutes > 0:
            async def _run_macro() -> None:
                await run_macro_scans_for_all(repo)
                snapshot.store.clear()

            macro_scheduler = IntervalScheduler(
                heartbeat_wrapped("macro_scan", repo, _run_macro),
                minutes=settings.macro_scan_interval_minutes,
                timezone=settings.tz,
            )
            macro_scheduler.start()
            app.state.macro_scheduler = macro_scheduler

        if settings.anomaly_scan_cron:
            async def _run_anomaly() -> None:
                await run_anomaly_scans_for_all(repo)
                snapshot.store.clear()

            anomaly_scheduler = DigestScheduler(
                heartbeat_wrapped("anomaly_scan", repo, _run_anomaly),
                cron=settings.anomaly_scan_cron,
                timezone=settings.tz,
                job_id="anomaly_scan",
                misfire_grace_seconds=settings.digest_misfire_grace_seconds,
            )
            anomaly_scheduler.start()
            app.state.anomaly_scheduler = anomaly_scheduler

        if settings.fundamentals_refresh_cron:
            async def _run_fundamentals_refresh() -> None:
                await fundamentals.run_fundamentals_refresh(repo, settings)

            fundamentals_scheduler = DigestScheduler(
                heartbeat_wrapped("fundamentals_refresh", repo, _run_fundamentals_refresh),
                cron=settings.fundamentals_refresh_cron,
                timezone=settings.tz,
                job_id="fundamentals_refresh",
                misfire_grace_seconds=settings.digest_misfire_grace_seconds,
            )
            fundamentals_scheduler.start()
            app.state.fundamentals_scheduler = fundamentals_scheduler

        if settings.daily_prices_cron:
            async def _run_daily_prices_sync() -> None:
                await price_store.run_daily_prices_sync(repo, settings)

            daily_prices_scheduler = DigestScheduler(
                heartbeat_wrapped("daily_prices_sync", repo, _run_daily_prices_sync),
                cron=settings.daily_prices_cron,
                timezone=settings.tz,
                job_id="daily_prices_sync",
                misfire_grace_seconds=settings.digest_misfire_grace_seconds,
            )
            daily_prices_scheduler.start()
            app.state.daily_prices_scheduler = daily_prices_scheduler

        if settings.news_refresh_cron:
            async def _run_news_refresh() -> None:
                await run_news_refresh_for_all(repo)
                snapshot.store.clear()

            news_scheduler = DigestScheduler(
                heartbeat_wrapped("news_refresh", repo, _run_news_refresh),
                cron=settings.news_refresh_cron,
                timezone=settings.tz,
                job_id="news_refresh",
                misfire_grace_seconds=settings.digest_misfire_grace_seconds,
            )
            news_scheduler.start()
            app.state.news_scheduler = news_scheduler

        if settings.deep_dive_cron:
            async def _run_deep_dives() -> None:
                await run_deep_dives_for_all(repo)

            deep_dive_scheduler = DigestScheduler(
                heartbeat_wrapped("deep_dive", repo, _run_deep_dives),
                cron=settings.deep_dive_cron,
                timezone=settings.tz,
                job_id="deep_dive",
                misfire_grace_seconds=settings.digest_misfire_grace_seconds,
            )
            deep_dive_scheduler.start()
            app.state.deep_dive_scheduler = deep_dive_scheduler

        if settings.picks_sync_cron:
            async def _run_picks_sync() -> None:
                await universe.run_universe_sync(repo, settings)

            picks_sync_scheduler = DigestScheduler(
                heartbeat_wrapped("picks_sync", repo, _run_picks_sync),
                cron=settings.picks_sync_cron,
                timezone=settings.tz,
                job_id="picks_sync",
                misfire_grace_seconds=settings.digest_misfire_grace_seconds,
            )
            picks_sync_scheduler.start()
            app.state.picks_sync_scheduler = picks_sync_scheduler

        if settings.valuation_refresh_cron:
            async def _run_valuation_refresh() -> None:
                await valuation_refresh.run_valuation_refresh(repo, settings)

            valuation_refresh_scheduler = DigestScheduler(
                heartbeat_wrapped("valuation_refresh", repo, _run_valuation_refresh),
                cron=settings.valuation_refresh_cron,
                timezone=settings.tz,
                job_id="valuation_refresh",
                misfire_grace_seconds=settings.digest_misfire_grace_seconds,
            )
            valuation_refresh_scheduler.start()
            app.state.valuation_refresh_scheduler = valuation_refresh_scheduler

        if settings.picks_cron:
            async def _run_picks() -> None:
                await run_stock_picks(repo)
                # New entries exist; the public proof page should show them.
                _track_record_cache.clear()

            picks_scheduler = DigestScheduler(
                heartbeat_wrapped("picks_run", repo, _run_picks),
                cron=settings.picks_cron,
                timezone=settings.tz,
                job_id="picks_run",
                misfire_grace_seconds=settings.digest_misfire_grace_seconds,
            )
            picks_scheduler.start()
            app.state.picks_scheduler = picks_scheduler

        if settings.trial_notices_cron:
            async def _run_trial_notices() -> None:
                await run_trial_notices(repo, get_settings())

            trial_notices_scheduler = DigestScheduler(
                heartbeat_wrapped("trial_notices", repo, _run_trial_notices),
                cron=settings.trial_notices_cron,
                timezone=settings.tz,
                job_id="trial_notices",
                misfire_grace_seconds=settings.digest_misfire_grace_seconds,
            )
            trial_notices_scheduler.start()
            app.state.trial_notices_scheduler = trial_notices_scheduler

        if settings.quote_warm_interval_seconds > 0:
            async def _warm_builder(user_id: uuid.UUID, name: str):
                set_current_user_id(user_id)
                if name == "portfolio":
                    ctx = ToolContext(
                        settings=get_settings(), repo=repo, user_id=user_id
                    )
                    return await portfolio.get_portfolio({}, ctx)
                if name == "watchlist":
                    return await _watchlist_payload(repo, user_id)
                raise ValueError(f"unwarmable section {name!r}")

            async def _run_quote_warm() -> None:
                # Keep quotes hot for anyone with a recent dashboard touch so
                # their next bootstrap serves fresh sections instantly. Off
                # hours the close doesn't move; skip entirely.
                if not snapshot.market_hours_now():
                    return
                for uid in snapshot.store.active_users(30 * 60):
                    snapshot.store.refresh(
                        uid, ["portfolio", "watchlist"], _warm_builder
                    )

            quote_warm_scheduler = DeliveryScheduler(
                heartbeat_wrapped("quote_warm", repo, _run_quote_warm),
                seconds=settings.quote_warm_interval_seconds,
                timezone=settings.tz,
                job_id="quote_warm",
            )
            quote_warm_scheduler.start()
            app.state.quote_warm_scheduler = quote_warm_scheduler

        if settings.positions_refresh_interval_minutes > 0:
            async def _run_positions_refresh() -> None:
                """Scheduled brokerage re-sync for recently-active connected
                users — positions previously only updated on manual sync."""
                if not snapshot.market_hours_now():
                    return
                for uid in snapshot.store.active_users(24 * 3600):
                    set_current_user_id(uid)
                    if await repo.get_snaptrade_credentials(uid) is None:
                        continue
                    try:
                        await sync_brokerage_positions(repo, user_id=uid)
                        snapshot.store.invalidate(uid, "portfolio", "status", "me")
                    except Exception as exc:
                        logging.getLogger(__name__).warning(
                            "positions refresh for %s failed: %s", uid, exc
                        )
                    # Serial with a pause: SnapTrade rate limits are per-key.
                    await asyncio.sleep(2)

            positions_refresh_scheduler = IntervalScheduler(
                heartbeat_wrapped("positions_refresh", repo, _run_positions_refresh),
                minutes=settings.positions_refresh_interval_minutes,
                timezone=settings.tz,
                job_id="positions_refresh",
            )
            positions_refresh_scheduler.start()
            app.state.positions_refresh_scheduler = positions_refresh_scheduler

        if settings.delivery_interval_seconds > 0:
            dispatcher = Dispatcher(
                repo,
                app.state.delivery_adapters,
                max_attempts=settings.delivery_max_attempts,
                unsubscribe_url_for=lambda uid, ch: unsubscribe.unsubscribe_url(
                    get_settings(), uid, ch
                ),
            )
            delivery_scheduler = DeliveryScheduler(
                heartbeat_wrapped("delivery_dispatch", repo, dispatcher.tick),
                seconds=settings.delivery_interval_seconds,
                timezone=settings.tz,
            )
            delivery_scheduler.start()
            app.state.delivery_scheduler = delivery_scheduler

    try:
        yield
    finally:
        if app.state.trial_notices_scheduler is not None:
            app.state.trial_notices_scheduler.shutdown()
        if app.state.positions_refresh_scheduler is not None:
            app.state.positions_refresh_scheduler.shutdown()
        if app.state.quote_warm_scheduler is not None:
            app.state.quote_warm_scheduler.shutdown()
        if app.state.delivery_scheduler is not None:
            app.state.delivery_scheduler.shutdown()
        if app.state.picks_scheduler is not None:
            app.state.picks_scheduler.shutdown()
        if app.state.picks_sync_scheduler is not None:
            app.state.picks_sync_scheduler.shutdown()
        if app.state.valuation_refresh_scheduler is not None:
            app.state.valuation_refresh_scheduler.shutdown()
        if app.state.deep_dive_scheduler is not None:
            app.state.deep_dive_scheduler.shutdown()
        if app.state.news_scheduler is not None:
            app.state.news_scheduler.shutdown()
        if app.state.fundamentals_scheduler is not None:
            app.state.fundamentals_scheduler.shutdown()
        if app.state.daily_prices_scheduler is not None:
            app.state.daily_prices_scheduler.shutdown()
        if app.state.anomaly_scheduler is not None:
            app.state.anomaly_scheduler.shutdown()
        if app.state.macro_scheduler is not None:
            app.state.macro_scheduler.shutdown()
        if app.state.scheduler is not None:
            app.state.scheduler.shutdown()
        if repo is not None:
            await repo.dispose()


class ChatRequest(BaseModel):
    message: str


class PreferencesRequest(BaseModel):
    timezone: str | None = None
    digest_send_time: str | None = None  # "HH:MM"
    digest_enabled: bool | None = None
    digest_tickers: list[str] | None = None


class ProfileRequest(BaseModel):
    """Investor-profile answers from onboarding (all values enum-validated
    against app/profile.py — no free text ever reaches prompts)."""

    experience: str | None = None
    goals: list[str] = []
    horizon: str | None = None
    risk_tolerance: int | None = None  # 1-10 (explicit wins over posture)
    chosen_posture: str | None = None  # 'defensive' | 'current' | 'aggressive'


class ChannelRegisterRequest(BaseModel):
    channel: str  # 'sms' | 'email' | 'discord'
    destination: str
    consent: bool = False  # required True for sms (TCPA opt-in)


# Notification kinds a device can subscribe to. These are the `kind` values
# the fan-out matches against, so they must stay in step with the kinds passed
# to enqueue_outbound at its call sites.
_PUSH_KINDS: tuple[str, ...] = ("digest", "alert", "deep_dive", "trial")


class DeviceRegisterRequest(BaseModel):
    expo_token: str
    platform: str = "ios"
    kinds: list[str] = ["digest", "alert", "deep_dive"]


class DeviceUnregisterRequest(BaseModel):
    expo_token: str


class DeviceKindsRequest(BaseModel):
    kinds: list[str]


class ChannelVerifyRequest(BaseModel):
    channel: str
    code: str


class PreferredChannelRequest(BaseModel):
    channel: str


class CheckoutRequest(BaseModel):
    interval: str = "monthly"  # 'monthly' | 'annual'


class ManualPositionIn(BaseModel):
    ticker: str
    quantity: float


class ManualPortfolioRequest(BaseModel):
    """Typed holdings for users who won't link a brokerage on day one."""

    positions: list[ManualPositionIn]


_bearer = HTTPBearer(auto_error=False)

# Exempt from bearer auth so platform liveness probes and uptime pingers — which
# cannot attach the token — can reach it. /health returns no sensitive data.
# Every other route stays authed-by-default via the app-level dependency.
_AUTH_EXEMPT_PATHS = {
    "/",
    "/health",
    "/robots.txt",
    "/sitemap.xml",
    "/contact",
    "/privacy",
    "/terms",
    "/pricing",
    # Public proof surfaces: the picks track record (page + JSON it reads),
    # a sample digest, and the methodology page. Global, non-user data — the
    # marketing site's evidence.
    "/track-record",
    "/sample-digest",
    "/methodology",
    "/stocks/picks/track-record",
    # The valuation grid: the no-signup browse hook (ticker/price/verdict for
    # the whole tracked universe), same posture as the track record above —
    # global market data, not user data. Deeper evidence stays Pro-gated on
    # the per-ticker page, not here.
    "/screener",
    "/stocks/valuations",
    # The web app pages are static HTML shells; the browser authenticates the
    # API calls it makes from them with a Supabase JWT.
    "/app",
    "/app/onboarding",
    "/app/dashboard",
    "/app/risk",
    "/app/picks",
    "/app/deep-dives",
    "/app/settings",
    "/app/settings/delivery",
    "/app/reset",
    # Twilio cannot attach our bearer token; the route validates
    # X-Twilio-Signature instead.
    "/webhooks/twilio/sms",
    # Stripe cannot either; the route verifies Stripe-Signature instead.
    "/webhooks/stripe",
    # Email unsubscribe links carry their own signed token.
    "/unsubscribe",
    # Discord's OAuth redirect is a bare browser GET; the signed ``state``
    # (minted by connect-url for the signed-in user) is the auth.
    "/integrations/discord/callback",
}

_DISCORD_CALLBACK_PATH = "/integrations/discord/callback"

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)


async def require_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Resolve the caller to a user and bind it for the request.

    Two accepted credentials:
      1. the static service/owner token (``API_TOKEN``) → acts as the owner;
         used by internal callers (cron, Mac worker) and single-user mode.
      2. a Supabase Auth JWT (when ``SUPABASE_JWT_SECRET`` is set) → the
         per-user identity, provisioned on first sight.
    The resolved user_id is stashed on the request and in the ContextVar the DB
    layer reads to scope RLS."""
    # /app/stock/{ticker} is dynamic, so it can't live in the exact-match set.
    # Like the other /app shells it's static HTML; the API calls it makes are
    # what carry the Supabase JWT.
    if request.url.path in _AUTH_EXEMPT_PATHS or request.url.path.startswith(
        "/app/stock/"
    ):
        return
    settings = get_settings()
    supplied = creds.credentials if creds and creds.scheme.lower() == "bearer" else ""
    if not supplied:
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")

    # 1) Service/owner static token.
    if settings.api_token and hmac.compare_digest(supplied, settings.api_token):
        _bind_user(request, _OWNER_USER_ID)
        return

    # 2) Supabase per-user JWT — asymmetric (JWKS) with HS256 legacy fallback.
    if settings.supabase_url or settings.supabase_jwt_secret:
        # Hot path: a token verifies once, then its claims are served from
        # the in-process cache until the token's own exp (~1h). Likewise the
        # auth-uid → user-id mapping is insert-only, so after the first
        # provisioning query the DB is skipped entirely (app/perf/authcache).
        cached = authcache.get_verified(supplied)
        issued_at: datetime | None = None
        if cached is not None:
            auth_id, email = cached
        else:
            jwks_url = (
                jwks_url_for(settings.supabase_url) if settings.supabase_url else None
            )
            try:
                # Verification (incl. a possible blocking JWKS fetch) runs off-loop.
                claims = await asyncio.to_thread(
                    verify_supabase_jwt,
                    supplied,
                    settings.supabase_jwt_secret or None,
                    jwks_url=jwks_url,
                    audience=settings.supabase_jwt_aud,
                )
                auth_id = uuid.UUID(str(claims["sub"]))
            except (AuthError, ValueError) as exc:
                raise HTTPException(status_code=401, detail="invalid token") from exc
            email = claims.get("email")
            raw_iat = claims.get("iat")
            if raw_iat is not None:
                issued_at = datetime.fromtimestamp(float(raw_iat), tz=timezone.utc)
            authcache.put_verified(
                supplied, auth_id, email, float(claims.get("exp", 0))
            )
        user_id = authcache.get_user_id(auth_id)
        if user_id is None:
            repo = _require_repo(request.app)
            try:
                user_id = await repo.get_or_create_user(
                    auth_id=auth_id,
                    email=email,
                    trial_days=settings.trial_days,
                    issued_at=issued_at,
                )
            except DeletedAccountError as exc:
                # The signature is genuine but the account is gone, and this
                # token predates the deletion — provisioning a replacement would
                # silently resurrect it (migration 029).
                raise HTTPException(
                    status_code=401, detail="account deleted"
                ) from exc
            authcache.put_user_id(auth_id, user_id)
        _bind_user(request, user_id)
        return

    raise HTTPException(status_code=401, detail="invalid or missing bearer token")


def _bind_user(request: Request, user_id: uuid.UUID) -> None:
    request.state.user_id = user_id
    set_current_user_id(user_id)


def _user_id(request: Request) -> uuid.UUID:
    return getattr(request.state, "user_id", _OWNER_USER_ID)


def _require_repo(app: FastAPI) -> Repo:
    repo: Repo | None = app.state.repo
    if repo is None:
        raise HTTPException(status_code=503, detail="database not configured")
    return repo


# Tickers arrive in URL paths on the stock endpoints/pages; anything outside
# Yahoo's symbol alphabet is rejected before it reaches yfinance or markup.
_TICKER_PATH_RE = re.compile(r"^[A-Z0-9.\-^=]{1,12}$")


def _validated_ticker(raw: str) -> str:
    try:
        ticker = normalize_ticker(raw)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="unknown ticker") from exc
    if not _TICKER_PATH_RE.fullmatch(ticker):
        raise HTTPException(status_code=404, detail="unknown ticker")
    return ticker


def _fmt_time(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value[:5]
    return value.strftime("%H:%M")


# The track record's benchmark is SPY's dividend-adjusted close — a total-return
# S&P 500 proxy. Picks are measured on dividend-adjusted closes, so a price-only
# index (^GSPC) would structurally flatter them by the S&P's dividend yield.
_TRACK_BENCHMARK_TICKER = "SPY"
# Public, unauthenticated, and fetched by the homepage stat strip on every
# load: serve a cached payload rather than re-querying per request.
_TRACK_RECORD_TTL_SECONDS = 900.0
_track_record_cache: dict[int, tuple[float, dict]] = {}


async def _valuations_payload(repo: Repo) -> dict:
    """The valuation grid document: ticker/name/sector/cap/price/verdict for
    the whole tracked universe, from the ``ticker_valuations`` cache written
    nightly by app/tools/valuation_refresh.py. Shared by the public
    /stocks/valuations JSON route and the public /screener page — same flat
    DB read either way, no live scoring in the request path."""
    rows = await repo.get_ticker_valuations()
    as_of = max((r.as_of for r in rows.values()), default=None)
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "universe": universe.universe_snapshot(get_settings().picks_universe_limit),
        "rows": [
            {
                "ticker": t,
                "name": r.name,
                "sector": r.sector,
                "market_cap": float(r.market_cap) if r.market_cap is not None else None,
                "last_price": float(r.last_price) if r.last_price is not None else None,
                "verdict": r.verdict,
            }
            for t, r in sorted(rows.items())
        ],
    }


def _close_before(rows: list[tuple[date, float]], d: date) -> float | None:
    """Last close strictly before ``d`` — the bar entry_price was frozen at."""
    prior = None
    for row_date, close in rows:
        if row_date >= d:
            break
        prior = close
    return prior


async def _track_record_payload(repo: Repo, days: int = 90) -> dict:
    """Realized performance of past picks, computed at read time.

    Every return is a ratio of dividend/split-adjusted closes drawn from the
    *same* stored series: the last bar before publication (the bar the frozen
    entry_price displays) to the latest bar. Comparing today's series against
    a price frozen months ago would drift whenever yfinance re-adjusts history
    — a split would read as a fake −50%. The benchmark is SPY total-return
    over the identical span. Global data — shared by the public JSON route
    and the public /track-record page."""
    days = max(7, min(days, 365))
    cached = _track_record_cache.get(days)
    if cached is not None and perf_counter() - cached[0] < _TRACK_RECORD_TTL_SECONDS:
        return cached[1]

    since = date.today() - timedelta(days=days)
    entries = await repo.list_pick_entries(since=since)
    if not entries:
        payload = {"available": False, "entries": [], "summary": None}
        _track_record_cache[days] = (perf_counter(), payload)
        return payload

    tickers = sorted({e.ticker for e in entries})
    # One query for every pick series; the extra week covers the first
    # entries' prior close. The benchmark reads through the price store
    # (fill-on-miss) so it works even before the first nightly sync.
    series = await repo.get_daily_prices_bulk(
        tickers, since=since - timedelta(days=7)
    )
    by_ticker = {
        t: [(r.price_date, float(r.adj_close)) for r in rows]
        for t, rows in series.items()
    }
    bench_by_date = [
        (date.fromisoformat(r["date"]), float(r["adj_close"]))
        for r in await price_store.get_adjusted_closes(
            repo, _TRACK_BENCHMARK_TICKER, days + 14
        )
    ]

    def bench_between(start: date, end: date) -> float | None:
        """SPY total return from its last close before ``start`` to its last
        close on/before ``end`` — the pick's exact measurement span."""
        b0 = _close_before(bench_by_date, start)
        b1 = None
        for row_date, close in bench_by_date:
            if row_date > end:
                break
            b1 = close
        if not b0 or b1 is None:
            return None
        return (b1 / b0 - 1) * 100

    out = []
    returns: list[float] = []
    beats = 0
    compared = 0
    for e in entries:
        rows = by_ticker.get(e.ticker) or []
        entry_price = float(e.entry_price) if e.entry_price is not None else None
        row: dict = {
            "ticker": e.ticker,
            "run_date": e.run_date.isoformat(),
            "rank": e.rank,
            "confidence": float(e.confidence) if e.confidence is not None else None,
            "entry_price": entry_price,
        }
        entry_close = _close_before(rows, e.run_date)
        if rows and entry_close:
            as_of_date, last_close = rows[-1]
            ret = (last_close / entry_close - 1) * 100
            row["return_pct"] = round(ret, 2)
            row["as_of"] = as_of_date.isoformat()
            returns.append(ret)
            bench_ret = bench_between(e.run_date, as_of_date)
            if bench_ret is not None:
                row["benchmark_return_pct"] = round(bench_ret, 2)
                compared += 1
                if ret > bench_ret:
                    beats += 1
        out.append(row)
    summary = {
        "picks": len(out),
        "measured": len(returns),
        "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else None,
        "beat_benchmark": beats,
        "compared": compared,
        "hit_rate_pct": round(beats / compared * 100, 1) if compared else None,
    }
    # Cohort view: the per-entry list double-counts persistent picks (a name
    # picked 30 days running appears 30 times), so the honest headline stats
    # are dated cohorts at fully-elapsed horizons plus a "top-5 bought each
    # run" simulated portfolio — pure math in app/quant/trackrecord.py.
    cohort_inputs = [
        {"run_date": e.run_date, "ticker": e.ticker, "rank": e.rank}
        for e in entries
        if e.rank is not None
    ]
    payload = {
        "available": True,
        "entries": out,
        "summary": summary,
        "cohorts": trackrecord.cohort_returns(
            cohort_inputs, by_ticker, bench_by_date
        ),
        "simulated": trackrecord.simulate_top_picks(
            cohort_inputs, by_ticker, bench_by_date
        ),
    }
    _track_record_cache[days] = (perf_counter(), payload)
    return payload


def _trial_payload(user) -> dict:
    """Trial state for the UI: active countdown, or the paused decision gate."""
    ends = getattr(user, "trial_ends_at", None) if user is not None else None
    return {
        "active": trial_active(user),
        "ends_at": ends.isoformat() if ends else None,
        "decision_pending": trial_decision_pending(user),
    }


def _billing_payload(settings, user) -> dict:
    """Billing state for the settings UI. Rendered from the mirrored columns
    so no page load ever waits on a Stripe round-trip."""
    period_end = getattr(user, "stripe_current_period_end", None) if user else None
    return {
        "enabled": billing.billing_enabled(settings),
        "annual_available": bool(settings.stripe_price_pro_annual),
        "has_billing_account": bool(getattr(user, "stripe_customer_id", None)),
        "cancel_at_period_end": bool(
            getattr(user, "stripe_cancel_at_period_end", False)
        ),
        "current_period_end": period_end.isoformat() if period_end else None,
    }


async def _me_payload(repo: Repo, user_id: uuid.UUID) -> dict:
    settings = get_settings()
    user = await repo.get_user(user_id)
    is_owner = user_id == _OWNER_USER_ID
    if user is None:
        return {
            "user_id": str(user_id),
            "email": None,
            "plan": "pro" if is_owner else "free",
            "effective_plan": "pro" if is_owner else "free",
            "timezone": "America/Toronto",
            "digest_send_time": "09:00",
            "digest_enabled": True,
            "preferred_channel": None,
            "digest_tickers": [],
            "digest_tickers_limit": None if is_owner else settings.free_max_digest_holdings,
            "digest_tickers_editable": False,
            "is_owner": is_owner,
            "profile": profile_payload(None),
            "trial": _trial_payload(None),
            "billing": _billing_payload(settings, None),
            "chat_quota": await _chat_quota_payload(repo, user_id, "free", settings),
        }
    # Limits track the effective plan (an active trial is Pro); "plan" stays
    # the stored paid flag so the UI can tell trial apart from subscription.
    plan = effective_plan(user)
    cap = max_digest_holdings(plan, settings)
    positions = await repo.list_positions(user_id=user_id)
    unique_tickers = sorted({p.ticker for p in positions})
    # Read off the row already in hand (repo.get_digest_tickers would
    # re-fetch the same user for one column).
    digest_tickers = [str(t) for t in (getattr(user, "digest_tickers", None) or [])]
    editable = (
        plan == "free"
        and cap is not None
        and len(unique_tickers) > cap
    )
    return {
        "user_id": str(user_id),
        "email": user.email,
        "plan": user.plan,
        "effective_plan": plan,
        "timezone": user.timezone,
        "digest_send_time": _fmt_time(user.digest_send_time),
        "digest_enabled": user.digest_enabled,
        "preferred_channel": user.preferred_channel,
        "digest_tickers": digest_tickers,
        "digest_tickers_limit": cap,
        "digest_tickers_editable": editable,
        "is_owner": is_owner,
        "profile": profile_payload(user),
        "trial": _trial_payload(user),
        "billing": _billing_payload(settings, user),
        "chat_quota": await _chat_quota_payload(repo, user_id, plan, settings),
    }


async def _validate_digest_tickers(
    repo: Repo, user_id: uuid.UUID, tickers: list[str]
) -> list[str]:
    """Validate and normalize a digest watchlist update."""
    settings = get_settings()
    user = await repo.get_user(user_id)
    plan = effective_plan(user)
    if plan == "pro":
        return []
    cap = max_digest_holdings(plan, settings)
    if cap is None:
        return []
    if len(tickers) > cap:
        raise HTTPException(
            status_code=400,
            detail=f"Free plan allows at most {cap} digest holdings.",
        )
    positions = await repo.list_positions(user_id=user_id)
    owned = {p.ticker for p in positions}
    normalized: list[str] = []
    for t in tickers:
        if t not in owned:
            raise HTTPException(
                status_code=400,
                detail=f"Ticker {t} is not in your portfolio.",
            )
        if t not in normalized:
            normalized.append(t)
    return normalized


def _is_real_instrument(data: dict | None, last_price) -> bool:
    """Whether a ticker resolved to something real. Yahoo's ``.info`` for a
    garbage symbol doesn't fail — it returns a minimal dict the fundamentals
    normalizer expands into an all-None skeleton — so a truthy ``data`` alone
    proves nothing; require an actual signal (quote type, name, or a price)."""
    if last_price is not None:
        return True
    if not data:
        return False
    return bool(
        data.get("quote_type") or (data.get("profile") or {}).get("name")
    )


async def _watchlist_payload(repo: Repo, user_id: uuid.UUID) -> dict:
    """The user's watchlist with live quotes plus the plan-cap quota block
    (shape mirrors the chat quota: limit/used/remaining)."""
    settings = get_settings()
    is_owner = user_id == _OWNER_USER_ID
    if is_owner:
        cap = None
    else:
        user = await repo.get_user(user_id)
        cap = max_watchlist(effective_plan(user), settings)
    items = await repo.list_watchlist(user_id)
    positions = await repo.list_positions(user_id=user_id)
    held = {p.ticker for p in positions}
    quotes: dict[str, dict] = {}
    if items:
        result = await market.get_quote({"tickers": [i.ticker for i in items]})
        quotes = {q["ticker"]: q for q in result.get("quotes", [])}
    used = len(items)
    return {
        "items": [
            {
                "ticker": i.ticker,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "last_price": quotes.get(i.ticker, {}).get("last_price"),
                "day_change_pct": quotes.get(i.ticker, {}).get("day_change_pct"),
                "held": i.ticker in held,
            }
            for i in items
        ],
        "limit": cap,
        "used": used,
        # A Pro→Free downgrade can leave used > cap; clamp instead of going negative.
        "remaining": None if cap is None else max(0, cap - used),
    }


async def _delete_supabase_auth_user(settings, auth_id: uuid.UUID | None) -> bool:
    """Delete the Supabase auth user via the admin API (service-role key).

    Best-effort: returns False when the key/URL/auth_id is missing or the call
    fails — the caller has already removed all app data either way."""
    if not (settings.supabase_url and settings.supabase_service_role_key and auth_id):
        return False
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{auth_id}"
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(url, headers=headers)
    except httpx.HTTPError:
        return False
    # 404 = already gone, which is the outcome we wanted.
    return resp.status_code < 400 or resp.status_code == 404


def _chat_window(plan: str) -> tuple[str, timedelta]:
    """Rolling quota window for a plan: Pro counts per 24h, Free per 7 days."""
    if plan == "pro":
        return "day", timedelta(hours=24)
    return "week", timedelta(days=7)


def _chat_limit(plan: str, settings) -> int:
    return (
        settings.pro_daily_chat_limit
        if plan == "pro"
        else settings.free_weekly_chat_limit
    )


async def _chat_quota_payload(
    repo: Repo, user_id: uuid.UUID, plan: str, settings
) -> dict | None:
    """The user's chat-question quota state (None for the exempt owner)."""
    if user_id == _OWNER_USER_ID:
        return None
    window, span = _chat_window(plan)
    used, oldest = await repo.chat_usage_since(
        user_id, datetime.now(timezone.utc) - span
    )
    # The oldest counted question leaving the window is when a slot frees up.
    resets_at = (oldest + span).isoformat() if oldest is not None else None
    return {
        "limit": _chat_limit(plan, settings),
        "used": used,
        "remaining": max(0, _chat_limit(plan, settings) - used),
        "window": window,
        "resets_at": resets_at,
    }


def _user_tz(user) -> ZoneInfo:
    try:
        return ZoneInfo(getattr(user, "timezone", None) or "America/Toronto")
    except Exception:
        return ZoneInfo("UTC")


# Prior turns are replayed verbatim into the prompt; cap each message so one
# long answer doesn't dominate the context window.
_CHAT_HISTORY_MSG_CHARS = 1200


async def _chat_history_messages(
    repo: Repo, user_id: uuid.UUID, settings
) -> list[dict]:
    """Up to chat_history_turns prior Q&A pairs, oldest first, as plain
    user/assistant text messages (no tool traces). Runs that errored or never
    produced an answer are skipped so roles stay strictly paired."""
    turns = settings.chat_history_turns
    if turns <= 0:
        return []
    # Over-fetch: errored/answerless runs are skipped below, and they must not
    # crowd usable turns out of the fixed-size window.
    runs = await repo.list_chat_runs(user_id, limit=turns * 2)
    pairs: list[list[dict]] = []
    for r in runs:  # newest first
        question = getattr(r, "user_message", None)
        answer = getattr(r, "final_answer", None)
        if getattr(r, "status", None) == "error" or not question or not answer:
            continue
        pairs.append([
            {"role": "user", "content": question[:_CHAT_HISTORY_MSG_CHARS]},
            {"role": "assistant", "content": answer[:_CHAT_HISTORY_MSG_CHARS]},
        ])
        if len(pairs) == turns:
            break
    # Chronological order for the prompt: oldest pair first.
    return [msg for pair in reversed(pairs) for msg in pair]


async def _enforce_usage_limits(repo: Repo, user_id: uuid.UUID, settings) -> None:
    """Guard a chat against the plan's rolling question quota (Free 3/week,
    Pro 10/day) and the monthly fair-use compute cap. Owner/service token is
    exempt. Raises 402 when over."""
    if user_id == _OWNER_USER_ID:
        return
    user = await repo.get_user(user_id)
    # An active no-card trial counts as Pro everywhere, quotas included.
    plan = effective_plan(user)
    if await repo.monthly_cost_usd(user_id) >= monthly_cost_cap(plan, settings):
        upsell = "" if plan == "pro" else " Upgrade to Pro for more headroom."
        raise HTTPException(
            status_code=402,
            detail=(
                "You've reached this month's fair-use compute cap. It resets "
                f"at the start of next month.{upsell}"
            ),
        )
    window, span = _chat_window(plan)
    now = datetime.now(timezone.utc)
    used, oldest = await repo.chat_usage_since(user_id, now - span)
    limit = _chat_limit(plan, settings)
    if used < limit:
        return
    unlocks = (oldest or now) + span
    local = unlocks.astimezone(_user_tz(user))
    if plan == "pro":
        raise HTTPException(
            status_code=402,
            detail=(
                f"Daily limit reached ({limit} questions per day on Pro). "
                f"Your next question unlocks at {local:%-I:%M %p} ({local:%Z})."
            ),
        )
    raise HTTPException(
        status_code=402,
        detail=(
            f"You've used your {limit} free questions this week. Your next "
            f"question unlocks {local:%a %b %-d}. Upgrade to Pro for "
            f"{settings.pro_daily_chat_limit} per day."
        ),
    )


async def _prepare_chat(
    repo: Repo, user_id: uuid.UUID, settings
) -> tuple[str, Budget, ToolContext, list[dict], str, list[dict]]:
    """Everything ``/chat`` and ``/chat/stream`` share — plan resolution,
    budget, tool context, portfolio context, history, and tool roster — in one
    place so the two endpoints cannot drift. Returns
    (plan, budget, ctx, tools, system_prompt, history)."""
    user = await repo.get_user(user_id)
    plan = effective_plan(user)
    if user_id == _OWNER_USER_ID:
        max_cost = settings.chat_max_cost_usd
    else:
        max_cost = chat_run_budget(plan, settings)
    budget = Budget(
        max_iterations=settings.chat_max_iterations,
        max_cost_usd=max_cost,
        model=settings.model,
    )
    tz = getattr(user, "timezone", None) or settings.tz
    ctx = ToolContext(settings=settings, repo=repo, user_id=user_id, timezone=tz)
    context = await build_chat_context(ctx, tz=tz)
    history = await _chat_history_messages(repo, user_id, settings)
    # Server-side web search is a Pro perk: its per-search cost doesn't fit
    # the Free tier's economics.
    base_prompt = CHAT_SYSTEM_PROMPT
    tools = CHAT_TOOLS
    if plan == "pro" or user_id == _OWNER_USER_ID:
        base_prompt = (
            CHAT_SYSTEM_PROMPT + CHAT_ANALYZE_RISK_SUFFIX + CHAT_WEB_SEARCH_SUFFIX
        )
        tools = [*CHAT_TOOLS, *PRO_CHAT_TOOLS, WEB_SEARCH_TOOL]
    # Semantic memory is for all plans (embedding cost is negligible next to
    # the model spend, and quotas already bound chat volume); offered only
    # when the deployment has an embedding key.
    if memory_enabled(settings):
        base_prompt = base_prompt + CHAT_MEMORY_SUFFIX
        tools = [*tools, RECALL_MEMORY_SCHEMA]
    profile_block = build_profile_context(profile_from_user(user))
    system_prompt = compose_chat_system_prompt(
        base_prompt, context, profile_block=profile_block
    )
    return plan, budget, ctx, tools, system_prompt, history


def _ingest_chat_memory(repo: Repo, user_id: uuid.UUID, question: str, result) -> None:
    """Fire-and-forget: embed a finished chat Q&A into semantic memory.
    No-op when memory is disabled or the run produced no answer."""
    if not memory_enabled(get_settings()):
        return
    if result.status == "error" or not result.answer:
        return

    async def _embed() -> None:
        positions = await repo.list_positions(user_id=user_id)
        await memory_ingest.embed_chat_run(
            repo,
            user_id=user_id,
            run_id=result.run_id,
            question=question,
            answer=result.answer,
            created_at=datetime.now(timezone.utc),
            holdings_tickers=sorted({p.ticker for p in positions}),
        )

    memory_ingest.schedule(_embed())


async def _run_chat_turn(
    repo: Repo,
    *,
    user_id: uuid.UUID,
    message: str,
    settings,
    prepared: tuple[str, Budget, ToolContext, list[dict], str, list[dict]],
    on_event=None,
    run_id: uuid.UUID | None = None,
) -> dict:
    """One chat turn, end to end: run the agent, refresh the quota, ingest the
    exchange into memory, invalidate the sections the agent's tools may have
    written, and return the terminal payload.

    Shared by ``/chat``, ``/chat/stream`` and ``/chat/start`` so the three
    cannot drift — the streaming variants ship this same dict as their ``done``
    event. ``prepared`` is the tuple from ``_prepare_chat``; ``run_id`` is set
    only when the caller pre-created the run to return its id up front.
    """
    plan, budget, ctx, tools, system_prompt, history = prepared
    result = await run_agent(
        message,
        trigger="chat",
        system_prompt=system_prompt,
        tools=tools,
        budget=budget,
        db=repo,
        ctx=ctx,
        user_id=user_id,
        history=history,
        on_event=on_event,
        run_id=run_id,
    )
    quota = await _chat_quota_payload(repo, user_id, plan, settings)
    _ingest_chat_memory(repo, user_id, message, result)
    # Agent tools may have written alerts or watchlist rows.
    snapshot.store.invalidate(user_id, "news", "watchlist", "me")
    return {
        "run_id": str(result.run_id),
        "answer": result.answer,
        "status": result.status,
        "iterations": result.iterations,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
        "tool_calls": result.tool_summaries,
        "chat_quota": quota,
    }


# Funnel visibility (PRODUCT.md: visitor -> signup -> connected portfolio).
# One structured log line per page render; no cookies, no client-side JS.
_funnel_logger = logging.getLogger("cirvia.funnel")
_timing_logger = logging.getLogger("cirvia.timing")
_FUNNEL_PATHS = frozenset({"/", "/pricing", "/app", "/app/onboarding", "/app/dashboard"})


def create_app() -> FastAPI:
    # The perf caches are process-wide singletons; a fresh app instance must
    # not inherit another instance's data (tests build many apps — prod one).
    snapshot.store.clear()
    authcache.cache_clear()
    _track_record_cache.clear()
    app = FastAPI(
        title="Cirvia",
        description="AI portfolio analyst for Canadian investors: read-only brokerage sync, daily digest, macro alerts.",
        lifespan=lifespan,
        dependencies=[Depends(require_auth)],
    )

    # Compress JSON/HTML bodies (news feeds and page shells shrink ~80%).
    # Starlette's GZip responder passes streaming responses through per-chunk,
    # so SSE (/chat/stream, deep-dive events) still delivers incrementally.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )

    @app.middleware("http")
    async def funnel_page_views(request: Request, call_next):
        started = perf_counter()
        response = await call_next(request)
        elapsed_ms = (perf_counter() - started) * 1000
        # Server-side timing for every API call: one log line + a
        # Server-Timing header the browser devtools surface per request.
        response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
        if request.url.path not in ("/health",):
            _timing_logger.info(
                "%s %s %d %.1fms",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        if (
            request.method == "GET"
            and request.url.path in _FUNNEL_PATHS
            and response.status_code == 200
        ):
            # Referrer + UTM capture (marketing.md backlog #2): the only way
            # to tell which channel/SEO surface actually drove a visit, with
            # no cookies and no third-party service — just more fields on
            # the same structured log line.
            qp = request.query_params
            _funnel_logger.info(
                "funnel.page_view path=%s referer=%s utm_source=%s utm_medium=%s "
                "utm_campaign=%s utm_term=%s utm_content=%s",
                request.url.path,
                request.headers.get("referer", "-"),
                qp.get("utm_source", "-"),
                qp.get("utm_medium", "-"),
                qp.get("utm_campaign", "-"),
                qp.get("utm_term", "-"),
                qp.get("utm_content", "-"),
            )
        return response

    @app.get("/", response_class=HTMLResponse)
    async def landing() -> HTMLResponse:
        """Public marketing page (also used for SnapTrade / partner review)."""
        return HTMLResponse(LANDING_HTML)

    @app.get("/robots.txt", response_class=Response)
    async def robots() -> Response:
        return Response(content=robots_txt(), media_type="text/plain")

    @app.get("/sitemap.xml", response_class=Response)
    async def sitemap() -> Response:
        return Response(content=sitemap_xml(), media_type="application/xml")

    @app.get("/contact", response_class=HTMLResponse)
    async def contact_page() -> HTMLResponse:
        return HTMLResponse(CONTACT_HTML)

    @app.get("/privacy", response_class=HTMLResponse)
    async def privacy_page() -> HTMLResponse:
        return HTMLResponse(PRIVACY_HTML)

    @app.get("/terms", response_class=HTMLResponse)
    async def terms_page() -> HTMLResponse:
        return HTMLResponse(TERMS_HTML)

    @app.get("/pricing", response_class=HTMLResponse)
    async def pricing_page() -> HTMLResponse:
        return HTMLResponse(PRICING_HTML)

    @app.get("/track-record", response_class=HTMLResponse)
    async def track_record_page() -> HTMLResponse:
        """Public proof page. A marketing surface must never 500 — any data
        problem degrades to the empty-state rendering."""
        payload: dict = {"available": False, "entries": [], "summary": None}
        if app.state.repo is not None:
            try:
                payload = await _track_record_payload(app.state.repo)
            except Exception:
                logging.getLogger(__name__).exception("track record page load failed")
        return HTMLResponse(track_record_html(payload))

    @app.get("/screener", response_class=HTMLResponse)
    async def screener_page() -> HTMLResponse:
        """Public valuation grid. Same never-500 posture as /track-record —
        a data problem degrades to the empty-state rendering."""
        payload: dict = {"as_of": None, "universe": {}, "rows": []}
        if app.state.repo is not None:
            try:
                payload = await _valuations_payload(app.state.repo)
            except Exception:
                logging.getLogger(__name__).exception("screener page load failed")
        return HTMLResponse(screener_html(payload))

    @app.get("/sample-digest", response_class=HTMLResponse)
    async def sample_digest_page() -> HTMLResponse:
        return HTMLResponse(SAMPLE_DIGEST_HTML)

    @app.get("/methodology", response_class=HTMLResponse)
    async def methodology_page() -> HTMLResponse:
        return HTMLResponse(METHODOLOGY_HTML)

    # ---- Signed-in web app (Supabase JS auth in the browser) -----------

    def _webapp_html(render) -> HTMLResponse:
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_anon_key:
            return HTMLResponse(NOT_CONFIGURED_HTML, status_code=503)
        return HTMLResponse(render(settings.supabase_url, settings.supabase_anon_key))

    @app.get("/app", response_class=HTMLResponse)
    async def app_login() -> HTMLResponse:
        """Sign in / sign up page."""
        return _webapp_html(login_page)

    @app.get("/app/onboarding", response_class=HTMLResponse)
    async def app_onboarding() -> HTMLResponse:
        """Connect brokerage -> sync -> digest preferences."""
        return _webapp_html(onboarding_page)

    @app.get("/app/dashboard", response_class=HTMLResponse)
    async def app_dashboard() -> HTMLResponse:
        """Holdings, digest, alerts, and chat."""
        return _webapp_html(dashboard_page)

    @app.get("/app/stock/{ticker}", response_class=HTMLResponse)
    async def app_stock(ticker: str) -> HTMLResponse:
        """Full-page view of one holding: chart, fundamentals, position, news."""
        t = _validated_ticker(ticker)  # 404s anything outside the symbol alphabet
        return _webapp_html(lambda url, key: stock_page(t, url, key))

    @app.get("/app/risk", response_class=HTMLResponse)
    async def app_risk() -> HTMLResponse:
        """Visual Risk Lab: portfolio-level quant analytics (Pro-gated by the
        /portfolio/risk-analytics API the page calls)."""
        return _webapp_html(risk_lab_page)

    @app.get("/app/picks", response_class=HTMLResponse)
    async def app_picks() -> HTMLResponse:
        """Daily Best Stocks dashboard (Pro-gated by the /stocks/picks API
        the page calls)."""
        return _webapp_html(picks_page)

    @app.get("/app/deep-dives", response_class=HTMLResponse)
    async def app_deep_dives() -> HTMLResponse:
        """Deep-dive report history and full report view (data comes from the
        Pro-gated /deep-dive APIs the page calls)."""
        return _webapp_html(deep_dives_page)

    @app.get("/app/settings", response_class=HTMLResponse)
    async def app_settings() -> HTMLResponse:
        """Account, brokerage connection, plan, and account deletion."""
        return _webapp_html(settings_page)

    @app.get("/app/settings/delivery")
    async def app_settings_delivery(request: Request) -> RedirectResponse:
        """Delivery now lives inside /app/settings as a section; old links
        and bookmarks (and the Discord OAuth callback) land on it directly."""
        qs = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"/app/settings{qs}#section-delivery", status_code=307)

    @app.get("/app/reset", response_class=HTMLResponse)
    async def app_reset() -> HTMLResponse:
        """Set a new password after a Supabase recovery-link redirect."""
        return _webapp_html(reset_page)

    @app.get("/health")
    async def health() -> dict:
        repo: Repo | None = app.state.repo
        db_ok = await repo.ping() if repo is not None else False
        scheduler = app.state.scheduler
        scheduler_ok = bool(scheduler and getattr(scheduler, "running", False))
        macro_scheduler = app.state.macro_scheduler
        macro_scheduler_ok = bool(
            macro_scheduler and getattr(macro_scheduler, "running", False)
        )
        delivery_scheduler = app.state.delivery_scheduler
        delivery_ok = bool(
            delivery_scheduler and getattr(delivery_scheduler, "running", False)
        )
        # Job-completion staleness (schedulers "running" says nothing about
        # whether jobs finish). Advisory: a stale digest must not flap the
        # deploy liveness probe, so "ok" stays db-only and jobs get their own
        # keys. Best-effort — a heartbeat-table problem degrades to {} rather
        # than 500ing the probe.
        jobs: dict = {}
        if repo is not None:
            try:
                heartbeats = {h.job_name: h for h in await repo.get_job_heartbeats()}
                jobs = job_health(heartbeats, get_settings())
            except Exception:
                logging.getLogger(__name__).warning(
                    "job heartbeat read failed", exc_info=True
                )
        jobs_ok = all(j.get("state") != "offline" for j in jobs.values())
        return {
            "ok": db_ok,
            "db": db_ok,
            "scheduler": scheduler_ok,
            "macro_scheduler": macro_scheduler_ok,
            "delivery_scheduler": delivery_ok,
            "jobs": jobs,
            "jobs_ok": jobs_ok,
        }

    @app.get("/auth/whoami")
    async def whoami(request: Request) -> dict:
        """Echo the user the current credential resolves to — a quick auth check.
        Works for both the service/owner token and a Supabase JWT."""
        user_id = _user_id(request)
        repo: Repo | None = app.state.repo
        email = None
        if repo is not None:
            user = await repo.get_user(user_id)
            email = user.email if user is not None else None
        return {
            "user_id": str(user_id),
            "email": email,
            "is_owner": user_id == _OWNER_USER_ID,
        }

    # One in-flight chat per user: the usage-limit check reads recorded cost
    # before the run starts, so parallel requests could all pass it at once
    # (check-then-act race) and blow past the Free caps. In-process is enough —
    # the app runs as a single process (see DeliveryScheduler et al.).
    active_chats: set[uuid.UUID] = set()
    # Exposed for the same reason the progress brokers are: it is a real
    # invariant of the three chat endpoints, and a test cannot hold a run
    # in flight across requests to observe it any other way.
    app.state.active_chats = active_chats

    @app.post("/chat")
    async def chat(req: ChatRequest, request: Request) -> dict:
        settings = get_settings()
        repo = _require_repo(app)
        user_id = _user_id(request)
        if user_id in active_chats:
            raise HTTPException(
                status_code=429,
                detail="A chat is already running for this account; wait for it to finish.",
            )
        # Claim before the first await so two racing requests can't both pass.
        active_chats.add(user_id)
        try:
            await _enforce_usage_limits(repo, user_id, settings)
            prepared = await _prepare_chat(repo, user_id, settings)
            return await _run_chat_turn(
                repo,
                user_id=user_id,
                message=req.message,
                settings=settings,
                prepared=prepared,
            )
        finally:
            active_chats.discard(user_id)

    # Keep strong references to driver tasks: asyncio only holds weak refs,
    # and a GC'd task would silently kill an in-flight streamed chat.
    stream_tasks: set[asyncio.Task] = set()

    @app.post("/chat/stream")
    async def chat_stream(req: ChatRequest, request: Request):
        """SSE variant of /chat: emits agent progress (tool steps, text
        deltas) live, then a terminal ``done`` event with the full answer.
        Pre-run failures (quota, concurrency) raise proper 4xx JSON before
        the stream starts; the browser falls back to POST /chat on transport
        errors."""
        settings = get_settings()
        repo = _require_repo(app)
        user_id = _user_id(request)
        if user_id in active_chats:
            raise HTTPException(
                status_code=429,
                detail="A chat is already running for this account; wait for it to finish.",
            )
        active_chats.add(user_id)
        try:
            await _enforce_usage_limits(repo, user_id, settings)
            prepared = await _prepare_chat(repo, user_id, settings)
        except BaseException:
            active_chats.discard(user_id)
            raise

        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(event: dict) -> None:
            await queue.put(event)

        async def drive() -> None:
            # Owns run completion: a disconnected client stops the SSE
            # generator, but the run still finishes, persists, and bills.
            try:
                done = await _run_chat_turn(
                    repo,
                    user_id=user_id,
                    message=req.message,
                    settings=settings,
                    prepared=prepared,
                    on_event=on_event,
                )
                await queue.put({"type": "done", **done})
            except Exception:
                logging.getLogger(__name__).exception("streamed chat run failed")
                await queue.put(
                    {
                        "type": "error",
                        "detail": "Something went wrong answering that. Please try again.",
                    }
                )
            finally:
                active_chats.discard(user_id)
                await queue.put(SENTINEL)

        task = asyncio.create_task(drive())
        stream_tasks.add(task)
        task.add_done_callback(stream_tasks.discard)
        return sse_response(queue, request)

    # Native clients cannot use POST /chat/stream: React Native's fetch has no
    # readable stream body and EventSource can neither POST nor set an
    # Authorization header. This pair splits the two halves — a POST that
    # claims the slot and returns the run id, then a plain GET for the SSE —
    # which also makes the run *recoverable*: when iOS suspends the app
    # mid-run the socket dies, but the run id is already on the client, so it
    # re-subscribes on foreground and replays what it missed. With
    # /chat/stream the id only arrives in the terminal `done` event, so a
    # backgrounded client loses the answer it has already been billed for.
    chat_broker = ProgressBroker(replay_size=500)
    app.state.chat_broker = chat_broker

    @app.post("/chat/start", status_code=202)
    async def chat_start(req: ChatRequest, request: Request) -> dict:
        """Claim the chat slot, start the run, and return its id immediately.

        Pre-run failures (quota, concurrency) still raise proper 4xx JSON
        before anything is started, exactly as /chat/stream does.
        """
        settings = get_settings()
        repo = _require_repo(app)
        user_id = _user_id(request)
        if user_id in active_chats:
            raise HTTPException(
                status_code=429,
                detail="A chat is already running for this account; wait for it to finish.",
            )
        active_chats.add(user_id)
        try:
            await _enforce_usage_limits(repo, user_id, settings)
            prepared = await _prepare_chat(repo, user_id, settings)
            # Created here rather than inside run_agent so the id exists before
            # the response is written.
            run_id = await repo.create_run(
                trigger="chat",
                user_message=req.message,
                model=settings.model,
                prompt_version=PROMPT_VERSION,
                user_id=user_id,
            )
        except BaseException:
            active_chats.discard(user_id)
            raise

        # Registered before the task starts so a client that opens the SSE in
        # the gap before the first event is told "live", not "unknown".
        chat_broker.open(run_id)

        async def on_event(event: dict) -> None:
            chat_broker.publish(run_id, event)

        async def drive() -> None:
            # Detached: the run owns its own completion, so a client that
            # never opens the SSE (or drops it) still gets a persisted,
            # billable answer it can collect later.
            try:
                done = await _run_chat_turn(
                    repo,
                    user_id=user_id,
                    message=req.message,
                    settings=settings,
                    prepared=prepared,
                    on_event=on_event,
                    run_id=run_id,
                )
                chat_broker.publish(run_id, {"type": "done", **done})
            except Exception:
                logging.getLogger(__name__).exception("started chat run failed")
                chat_broker.publish(
                    run_id,
                    {
                        "type": "error",
                        "detail": "Something went wrong answering that. Please try again.",
                    },
                )
            finally:
                active_chats.discard(user_id)
                chat_broker.close(run_id)

        task = asyncio.create_task(drive())
        stream_tasks.add(task)
        task.add_done_callback(stream_tasks.discard)
        return {"run_id": str(run_id)}

    @app.get("/chat/runs/{run_id}/events")
    async def chat_run_events(run_id: uuid.UUID, request: Request):
        """SSE tail for a run started by /chat/start.

        Opens with a ``chat_snapshot`` frame replaying every event buffered so
        far, which closes two gaps at once: the race between the POST
        returning and this GET opening, and a client that was suspended for
        the whole run and is only now coming back for its answer.
        """
        repo = _require_repo(app)
        caller = _user_id(request)
        run = await repo.get_run(run_id)
        # 404-not-403 so run ids can't be probed (same as /runs/{id}).
        if run is not None and caller != _OWNER_USER_ID and run.user_id != caller:
            run = None
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")

        # Read the broker's view *before* subscribing — subscribing would
        # itself make the run "known" and defeat the evicted-buffer check.
        finished = chat_broker.is_finished(run_id)
        known = chat_broker.is_known(run_id)
        replayed = chat_broker.history(run_id)

        queue = chat_broker.subscribe(run_id)
        await queue.put(
            {
                "type": "chat_snapshot",
                "run_id": str(run_id),
                "finished": finished,
                "events": replayed,
            }
        )
        if finished or not known:
            # Terminal, or so old its buffer was evicted: the snapshot is all
            # there is, and the client falls back to GET /runs/{run_id}.
            await queue.put(SENTINEL)
        response = sse_response(queue, request)
        original_iterator = response.body_iterator

        async def cleanup_iterator():
            try:
                async for chunk in original_iterator:
                    yield chunk
            finally:
                chat_broker.unsubscribe(run_id, queue)

        response.body_iterator = cleanup_iterator()
        return response

    @app.get("/chat/history")
    async def chat_history(request: Request, limit: int = 10) -> dict:
        """The user's recent chat turns, oldest first (dashboard rehydration).

        Turns are reconstructed from ``agent_runs`` (trigger='chat'): each run
        is one user message plus, when it finished, one assistant answer."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        limit = max(1, min(limit, 50))
        runs = await repo.list_chat_runs(user_id, limit=(limit + 1) // 2)
        turns: list[dict] = []
        for run in reversed(runs):  # repo returns newest first
            created = run.created_at.isoformat() if run.created_at else None
            turns.append(
                {"role": "user", "content": run.user_message, "created_at": created}
            )
            if run.final_answer:
                turns.append(
                    {
                        "role": "assistant",
                        "content": run.final_answer,
                        "created_at": created,
                    }
                )
        return {"turns": turns[-limit:]}

    # ---- Portfolio Deep Dive (multi-agent research; Pro-only) -----------

    # Same single-process reasoning as active_chats: one dive in flight per
    # user, and an in-process broker fans progress events out to SSE readers.
    active_deep_dives: set[uuid.UUID] = set()
    deep_dive_broker = ProgressBroker()
    app.state.deep_dive_broker = deep_dive_broker

    def _deep_dive_payload(row) -> dict:
        return {
            "report_id": str(row.id),
            "run_id": str(row.run_id),
            "status": row.status,
            "progress": row.progress or {},
            "report": row.report,
            "summary": row.summary,
            "cost_usd": float(row.cost_usd) if row.cost_usd is not None else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }

    @app.post("/deep-dive", status_code=202)
    async def start_deep_dive(request: Request) -> dict:
        settings = get_settings()
        repo = _require_repo(app)
        user_id = _user_id(request)
        user = await repo.get_user(user_id)
        plan = effective_plan(user)
        if user_id in active_deep_dives:
            raise HTTPException(
                status_code=429,
                detail="A deep dive is already running for this account.",
            )
        if user_id != _OWNER_USER_ID:
            if await repo.monthly_cost_usd(user_id) >= monthly_cost_cap(plan, settings):
                raise HTTPException(
                    status_code=402,
                    detail=(
                        "You've reached this month's fair-use compute cap. "
                        "It resets at the start of next month."
                    ),
                )
            # Pro: N per rolling week. Free: 1 per rolling month — enough to
            # taste the analyst depth that justifies Pro, not enough to live
            # on (the roadmap's free-tier repackaging).
            if plan == "pro":
                window = timedelta(days=7)
                limit = settings.deep_dive_weekly_limit
                period = "per week"
            else:
                window = timedelta(days=30)
                limit = settings.deep_dive_free_monthly_limit
                period = "per month on Free"
            if limit <= 0:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Deep dives are a Pro feature: a team of research "
                        "agents analyzing your whole portfolio. Upgrade to run one."
                    ),
                )
            used, oldest = await repo.deep_dive_usage_since(
                user_id, datetime.now(timezone.utc) - window
            )
            if used >= limit:
                unlocks = (oldest or datetime.now(timezone.utc)) + window
                local = unlocks.astimezone(_user_tz(user))
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Deep dive limit reached ({limit} {period}). "
                        f"Your next one unlocks {local:%a %b %-d}."
                    ),
                )
        if not await repo.list_positions(user_id=user_id):
            raise HTTPException(
                status_code=400,
                detail="Connect a brokerage and sync holdings before running a deep dive.",
            )

        active_deep_dives.add(user_id)
        try:
            run_id = await repo.create_run(
                trigger="deep_dive",
                user_message="[portfolio deep dive]",
                model=settings.model,
                prompt_version=PROMPT_VERSION,
                user_id=user_id,
            )
            report_id = await repo.create_deep_dive_report(
                run_id=run_id, user_id=user_id
            )
        except BaseException:
            active_deep_dives.discard(user_id)
            raise

        async def on_event(event: dict) -> None:
            deep_dive_broker.publish(report_id, event)

        async def drive() -> None:
            try:
                await run_deep_dive(
                    repo,
                    user_id=user_id,
                    report_id=report_id,
                    run_id=run_id,
                    on_event=on_event,
                )
            except Exception:
                logging.getLogger(__name__).exception("deep dive failed")
            finally:
                active_deep_dives.discard(user_id)
                deep_dive_broker.close(report_id)

        task = asyncio.create_task(drive())
        stream_tasks.add(task)
        task.add_done_callback(stream_tasks.discard)
        return {"report_id": str(report_id), "run_id": str(run_id)}

    @app.get("/deep-dive")
    async def list_deep_dives(request: Request, limit: int = 10) -> dict:
        repo = _require_repo(app)
        user_id = _user_id(request)
        rows = await repo.list_deep_dive_reports(user_id, limit=max(1, min(limit, 25)))
        return {"reports": [_deep_dive_payload(r) for r in rows]}

    @app.get("/deep-dive/{report_id}")
    async def get_deep_dive(report_id: uuid.UUID, request: Request) -> dict:
        repo = _require_repo(app)
        caller = _user_id(request)
        row = await repo.get_deep_dive_report(report_id)
        # 404-not-403 so report ids can't be probed (same as /runs/{id}).
        if row is not None and caller != _OWNER_USER_ID and row.user_id != caller:
            row = None
        if row is None:
            raise HTTPException(status_code=404, detail="report not found")
        return _deep_dive_payload(row)

    @app.get("/deep-dive/{report_id}/events")
    async def deep_dive_events(report_id: uuid.UUID, request: Request):
        """SSE progress tail: a snapshot frame first (so reconnects rehydrate),
        then live events until the dive finishes."""
        repo = _require_repo(app)
        caller = _user_id(request)
        row = await repo.get_deep_dive_report(report_id)
        if row is not None and caller != _OWNER_USER_ID and row.user_id != caller:
            row = None
        if row is None:
            raise HTTPException(status_code=404, detail="report not found")

        queue = deep_dive_broker.subscribe(report_id)
        await queue.put(
            {
                "type": "dd_snapshot",
                "status": row.status,
                "progress": row.progress or {},
            }
        )
        if row.status != "running":
            # Already terminal: snapshot is all there is.
            await queue.put(SENTINEL)
        response = sse_response(queue, request)
        # Unsubscribe when the response generator is exhausted/aborted.
        original_iterator = response.body_iterator

        async def cleanup_iterator():
            try:
                async for chunk in original_iterator:
                    yield chunk
            finally:
                deep_dive_broker.unsubscribe(report_id, queue)

        response.body_iterator = cleanup_iterator()
        return response

    @app.get("/runs/{run_id}")
    async def get_run(run_id: uuid.UUID, request: Request) -> dict:
        repo = _require_repo(app)
        run, model_calls, tool_calls = await repo.get_run_trajectory(run_id)
        # Tenant isolation: non-owner callers may only read their own runs.
        # 404 (not 403) so run ids can't be probed for existence.
        caller = _user_id(request)
        if run is not None and caller != _OWNER_USER_ID and run.user_id != caller:
            run = None
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {
            "run": _run_meta(run),
            "model_calls": [
                {
                    "iteration": mc.iteration,
                    "request": mc.request,
                    "response": mc.response,
                    "usage": mc.usage,
                }
                for mc in model_calls
            ],
            "tool_calls": [
                {
                    "iteration": tc.iteration,
                    "tool_name": tc.tool_name,
                    "input": tc.input,
                    "output": tc.output,
                    "is_error": tc.is_error,
                    "latency_ms": tc.latency_ms,
                }
                for tc in tool_calls
            ],
        }

    @app.get("/funnel")
    async def funnel_summary(request: Request) -> dict:
        """Owner-only funnel milestone counts (signup → connected → trial →
        decision) — the measurements the roadmap gates decisions on."""
        if _user_id(request) != _OWNER_USER_ID:
            raise HTTPException(status_code=403, detail="owner only")
        repo = _require_repo(app)
        return {"events": await repo.funnel_counts()}

    @app.get("/runs")
    async def list_runs(
        request: Request, trigger: str | None = None, limit: int = 50
    ) -> dict:
        repo = _require_repo(app)
        # Owner/service token sees all runs (ops debugging); users see their own.
        caller = _user_id(request)
        scope = None if caller == _OWNER_USER_ID else caller
        runs = await repo.list_runs(trigger=trigger, limit=limit, user_id=scope)
        return {"runs": [_run_meta(r) for r in runs]}

    @app.post("/digest/run")
    async def digest_run(request: Request) -> dict:
        repo = _require_repo(app)
        user_id = _user_id(request)
        if user_id == _OWNER_USER_ID and request.headers.get("X-Digest-Run-All") == "1":
            result = {"digests": await run_digests_for_all(repo)}
            snapshot.store.clear()
            return result
        result = await run_digest_pipeline(repo, user_id=user_id, force=True)
        snapshot.store.invalidate(user_id, "digest", "news")
        return result

    first_briefings_active: set[uuid.UUID] = set()

    @app.post("/digest/first", status_code=202)
    async def digest_first(request: Request) -> dict:
        """The instant first briefing — onboarding's aha moment.

        Fired as the user finishes onboarding, so their first value arrives in
        minutes, not with tomorrow's 9am digest. Runs in the background (the
        browser navigates away immediately); a no-op once any digest exists,
        so it can't be farmed for free runs."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        user = await repo.get_user(user_id)
        tz = user.timezone if user is not None else get_settings().tz
        if await get_latest_digest(repo, user_id=user_id, tz=tz) is not None:
            return {"status": "exists"}
        if user_id in first_briefings_active:
            return {"status": "running"}
        if not await repo.list_positions(user_id=user_id):
            raise HTTPException(
                status_code=400, detail="Add holdings before your first briefing."
            )
        first_briefings_active.add(user_id)

        async def drive() -> None:
            try:
                await run_digest_pipeline(repo, user_id=user_id, force=True)
                await repo.record_funnel_event("first_briefing", user_id=user_id)
                snapshot.store.invalidate(user_id, "digest", "news")
            except Exception:
                logging.getLogger(__name__).exception("first briefing failed")
            finally:
                first_briefings_active.discard(user_id)

        task = asyncio.create_task(drive())
        stream_tasks.add(task)
        task.add_done_callback(stream_tasks.discard)
        return {"status": "started"}

    @app.get("/digest/latest")
    async def digest_latest(request: Request) -> dict:
        repo = _require_repo(app)
        user_id = _user_id(request)
        user = await repo.get_user(user_id)
        tz = user.timezone if user is not None else get_settings().tz
        latest = await get_latest_digest(repo, user_id=user_id, tz=tz)
        if latest is None:
            raise HTTPException(status_code=404, detail="no digest for today yet")
        return latest

    # ---- Macro alerts --------------------------------------------------

    @app.post("/macro/scan")
    async def macro_scan(request: Request) -> dict:
        """Run macro specialists for the authenticated user (or all users via service token)."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        if user_id == _OWNER_USER_ID and request.headers.get("X-Macro-Scan-All") == "1":
            results = await run_macro_scans_for_all(repo)
            return {"scans": results}
        return await run_macro_scan(repo, user_id=user_id)

    @app.post("/anomaly/scan")
    async def anomaly_scan(request: Request) -> dict:
        """Run the price-anomaly detectors for the authenticated user (or all
        recipients via service token). Detector math is model-free; only the
        per-user narration costs anything."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        if user_id == _OWNER_USER_ID and request.headers.get("X-Anomaly-Scan-All") == "1":
            results = await run_anomaly_scans_for_all(repo)
            return {"scans": results}
        return await run_anomaly_scan(repo, user_id=user_id)

    @app.post("/news/refresh")
    async def news_refresh(request: Request) -> dict:
        """Fetch, importance-filter, and store holding news for the caller
        (or every recipient via service token) — same path as the daily job."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        if user_id == _OWNER_USER_ID and request.headers.get("X-News-Refresh-All") == "1":
            result = {"refreshes": await run_news_refresh_for_all(repo)}
            snapshot.store.clear()
            return result
        result = await refresh_news_for_user(repo, user_id)
        snapshot.store.invalidate(user_id, "news")
        return result

    @app.get("/alerts")
    async def list_alerts(request: Request, limit: int = 20) -> dict:
        repo = _require_repo(app)
        alerts = await repo.recent_alerts(limit=limit, user_id=_user_id(request))
        return {
            "alerts": [
                {
                    "id": str(a.id),
                    "category": a.category,
                    "severity": a.severity,
                    "headline": a.headline,
                    "body": a.body,
                    "tickers": a.tickers,
                    "delivered": a.delivered,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in alerts
            ]
        }


    # ---- Brokerage sync (SnapTrade) ------------------------------------

    @app.post("/portfolio/snaptrade/register")
    async def portfolio_register(request: Request) -> dict:
        """Register a SnapTrade user for the caller (idempotent)."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        try:
            return await register_snaptrade_user(repo, user_id, get_settings())
        except SnapTradeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/portfolio/connect-url")
    async def portfolio_connect_url(request: Request) -> dict:
        """Return a SnapTrade Connection Portal URL for linking a brokerage."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        try:
            service = await service_for_user(repo, user_id, get_settings())
            return {"url": await asyncio.to_thread(service.connection_portal_url)}
        except SnapTradeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/portfolio/status")
    async def portfolio_brokerage_status(request: Request) -> dict:
        """Brokerage registration/connection/sync status for onboarding."""
        repo = _require_repo(app)
        return await portfolio_status(repo, _user_id(request), get_settings())

    @app.post("/portfolio/sync")
    async def portfolio_sync(request: Request) -> dict:
        """Pull live brokerage holdings from SnapTrade into positions."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        try:
            result = await sync_brokerage_positions(repo, user_id=user_id)
        except (SnapTradeError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        # First successful sync is the value moment: arm the account's one
        # no-card Pro trial (no-op on every later sync) and mark the funnel.
        armed = await repo.maybe_start_trial(user_id, get_settings().trial_days)
        await repo.record_funnel_event("portfolio_connected", user_id=user_id)
        if armed is not None:
            result = {**result, "trial_ends_at": armed.isoformat()}
        snapshot.store.invalidate(user_id, "portfolio", "status", "me")
        return result

    _MANUAL_ACCOUNT = "Manual"
    _MANUAL_MAX_ROWS = 30

    @app.post("/portfolio/manual")
    async def set_manual_portfolio(
        req: ManualPortfolioRequest, request: Request
    ) -> dict:
        """Typed-in holdings — the fallback for users who won't link a
        brokerage to an unknown site on day one (the funnel's #1 drop-off).

        Replaces the user's ``Manual`` account wholesale (brokerage-synced
        accounts are untouched). Cost basis is unknowable for typed entries,
        so avg_cost records the current price — P&L is measured from entry,
        which the UI labels. Counts as the first value moment: arms the
        trial and stamps the funnel, exactly like a brokerage sync."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        if not req.positions or len(req.positions) > _MANUAL_MAX_ROWS:
            raise HTTPException(
                status_code=400,
                detail=f"Enter between 1 and {_MANUAL_MAX_ROWS} holdings.",
            )
        merged: dict[str, float] = {}
        for row in req.positions:
            ticker = _validated_ticker(row.ticker)
            if not (0 < row.quantity <= 1e9):
                raise HTTPException(
                    status_code=400,
                    detail=f"{ticker}: quantity must be a positive number.",
                )
            merged[ticker] = merged.get(ticker, 0.0) + row.quantity

        tickers = sorted(merged)
        quote_result = await market.get_quote({"tickers": tickers})
        quotes = {q["ticker"]: q for q in quote_result.get("quotes", [])}
        unknown = [
            t for t in tickers if quotes.get(t, {}).get("last_price") is None
        ]
        if unknown:
            raise HTTPException(
                status_code=404,
                detail=f"Could not find a price for: {', '.join(unknown)}.",
            )

        for ticker in tickers:
            await repo.upsert_position(
                ticker=ticker,
                quantity=merged[ticker],
                avg_cost=quotes[ticker]["last_price"],
                # Yahoo-format heuristic: .TO trades in CAD, the rest in USD.
                currency="CAD" if ticker.endswith(".TO") else "USD",
                account=_MANUAL_ACCOUNT,
                user_id=user_id,
            )
        # Drop manual rows not re-submitted; never touch brokerage accounts.
        keep = {(t, _MANUAL_ACCOUNT) for t in tickers} | {
            (p.ticker, p.account)
            for p in await repo.list_positions(user_id=user_id)
            if p.account != _MANUAL_ACCOUNT
        }
        removed = await repo.prune_positions_except(keep, user_id=user_id)

        armed = await repo.maybe_start_trial(user_id, get_settings().trial_days)
        await repo.record_funnel_event("portfolio_connected", user_id=user_id)
        snapshot.store.invalidate(user_id, "portfolio", "status", "me")
        result: dict = {"positions": len(tickers), "removed": removed}
        if armed is not None:
            result["trial_ends_at"] = armed.isoformat()
        return result

    @app.delete("/connection")
    async def disconnect_brokerage(request: Request) -> dict:
        """Sever the caller's brokerage connection.

        Deletes the remote SnapTrade user when the client supports it
        (commercial mode), then clears the stored credentials. Already-synced
        holdings stay visible but stop updating."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        settings = get_settings()
        row = await repo.get_snaptrade_credentials(user_id)
        owner_env_creds = user_id == _OWNER_USER_ID and bool(
            settings.snaptrade_user_secret
        )
        if row is None and not owner_env_creds:
            raise HTTPException(
                status_code=404, detail="no brokerage connection to disconnect"
            )
        remote_deleted = False
        remote_error: str | None = None
        try:
            service = await service_for_user(repo, user_id, settings)
            remote_deleted = await asyncio.to_thread(service.delete_user)
        except SnapTradeError as exc:
            remote_error = str(exc)
        local_cleared = await repo.delete_snaptrade_credentials(user_id)
        snapshot.store.invalidate(user_id, "status", "portfolio")
        return {
            "disconnected": True,
            "remote_deleted": remote_deleted,
            "local_cleared": local_cleared,
            "remote_error": remote_error,
        }

    # ---- User profile & holdings ---------------------------------------

    @app.get("/me")
    async def get_me(request: Request) -> dict:
        """The authenticated user's profile + preferences."""
        repo = _require_repo(app)
        return await _me_payload(repo, _user_id(request))

    @app.patch("/me")
    async def update_me(req: PreferencesRequest, request: Request) -> dict:
        """Update digest preferences (timezone, send-time, enabled, watchlist)."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        send_time: time | None = None
        if req.digest_send_time is not None:
            try:
                send_time = time.fromisoformat(req.digest_send_time)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="digest_send_time must be HH:MM"
                ) from exc
        digest_tickers: list[str] | None = None
        if req.digest_tickers is not None:
            digest_tickers = await _validate_digest_tickers(
                repo, user_id, req.digest_tickers
            )
        await repo.update_user_preferences(
            user_id,
            timezone=req.timezone,
            digest_send_time=send_time,
            digest_enabled=req.digest_enabled,
            digest_tickers=digest_tickers,
        )
        snapshot.store.invalidate(user_id, "me", "portfolio")
        return await _me_payload(repo, user_id)

    @app.put("/me/profile")
    async def put_profile(req: ProfileRequest, request: Request) -> dict:
        """Persist the investor profile from onboarding / re-personalization.

        One write for the whole flow (answers + optional risk-comfort posture)
        so a skip mid-wizard never leaves a partial profile."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        if req.experience is not None and req.experience not in EXPERIENCE_LEVELS:
            raise HTTPException(status_code=400, detail="unknown experience level")
        if req.horizon is not None and req.horizon not in HORIZONS:
            raise HTTPException(status_code=400, detail="unknown horizon")
        bad_goals = [g for g in req.goals if g not in GOALS]
        if bad_goals:
            raise HTTPException(
                status_code=400, detail=f"unknown goals: {', '.join(bad_goals)}"
            )
        if req.risk_tolerance is not None and not 1 <= req.risk_tolerance <= 10:
            raise HTTPException(
                status_code=400, detail="risk_tolerance must be 1-10"
            )
        if req.chosen_posture is not None and req.chosen_posture not in POSTURES:
            raise HTTPException(status_code=400, detail="unknown posture")
        risk = resolve_risk_tolerance(req.risk_tolerance, req.chosen_posture)
        archetype = derive_archetype(req.horizon, risk, req.goals)
        await repo.update_user_profile(
            user_id,
            archetype=archetype,
            risk_tolerance=risk,
            horizon=req.horizon,
            experience=req.experience,
            goals=req.goals,
            completed_at=datetime.now(timezone.utc),
        )
        snapshot.store.invalidate(user_id, "me")
        return await _me_payload(repo, user_id)

    @app.post("/me/profile/dismiss")
    async def dismiss_profile_prompt(request: Request) -> dict:
        """Record the one-time 'personalize your experience' prompt dismissal
        (idempotent, persisted so it never re-appears on another device)."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        await repo.set_profile_prompt_dismissed(user_id)
        snapshot.store.invalidate(user_id, "me")
        return await _me_payload(repo, user_id)

    @app.get("/me/profile/projections")
    async def profile_projections(request: Request) -> dict:
        """Monte Carlo fans of the user's portfolio at three risk postures for
        the onboarding risk-comfort picker. Deliberately NOT Pro-gated (unlike
        /portfolio/risk-analytics): existing Free users re-personalizing must
        not hit a 402, and this is pure numpy on cached prices — no LLM cost.
        Falls back to illustrative fans when the book isn't analyzable yet."""
        repo = _require_repo(app)
        settings = get_settings()
        user_id = _user_id(request)
        user = await repo.get_user(user_id)
        tz = getattr(user, "timezone", None) or settings.tz
        ctx = ToolContext(settings=settings, repo=repo, user_id=user_id, timezone=tz)
        return await portfolio_risk.risk_posture_projections(ctx)

    @app.delete("/me")
    async def delete_me(request: Request) -> dict:
        """Delete the caller's account: every app table they own, and — when a
        service-role key is configured — the Supabase auth user too."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        if user_id == _OWNER_USER_ID:
            # The seeded owner backs the service token and background jobs.
            raise HTTPException(
                status_code=400, detail="the owner account cannot be deleted"
            )
        settings = get_settings()
        user = await repo.get_user(user_id)
        auth_id = getattr(user, "auth_id", None) if user is not None else None
        # An active subscription must die with the account — otherwise Stripe
        # keeps charging a customer we no longer know. Abort on failure rather
        # than leave a paying zombie behind.
        subscription_id = (
            getattr(user, "stripe_subscription_id", None) if user is not None else None
        )
        if subscription_id and billing.billing_enabled(settings):
            try:
                await billing.cancel_subscription(settings, subscription_id)
            except Exception as exc:
                logging.getLogger(__name__).error(
                    "could not cancel subscription %s during account deletion: %s",
                    subscription_id,
                    exc,
                )
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "could not cancel your subscription; try again in a "
                        "minute or contact us"
                    ),
                ) from exc
        await repo.delete_user_data(user_id)
        deleted_uid = auth_id if isinstance(auth_id, uuid.UUID) else None
        # The caller's JWT stays valid until its own exp, and deleting the
        # Supabase auth user below cannot revoke it. Tombstone the uid so a
        # token minted before now can't walk back into get_or_create_user and
        # silently provision a replacement account (migration 029). Written
        # after the data delete: tombstoning an account that then failed to
        # delete would lock a live user out.
        if deleted_uid is not None:
            await repo.tombstone_auth_id(deleted_uid)
        # Drop the cached auth mapping so a re-signup with the same auth uid
        # re-provisions instead of hitting a dead user id, and the cached
        # verifications so the next request re-verifies and recovers the iat
        # the tombstone check needs.
        authcache.evict_user(deleted_uid)
        authcache.evict_tokens_for(deleted_uid)
        snapshot.store.invalidate(user_id)
        auth_user_deleted = await _delete_supabase_auth_user(settings, auth_id)
        return {"deleted": True, "auth_user_deleted": auth_user_deleted}

    # ---- Watchlist ---------------------------------------------------------

    @app.get("/watchlist")
    async def get_watchlist(request: Request) -> dict:
        """The caller's watched tickers with live quotes and the plan cap."""
        repo = _require_repo(app)
        return await _watchlist_payload(repo, _user_id(request))

    @app.post("/watchlist/{ticker}")
    async def add_to_watchlist(ticker: str, request: Request) -> dict:
        """Watch a ticker (idempotent). Presence = opted into coverage: news
        refresh, the digest WATCHLIST section, and anomaly scans (Pro)."""
        t = _validated_ticker(ticker)
        repo = _require_repo(app)
        user_id = _user_id(request)
        settings = get_settings()

        current = await repo.get_watchlist_tickers(user_id)
        if t not in current and user_id != _OWNER_USER_ID:
            user = await repo.get_user(user_id)
            plan = effective_plan(user)
            cap = max_watchlist(plan, settings)
            if len(current) >= cap:
                hint = (
                    " Upgrade to Pro to watch more."
                    if plan != "pro"
                    else ""
                )
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{'Pro' if plan == 'pro' else 'Free'} plan allows at "
                        f"most {cap} watched stocks.{hint}"
                    ),
                )

        # The ticker must resolve to a real instrument before it can ride the
        # serial nightly fetch loops — junk stays out of the jobs entirely.
        funds = await fundamentals.get_fundamentals([t], repo=repo, settings=settings)
        data = funds.get(t) or {}
        if not _is_real_instrument(data, None):
            quote_result = await market.get_quote({"tickers": [t]})
            quotes = {q["ticker"]: q for q in quote_result.get("quotes", [])}
            if not _is_real_instrument(data, quotes.get(t, {}).get("last_price")):
                raise HTTPException(status_code=404, detail="unknown ticker")

        await repo.add_watchlist_ticker(user_id, t)
        snapshot.store.invalidate(user_id, "watchlist")
        return await _watchlist_payload(repo, user_id)

    @app.delete("/watchlist/{ticker}")
    async def remove_from_watchlist(ticker: str, request: Request) -> dict:
        """Stop watching a ticker; coverage stops with it."""
        t = _validated_ticker(ticker)
        repo = _require_repo(app)
        user_id = _user_id(request)
        await repo.remove_watchlist_ticker(user_id, t)
        snapshot.store.invalidate(user_id, "watchlist")
        return await _watchlist_payload(repo, user_id)

    # ---- Billing (Stripe) ------------------------------------------------

    @app.post("/billing/checkout")
    async def billing_checkout(req: CheckoutRequest, request: Request) -> dict:
        """A hosted Checkout URL for upgrading to Pro; the browser redirects."""
        settings = get_settings()
        if not billing.billing_enabled(settings):
            raise HTTPException(status_code=503, detail="billing is not configured")
        repo = _require_repo(app)
        user_id = _user_id(request)
        if user_id == _OWNER_USER_ID:
            raise HTTPException(
                status_code=400, detail="the owner account is already Pro"
            )
        user = await repo.get_user(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        if user.plan == "pro":
            raise HTTPException(
                status_code=409,
                detail="Already on Pro. Use Manage billing to change your plan.",
            )
        url = await billing.create_checkout_session(
            repo, settings, user, interval=req.interval
        )
        return {"url": url}

    @app.post("/billing/choose-free")
    async def billing_choose_free(request: Request) -> dict:
        """Resolve a lapsed (or running) trial by continuing on the Free plan.

        Clears the trial marker so digests resume on the Free cadence.
        Idempotent; a no-op for users with no trial state."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        await repo.resolve_trial(user_id)
        snapshot.store.invalidate(user_id, "me")
        return await _me_payload(repo, user_id)

    @app.post("/billing/portal")
    async def billing_portal(request: Request) -> dict:
        """A hosted Customer Portal URL (invoices, payment method, cancel)."""
        settings = get_settings()
        if not billing.billing_enabled(settings):
            raise HTTPException(status_code=503, detail="billing is not configured")
        repo = _require_repo(app)
        user = await repo.get_user(_user_id(request))
        customer_id = getattr(user, "stripe_customer_id", None) if user else None
        if not customer_id:
            raise HTTPException(status_code=409, detail="no billing history yet")
        return {"url": await billing.create_portal_session(settings, customer_id)}

    @app.post("/webhooks/stripe")
    async def stripe_webhook(request: Request) -> dict:
        """Subscription lifecycle events. Bearer-exempt; Stripe-Signature over
        the raw body is the auth. Every event re-fetches current subscription
        state, so ordering and redelivery are both harmless."""
        settings = get_settings()
        if not settings.stripe_webhook_secret:
            raise HTTPException(status_code=503, detail="billing is not configured")
        raw = await request.body()
        signature = request.headers.get("Stripe-Signature", "")
        try:
            event = billing.verify_webhook(
                raw, signature, settings.stripe_webhook_secret
            )
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail="invalid Stripe signature"
            ) from exc
        repo = _require_repo(app)
        if await repo.stripe_event_seen(event["id"]):
            return {"received": True, "duplicate": True}
        # Record only after success: a failed event must stay unrecorded so
        # Stripe's retry is processed rather than skipped as a duplicate.
        # (A racing duplicate delivery double-processes harmlessly — handling
        # re-fetches current Stripe state.)
        await billing.handle_event(repo, settings, event)
        await repo.record_stripe_event(event["id"], event["type"])
        # Subscription state changed for one of our users; snapshots are
        # cheap to rebuild, so clear rather than resolve customer → user.
        snapshot.store.clear()
        return {"received": True}

    @app.get("/news")
    async def list_news(
        request: Request,
        ticker: str | None = None,
        kind: str = "all",
        since: str | None = None,
        severity: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Unified stored-news feed: digests, macro alerts, holding articles."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        since_dt: datetime | None = None
        if since is not None:
            try:
                since_dt = datetime.fromisoformat(since)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="since must be ISO date or datetime"
                ) from exc
        items = await repo.list_stored_news(
            user_id,
            ticker=ticker,
            kind=kind,
            since=since_dt,
            severity=severity,
            category=category,
            limit=min(limit, 100),
        )
        return {"items": items}

    # ---- Notification channels ------------------------------------------

    async def _notifications_payload(repo: Repo, user_id: uuid.UUID) -> dict:
        settings = get_settings()
        user = await repo.get_user(user_id)
        rows = await repo.get_notification_channels(user_id)
        devices = await repo.list_push_devices(user_id)
        return {
            "preferred_channel": getattr(user, "preferred_channel", None),
            # Channels this deployment can send (creds configured) — drives the
            # UI picker. Push is filtered out on purpose: it is an additive
            # fan-out, not a destination a user can choose instead of email,
            # and offering it in the picker would let them lose their digest.
            "available_channels": sorted(
                c for c in app.state.delivery_adapters if c != PUSH_CHANNEL
            ),
            # Read-only for the web settings page, so web and native agree on
            # which devices are registered.
            "devices": [
                {
                    "id": str(d.id),
                    "platform": d.platform,
                    "kinds": list(d.kinds or []),
                    "masked": mask_destination(PUSH_CHANNEL, d.expo_token),
                    "last_seen_at": (
                        d.last_seen_at.isoformat() if d.last_seen_at else None
                    ),
                }
                for d in devices
            ],
            # One-click Discord connect (OAuth webhook.incoming) is offered
            # when the app creds + a state-signing secret are configured.
            "discord_oauth": bool(
                settings.discord_client_id
                and settings.discord_client_secret
                and unsubscribe.unsubscribe_secret(settings)
            ),
            "channels": [
                {
                    "channel": row.channel,
                    "destination_masked": mask_destination(row.channel, row.destination),
                    "verified": row.verified_at is not None,
                    "opted_out": row.opted_out_at is not None,
                    "consented": row.consent_at is not None,
                }
                for row in rows
            ],
        }

    @app.get("/me/notifications")
    async def get_notifications(request: Request) -> dict:
        """The user's registered channels + which channels are available."""
        repo = _require_repo(app)
        return await _notifications_payload(repo, _user_id(request))

    # ---- Push devices (native app) ---------------------------------------

    @app.post("/me/devices", status_code=201)
    async def register_device(req: DeviceRegisterRequest, request: Request) -> dict:
        """Register this device's Expo push token (idempotent).

        Called after the OS permission prompt is granted, and again on every
        launch — the token can rotate, and re-registering is what revives one
        that Expo previously reported dead.
        """
        repo = _require_repo(app)
        user_id = _user_id(request)
        token = req.expo_token.strip()
        if not token.startswith(("ExponentPushToken[", "ExpoPushToken[")):
            raise HTTPException(status_code=400, detail="not an Expo push token")
        if req.platform not in ("ios", "android"):
            raise HTTPException(status_code=400, detail="unknown platform")
        bad = [k for k in req.kinds if k not in _PUSH_KINDS]
        if bad:
            raise HTTPException(
                status_code=400, detail=f"unknown notification kinds: {', '.join(bad)}"
            )
        await repo.upsert_push_device(
            user_id,
            expo_token=token,
            platform=req.platform,
            kinds=list(req.kinds) or list(_PUSH_KINDS),
        )
        snapshot.store.invalidate(user_id, "notifications")
        return await _notifications_payload(repo, user_id)

    @app.delete("/me/devices")
    async def unregister_device(req: DeviceUnregisterRequest, request: Request) -> dict:
        """Stop pushing to a device — sign-out, or the user turning push off."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        # Ownership: only disable a token that belongs to the caller, so a
        # leaked token can't be used to silence someone else's device.
        owned = {d.expo_token for d in await repo.list_push_devices(user_id)}
        if req.expo_token.strip() in owned:
            await repo.disable_push_device(req.expo_token.strip())
        snapshot.store.invalidate(user_id, "notifications")
        return await _notifications_payload(repo, user_id)

    @app.patch("/me/devices/kinds")
    async def set_device_kinds(req: DeviceKindsRequest, request: Request) -> dict:
        """Which notifications this account's devices want."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        bad = [k for k in req.kinds if k not in _PUSH_KINDS]
        if bad:
            raise HTTPException(
                status_code=400, detail=f"unknown notification kinds: {', '.join(bad)}"
            )
        await repo.set_push_device_kinds(user_id, kinds=list(req.kinds))
        snapshot.store.invalidate(user_id, "notifications")
        return await _notifications_payload(repo, user_id)

    @app.post("/me/notifications/channel", status_code=202)
    async def register_channel(req: ChannelRegisterRequest, request: Request) -> dict:
        """Register a destination and send it a one-time verification code."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        if req.channel == "sms" and not req.consent:
            raise HTTPException(
                status_code=400,
                detail="SMS requires consent to receive automated texts",
            )
        try:
            await verification.issue_code(
                repo,
                app.state.delivery_adapters,
                user_id,
                channel=req.channel,
                destination=req.destination.strip(),
                consent=req.consent,
            )
        except verification.VerificationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return {"status": "code_sent", "channel": req.channel}

    @app.post("/me/notifications/verify")
    async def verify_channel(req: ChannelVerifyRequest, request: Request) -> dict:
        """Confirm a code; the channel becomes verified and preferred."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        try:
            await verification.check_code(
                repo, user_id, channel=req.channel, code=req.code
            )
        except verification.VerificationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        snapshot.store.invalidate(user_id, "notifications", "me")
        return await _notifications_payload(repo, user_id)

    @app.post("/me/notifications/preferred")
    async def set_preferred(req: PreferredChannelRequest, request: Request) -> dict:
        """Switch among already-verified channels."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        ok = await repo.set_preferred_channel(user_id, req.channel)
        if not ok:
            raise HTTPException(
                status_code=400, detail="channel is not verified for this account"
            )
        snapshot.store.invalidate(user_id, "notifications", "me")
        return await _notifications_payload(repo, user_id)

    def _public_base(request: Request) -> str:
        settings = get_settings()
        return settings.public_base_url.rstrip("/") or str(request.base_url).rstrip("/")

    def _discord_redirect(return_path: str, status: str) -> RedirectResponse:
        return RedirectResponse(f"{return_path}?discord={status}", status_code=303)

    @app.get("/me/notifications/discord/connect-url")
    async def discord_connect_url(request: Request, return_to: str = "settings") -> dict:
        """Mint the Discord OAuth2 authorize URL (scope webhook.incoming).

        Discord shows its native server + channel picker; the callback below
        receives a ready-made webhook URL. ``return_to`` names which app page
        the callback should land on afterwards."""
        settings = get_settings()
        secret = unsubscribe.unsubscribe_secret(settings)
        if not (settings.discord_client_id and settings.discord_client_secret and secret):
            raise HTTPException(
                status_code=503,
                detail="Discord connect is not configured; paste a webhook URL instead",
            )
        if return_to not in discord_connect.RETURN_PATHS:
            raise HTTPException(status_code=400, detail="unknown return_to")
        state = discord_connect.sign_state(secret, _user_id(request), return_to=return_to)
        url = discord_connect.authorize_url(
            settings.discord_client_id,
            redirect_uri=_public_base(request) + _DISCORD_CALLBACK_PATH,
            state=state,
        )
        return {"url": url}

    @app.get(_DISCORD_CALLBACK_PATH)
    async def discord_oauth_callback(
        request: Request, code: str = "", state: str = "", error: str = ""
    ) -> RedirectResponse:
        """Discord redirects here after the user picks a server + channel.

        Bearer-exempt: the signed ``state`` proves which user initiated the
        connect. On success the webhook becomes the verified, preferred
        ``discord`` destination — OAuth already proved ownership, so no
        verification code is needed."""
        settings = get_settings()
        secret = unsubscribe.unsubscribe_secret(settings)
        parsed = discord_connect.verify_state(secret, state) if secret else None
        if parsed is None:
            # No trusted user/return target; land somewhere sensible and let
            # the page offer the manual webhook fallback.
            return _discord_redirect("/app/settings", "error")
        user_id, return_path = parsed
        if error or not code:
            status = "cancelled" if error == "access_denied" else "error"
            return _discord_redirect(return_path, status)
        repo = _require_repo(app)
        _bind_user(request, user_id)
        try:
            webhook_url = await discord_connect.exchange_code(
                settings.discord_client_id,
                settings.discord_client_secret,
                code=code,
                redirect_uri=_public_base(request) + _DISCORD_CALLBACK_PATH,
            )
        except discord_connect.DiscordConnectError as exc:
            logging.getLogger(__name__).warning("discord connect failed: %s", exc)
            return _discord_redirect(return_path, "error")
        await repo.upsert_notification_channel(
            user_id, channel="discord", destination=webhook_url
        )
        await repo.mark_channel_verified(user_id, "discord")
        await repo.set_preferred_channel(user_id, "discord")
        return _discord_redirect(return_path, "connected")

    @app.post("/webhooks/twilio/sms")
    async def twilio_sms_webhook(request: Request) -> Response:
        """Inbound SMS from Twilio (STOP/HELP/START). Bearer-exempt; validated
        via X-Twilio-Signature over PUBLIC_BASE_URL + path + form params."""
        settings = get_settings()
        # Twilio posts application/x-www-form-urlencoded; parse directly rather
        # than request.form(), which requires the python-multipart package.
        raw = await request.body()
        params = dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True))
        base = settings.public_base_url.rstrip("/") or str(request.base_url).rstrip("/")
        signature = request.headers.get("X-Twilio-Signature", "")
        if not twilio_inbound.signature_valid(
            settings.twilio_auth_token, base + "/webhooks/twilio/sms", params, signature
        ):
            raise HTTPException(status_code=403, detail="invalid Twilio signature")
        repo = _require_repo(app)
        twiml = await twilio_inbound.handle_inbound_sms(
            repo, from_number=params.get("From", ""), body=params.get("Body", "")
        )
        return Response(content=twiml, media_type="application/xml")

    async def _handle_unsubscribe(token: str) -> HTMLResponse:
        """Verify a signed unsubscribe token and opt the channel out. Invalid
        tokens get one generic page — no hint about what was wrong."""
        settings = get_settings()
        secret = unsubscribe.unsubscribe_secret(settings)
        parsed = unsubscribe.verify_token(secret, token)
        if parsed is None:
            return HTMLResponse(unsubscribe.INVALID_LINK_HTML, status_code=400)
        user_id, channel = parsed
        repo = _require_repo(app)
        row = await repo.get_notification_channel(user_id, channel)
        if row is not None:
            # Same repo path as the Twilio STOP webhook.
            await repo.set_opt_out_by_destination(
                channel=channel, destination=row.destination, opted_out=True
            )
        return HTMLResponse(unsubscribe.UNSUBSCRIBED_HTML)

    @app.get("/unsubscribe", response_class=HTMLResponse)
    async def unsubscribe_get(token: str = "") -> HTMLResponse:
        """Email unsubscribe link (CASL). Bearer-exempt; the token is the auth."""
        return await _handle_unsubscribe(token)

    @app.post("/unsubscribe", response_class=HTMLResponse)
    async def unsubscribe_post(token: str = "") -> HTMLResponse:
        """RFC 8058 one-click unsubscribe (mail clients POST to the same URL)."""
        return await _handle_unsubscribe(token)

    @app.get("/portfolio")
    async def portfolio_holdings(request: Request) -> dict:
        """The authenticated user's holdings with live valuations."""
        repo = _require_repo(app)
        ctx = ToolContext(settings=get_settings(), repo=repo, user_id=_user_id(request))
        return await portfolio.get_portfolio({}, ctx)

    # ---- Dashboard bootstrap ---------------------------------------------

    async def _build_section(repo: Repo, user_id: uuid.UUID, name: str):
        """One dashboard section's raw data — byte-identical to the payload of
        its individual endpoint, so the client feeds the same renderers."""
        settings = get_settings()
        if name == "me":
            return await _me_payload(repo, user_id)
        if name == "portfolio":
            ctx = ToolContext(settings=settings, repo=repo, user_id=user_id)
            return await portfolio.get_portfolio({}, ctx)
        if name == "watchlist":
            return await _watchlist_payload(repo, user_id)
        if name == "digest":
            user = await repo.get_user(user_id)
            tz = user.timezone if user is not None else settings.tz
            # None (no digest yet) is a valid value, not an error: the
            # /digest/latest endpoint 404s, the bootstrap ships data: null.
            return await get_latest_digest(repo, user_id=user_id, tz=tz)
        if name == "news":
            items = await repo.list_stored_news(user_id, kind="all", limit=20)
            return {"items": items}
        if name == "status":
            return await portfolio_status(repo, user_id, settings)
        if name == "notifications":
            return await _notifications_payload(repo, user_id)
        raise ValueError(f"unknown bootstrap section {name!r}")

    async def _section_builder(user_id: uuid.UUID, name: str):
        """Builder for background snapshot refreshes (no request context, so
        the RLS ContextVar must be bound here)."""
        set_current_user_id(user_id)
        return await _build_section(_require_repo(app), user_id, name)

    @app.get("/dashboard/bootstrap")
    async def dashboard_bootstrap(request: Request) -> Response:
        """One aggregated read for the dashboard, stale-while-revalidate.

        Sections come from the per-user snapshot store: present sections are
        served instantly (expired ones re-listed in ``refreshing`` and rebuilt
        in the background); missing sections — cold start or post-write
        invalidation — are built inline. Warm requests therefore never wait
        on yfinance or SnapTrade."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        snapshot.store.touch(user_id)
        snap, stale = snapshot.store.get(user_id)
        if not snap:
            # Cold start for this user+process: cheap point to stamp the
            # once-per-account milestone (insert is idempotent).
            await repo.record_funnel_event("dashboard_viewed", user_id=user_id)
        sections: dict[str, dict] = {
            n: {"data": snap[n]} for n in snapshot.SECTION_NAMES if n in snap
        }
        missing = [n for n in snapshot.SECTION_NAMES if n not in snap]
        if missing:
            results = await asyncio.gather(
                *(_build_section(repo, user_id, n) for n in missing),
                return_exceptions=True,
            )
            for name, result in zip(missing, results):
                if isinstance(result, BaseException):
                    logging.getLogger(__name__).warning(
                        "bootstrap section %s failed: %s", name, result
                    )
                    sections[name] = {"error": str(result)}
                else:
                    sections[name] = {"data": result}
                    snapshot.store.put(user_id, name, result)
        if stale:
            snapshot.store.refresh(user_id, stale, _section_builder)
        # ETag over the sections only — generated_at changes every call and
        # would defeat If-None-Match revalidation.
        sections_body = json.dumps(sections, separators=(",", ":"), default=str)
        etag = f'"{hashlib.sha1(sections_body.encode()).hexdigest()}"'
        headers = {
            "ETag": etag,
            "Cache-Control": "private, max-age=0, must-revalidate",
            "Vary": "Authorization",
        }
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        payload = {
            "v": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "refreshing": stale,
            "sections": sections,
        }
        return Response(
            json.dumps(payload, separators=(",", ":"), default=str),
            media_type="application/json",
            headers=headers,
        )

    @app.get("/portfolio/metrics")
    async def portfolio_metrics(request: Request) -> dict:
        """Fundamental metrics for the caller's held tickers — the dashboard's
        second call, so /portfolio itself stays fast. Worst case (all tickers
        cold) this blocks on yfinance; the holdings table is already on screen."""
        repo = _require_repo(app)
        settings = get_settings()
        positions = await repo.list_positions(user_id=_user_id(request))
        tickers = sorted({p.ticker for p in positions})
        if not tickers:
            return {"metrics": {}}
        funds, quote_result = await asyncio.gather(
            fundamentals.get_fundamentals(tickers, repo=repo, settings=settings),
            market.get_quote({"tickers": tickers}),  # warm — /portfolio just ran
        )
        quotes = {q["ticker"]: q for q in quote_result["quotes"]}
        today = datetime.now(ZoneInfo(settings.tz)).date()
        metrics = {
            t: fundamentals.core_metrics(
                data, (quotes.get(t) or {}).get("last_price"), today
            )
            for t, data in funds.items()
        }
        return {"metrics": metrics}

    @app.get("/portfolio/logo/{ticker}")
    async def portfolio_logo(request: Request, ticker: str) -> Response:
        """Company logo for a ticker, resolved and cached server-side so the
        browser never tells a third-party icon host what the user holds.
        404 (no website / no icon yet) renders as the legend's lettermark."""
        repo = _require_repo(app)
        icon = await logos.get_logo(
            _validated_ticker(ticker), repo=repo, settings=get_settings()
        )
        if icon is None:
            raise HTTPException(status_code=404, detail="no logo for this ticker")
        body, media_type = icon
        return Response(
            body,
            media_type=media_type,
            # Logos are immutable in practice; a day of browser cache keeps
            # repeat dashboard loads from re-requesting all of them.
            headers={"Cache-Control": "private, max-age=86400"},
        )

    @app.get("/portfolio/risk-analytics")
    async def portfolio_risk_analytics(request: Request) -> dict:
        """Portfolio-level quant analytics for the visual Risk Lab page:
        covariance-based volatility, risk decomposition, correlation matrix,
        VaR, and the Monte Carlo fan. Pro-only (same economics as the Pro chat
        quant tools); Free callers get a 402 the page renders as an upgrade
        prompt. All numbers precomputed in app/quant/ — descriptive, not advice."""
        repo = _require_repo(app)
        settings = get_settings()
        user_id = _user_id(request)
        user = await repo.get_user(user_id)
        if effective_plan(user) != "pro" and user_id != _OWNER_USER_ID:
            raise HTTPException(
                status_code=402,
                detail="Portfolio risk analytics are a Pro feature.",
            )
        tz = getattr(user, "timezone", None) or settings.tz
        ctx = ToolContext(settings=settings, repo=repo, user_id=user_id, timezone=tz)
        return await portfolio_risk.risk_analytics_payload(ctx)

    @app.get("/stocks/search")
    async def stocks_search(request: Request, q: str = "") -> dict:
        """Find stocks by ticker or company name (Yahoo-format symbols).

        Registered BEFORE /stocks/{ticker} — FastAPI matches routes in
        registration order, so this must come first or "search" would be
        treated as a ticker."""
        return {"results": await symbol_search.search_symbols(q)}

    @app.get("/stocks/valuations")
    async def stocks_valuations() -> dict:
        """The public "cheap or expensive" grid: ticker/price/verdict for the
        whole tracked universe, written nightly by
        app/tools/valuation_refresh.py. Public and auth-exempt, like
        /stocks/picks/track-record — this is the no-signup browse hook, free
        for anyone, same posture as valucurve's free list. Deeper evidence
        (sector-median comparisons) lives on the per-ticker page and is
        Pro-gated there, not here. Registered BEFORE /stocks/{ticker} for the
        same route-ordering reason as /stocks/search above."""
        return await _valuations_payload(_require_repo(app))

    @app.get("/stocks/picks")
    async def stock_picks(request: Request) -> dict:
        """The Best Stocks dashboard document: latest completed/partial daily
        run (ranked picks with verified evidence + movers with grounded
        explanations). Generated once globally per day; Pro-only (402 renders
        as the upgrade gate). Registered before /stocks/{ticker} so "picks"
        is never treated as a ticker."""
        repo = _require_repo(app)
        user_id = _user_id(request)
        user = await repo.get_user(user_id)
        if effective_plan(user) != "pro" and user_id != _OWNER_USER_ID:
            raise HTTPException(
                status_code=402,
                detail="Daily stock picks are a Pro feature.",
            )
        row = await repo.get_latest_picks_run()
        if row is None or not row.payload:
            return {
                "available": False,
                "note": "No analysis has been generated yet. Check back tomorrow morning.",
            }
        payload = dict(row.payload)
        payload["available"] = True
        payload["status"] = row.status
        days_old = (date.today() - row.run_date).days
        # Weekends legitimately serve Friday's run; anything older is stale.
        if days_old > (1 if date.today().weekday() < 5 else 3):
            payload["stale"] = True
            payload["stale_note"] = (
                f"This analysis is from {row.run_date.isoformat()}; a fresh "
                "run has not completed since."
            )
        return payload

    @app.get("/stocks/picks/track-record")
    async def stock_picks_track_record(days: int = 90) -> dict:
        """Realized performance of past picks, computed at read time as
        total returns from each pick's publication bar to the latest stored
        close, with SPY (S&P 500 total return) over the identical span as the
        honesty benchmark. Public — this is the marketing site's proof; the
        picks board itself stays Pro."""
        return await _track_record_payload(_require_repo(app), days)

    picks_jobs_active: set[str] = set()

    @app.post("/stocks/picks/sync", status_code=202)
    async def trigger_picks_sync(request: Request) -> dict:
        """Owner-only manual trigger for the evening universe data sync (the
        /news/refresh pattern). Runs detached — a full sync takes ~25 min."""
        repo = _require_repo(app)
        if _user_id(request) != _OWNER_USER_ID:
            raise HTTPException(status_code=403, detail="owner only")
        if "sync" in picks_jobs_active:
            raise HTTPException(status_code=429, detail="a universe sync is already running")
        picks_jobs_active.add("sync")

        async def drive() -> None:
            try:
                await universe.run_universe_sync(repo, get_settings())
            except Exception:
                logging.getLogger(__name__).exception("universe sync failed")
            finally:
                picks_jobs_active.discard("sync")

        task = asyncio.create_task(drive())
        stream_tasks.add(task)
        task.add_done_callback(stream_tasks.discard)
        return {"status": "started"}

    @app.post("/stocks/picks/run", status_code=202)
    async def trigger_picks_run(request: Request) -> dict:
        """Owner-only manual trigger for the daily picks pipeline."""
        repo = _require_repo(app)
        if _user_id(request) != _OWNER_USER_ID:
            raise HTTPException(status_code=403, detail="owner only")
        if "run" in picks_jobs_active:
            raise HTTPException(status_code=429, detail="a picks run is already running")
        picks_jobs_active.add("run")

        async def drive() -> None:
            try:
                await run_stock_picks(repo)
                # New entries exist; the public proof page should show them.
                _track_record_cache.clear()
            except Exception:
                logging.getLogger(__name__).exception("stock picks run failed")
            finally:
                picks_jobs_active.discard("run")

        task = asyncio.create_task(drive())
        stream_tasks.add(task)
        task.add_done_callback(stream_tasks.discard)
        return {"status": "started"}

    @app.get("/stocks/{ticker}")
    async def stock_detail(ticker: str, request: Request) -> dict:
        """Everything the stock detail page needs except history and news.

        Works for any real ticker, held or not: held tickers price from the
        portfolio rows; others take a live quote. 404 only when neither
        fundamentals nor a quote resolve (junk symbols stay cost-free)."""
        t = _validated_ticker(ticker)
        repo = _require_repo(app)
        settings = get_settings()
        user_id = _user_id(request)
        ctx = ToolContext(settings=settings, repo=repo, user_id=user_id)
        pf = await portfolio.get_portfolio({}, ctx)
        rows = [p for p in pf.get("positions", []) if p["ticker"] == t]

        funds = await fundamentals.get_fundamentals([t], repo=repo, settings=settings)
        data = funds.get(t) or {}
        stored = await repo.get_ticker_fundamentals([t])
        fetched_at = stored[t].fetched_at.isoformat() if t in stored else None
        watching = t in await repo.get_watchlist_tickers(user_id)
        val_rows = await repo.get_ticker_valuations([t])
        user = await repo.get_user(user_id)

        position = None
        if rows:
            last_price = rows[0]["last_price"]
            day_change_pct = rows[0]["day_change_pct"]
            quantity = sum(r["quantity"] for r in rows)
            cost_basis = sum(r["quantity"] * r["avg_cost"] for r in rows)
            market_value = (
                sum(r["market_value"] for r in rows)
                if all(r["market_value"] is not None for r in rows)
                else None
            )
            currency = rows[0]["currency"]
            totals = pf.get("totals", {})
            usdcad = totals.get("usdcad_rate")
            total_mv_cad = totals.get("total_market_value_cad")
            weight_pct = None
            if market_value is not None and total_mv_cad:
                mv_cad = portfolio._to_cad(market_value, currency, usdcad)
                if mv_cad is not None:
                    weight_pct = round(mv_cad / total_mv_cad * 100, 2)
        else:
            quote_result = await market.get_quote({"tickers": [t]})
            quotes = {q["ticker"]: q for q in quote_result.get("quotes", [])}
            last_price = quotes.get(t, {}).get("last_price")
            day_change_pct = quotes.get(t, {}).get("day_change_pct")
            if not _is_real_instrument(data, last_price):
                raise HTTPException(status_code=404, detail="unknown ticker")

        dividends = dict(data.get("dividends") or {})
        dividends["dividend_yield_pct"] = fundamentals.dividend_yield_pct(
            dividends.get("dividend_rate"), last_price
        )
        price_action = dict(data.get("price_action") or {})
        price_action["pct_from_52w_high"] = fundamentals.pct_from_52w_high(
            last_price, price_action.get("high_52w")
        )
        today = datetime.now(ZoneInfo(settings.tz)).date()

        profile = dict(data.get("profile") or {})
        profile["ticker"] = t
        profile["quote_type"] = data.get("quote_type")

        # "Cheap or expensive" verdict (app/quant/valuation.py), written
        # nightly by valuation_refresh — a flat cache read, not live scoring.
        # The label is free (same tier as the /stocks/valuations grid); the
        # evidence (peer-median comparisons) is Pro-gated, field-level,
        # same effective_plan() check used for whole-endpoint 402s elsewhere
        # in this file.
        val = val_rows.get(t)
        verdict = None
        if val is not None:
            is_pro = effective_plan(user) == "pro" or user_id == _OWNER_USER_ID
            verdict = {
                "label": val.verdict,
                "as_of": val.as_of.isoformat() if val.as_of else None,
                "not_scored_reason": val.not_scored_reason,
                "evidence_gated": not is_pro,
                "evidence": (
                    {
                        "sector_z": float(val.sector_z) if val.sector_z is not None else None,
                        "metrics_used": val.metrics_used,
                        "sector_comparison": val.sector_comparison,
                        "sector": val.sector,
                        "industry": (val.evidence or {}).get("industry"),
                        "metrics": (val.evidence or {}).get("metrics"),
                    }
                    if is_pro
                    else None
                ),
            }

        if rows:
            position = {
                "quantity": quantity,
                "avg_cost": round(cost_basis / quantity, 4) if quantity else None,
                "cost_basis": round(cost_basis, 2),
                "market_value": round(market_value, 2) if market_value is not None else None,
                "currency": currency,
                "unrealized_pnl": (
                    round(market_value - cost_basis, 2) if market_value is not None else None
                ),
                "unrealized_pnl_pct": (
                    round((market_value / cost_basis - 1) * 100, 2)
                    if market_value is not None and cost_basis
                    else None
                ),
                "weight_pct": weight_pct,
                "annual_dividend_income": fundamentals.annual_dividend_income(
                    quantity, dividends.get("dividend_rate")
                ),
                "accounts": [
                    {
                        "account": r["account"],
                        "quantity": r["quantity"],
                        "market_value": r["market_value"],
                    }
                    for r in rows
                ],
            }

        return {
            "profile": profile,
            "quote": {
                "last_price": last_price,
                "day_change_pct": day_change_pct,
            },
            "valuation": data.get("valuation"),
            "verdict": verdict,
            "growth": data.get("growth"),
            "profitability": data.get("profitability"),
            "financial_health": data.get("financial_health"),
            "dividends": dividends,
            "price_action": price_action,
            "earnings": {
                "next_earnings_date": fundamentals.next_earnings_date(
                    data.get("earnings_dates"), today
                ),
                "ex_dividend_date": dividends.get("ex_dividend_date"),
            },
            "etf": data.get("etf"),
            "position": position,
            "held": bool(rows),
            "watching": watching,
            "fetched_at": fetched_at,
        }

    @app.get("/stocks/{ticker}/history")
    async def stock_history(ticker: str, request: Request, days: int = 182) -> dict:
        """OHLCV for the detail-page chart: days=1 is today's 5-minute bars
        (60s cached, polled by the 1D view); anything else wraps the daily
        agent tool."""
        t = _validated_ticker(ticker)
        if days == 1:
            return await market.get_intraday(t)
        try:
            return await market.get_price_history({"ticker": t, "days": days})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def _run_meta(run) -> dict:
    return {
        "id": str(run.id),
        "trigger": run.trigger,
        "user_message": run.user_message,
        "final_answer": run.final_answer,
        "status": run.status,
        "iterations": run.iterations,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cost_usd": float(run.cost_usd) if run.cost_usd is not None else None,
        "latency_ms": run.latency_ms,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "error_detail": run.error_detail,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


app = create_app()
