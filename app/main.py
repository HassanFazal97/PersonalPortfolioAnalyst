"""FastAPI app factory, routes, and scheduler startup.

Routes are added milestone by milestone. The ``Repo`` and scheduler are created
in the lifespan and stored on ``app.state`` so routes and the scheduler share
one connection pool.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
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
from app.db.repo import Repo
from app.delivery import discord_connect, twilio_inbound, unsubscribe, verification
from app.delivery.adapters import build_adapters
from app.delivery.channels import mask_destination
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
    PRICING_HTML,
    PRIVACY_HTML,
    TERMS_HTML,
)
from app.memory import ingest as memory_ingest
from app.memory.embeddings import memory_enabled
from app.plans import (
    effective_plan,
    max_digest_holdings,
    trial_active,
    trial_decision_pending,
)
from app.scheduler import DeliveryScheduler, DigestScheduler, IntervalScheduler
from app.streaming import SENTINEL, ProgressBroker, sse_response
from app.tools import fundamentals, market, portfolio, portfolio_risk, price_store
from app.tools.registry import (
    CHAT_TOOLS,
    PRO_CHAT_TOOLS,
    RECALL_MEMORY_SCHEMA,
    WEB_SEARCH_TOOL,
    ToolContext,
)
from app.tools.tickers import normalize_ticker
from app.webapp import (
    NOT_CONFIGURED_HTML,
    dashboard_page,
    delivery_settings_page,
    login_page,
    onboarding_page,
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
    app.state.delivery_scheduler = None
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
        if app.state.delivery_scheduler is not None:
            app.state.delivery_scheduler.shutdown()
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


class ChannelRegisterRequest(BaseModel):
    channel: str  # 'sms' | 'email' | 'discord'
    destination: str
    consent: bool = False  # required True for sms (TCPA opt-in)


class ChannelVerifyRequest(BaseModel):
    channel: str
    code: str


class PreferredChannelRequest(BaseModel):
    channel: str


class CheckoutRequest(BaseModel):
    interval: str = "monthly"  # 'monthly' | 'annual'


_bearer = HTTPBearer(auto_error=False)

# Exempt from bearer auth so platform liveness probes and uptime pingers — which
# cannot attach the token — can reach it. /health returns no sensitive data.
# Every other route stays authed-by-default via the app-level dependency.
_AUTH_EXEMPT_PATHS = {
    "/",
    "/health",
    "/contact",
    "/privacy",
    "/terms",
    "/pricing",
    # The web app pages are static HTML shells; the browser authenticates the
    # API calls it makes from them with a Supabase JWT.
    "/app",
    "/app/onboarding",
    "/app/dashboard",
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
        jwks_url = jwks_url_for(settings.supabase_url) if settings.supabase_url else None
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
        repo = _require_repo(request.app)
        user_id = await repo.get_or_create_user(
            auth_id=auth_id,
            email=claims.get("email"),
            trial_days=settings.trial_days,
        )
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
    digest_tickers = await repo.get_digest_tickers(user_id)
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
    system_prompt = compose_chat_system_prompt(base_prompt, context)
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


# Funnel visibility (PRODUCT.md: visitor -> signup -> connected portfolio).
# One structured log line per page render; no cookies, no client-side JS.
_funnel_logger = logging.getLogger("cirvia.funnel")
_FUNNEL_PATHS = frozenset({"/", "/pricing", "/app", "/app/onboarding", "/app/dashboard"})


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cirvia",
        description="AI portfolio analyst for Canadian investors — read-only brokerage sync, daily digest, macro alerts.",
        lifespan=lifespan,
        dependencies=[Depends(require_auth)],
    )

    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )

    @app.middleware("http")
    async def funnel_page_views(request: Request, call_next):
        response = await call_next(request)
        if (
            request.method == "GET"
            and request.url.path in _FUNNEL_PATHS
            and response.status_code == 200
        ):
            _funnel_logger.info("funnel.page_view path=%s", request.url.path)
        return response

    @app.get("/", response_class=HTMLResponse)
    async def landing() -> HTMLResponse:
        """Public marketing page (also used for SnapTrade / partner review)."""
        return HTMLResponse(LANDING_HTML)

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

    @app.get("/app/settings", response_class=HTMLResponse)
    async def app_settings() -> HTMLResponse:
        """Account, brokerage connection, plan, and account deletion."""
        return _webapp_html(settings_page)

    @app.get("/app/settings/delivery", response_class=HTMLResponse)
    async def app_settings_delivery() -> HTMLResponse:
        """Digest delivery channel and schedule management."""
        return _webapp_html(delivery_settings_page)

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
            plan, budget, ctx, tools, system_prompt, history = await _prepare_chat(
                repo, user_id, settings
            )
            result = await run_agent(
                req.message,
                trigger="chat",
                system_prompt=system_prompt,
                tools=tools,
                budget=budget,
                db=repo,
                ctx=ctx,
                user_id=user_id,
                history=history,
            )
            quota = await _chat_quota_payload(repo, user_id, plan, settings)
            _ingest_chat_memory(repo, user_id, req.message, result)
        finally:
            active_chats.discard(user_id)
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
            plan, budget, ctx, tools, system_prompt, history = await _prepare_chat(
                repo, user_id, settings
            )
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
                result = await run_agent(
                    req.message,
                    trigger="chat",
                    system_prompt=system_prompt,
                    tools=tools,
                    budget=budget,
                    db=repo,
                    ctx=ctx,
                    user_id=user_id,
                    history=history,
                    on_event=on_event,
                )
                quota = await _chat_quota_payload(repo, user_id, plan, settings)
                _ingest_chat_memory(repo, user_id, req.message, result)
                await queue.put(
                    {
                        "type": "done",
                        "run_id": str(result.run_id),
                        "answer": result.answer,
                        "status": result.status,
                        "iterations": result.iterations,
                        "cost_usd": result.cost_usd,
                        "latency_ms": result.latency_ms,
                        "tool_calls": result.tool_summaries,
                        "chat_quota": quota,
                    }
                )
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
        if plan != "pro" and user_id != _OWNER_USER_ID:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Deep dives are a Pro feature — a team of research agents "
                    "analyzing your whole portfolio. Upgrade to run one."
                ),
            )
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
            window = timedelta(days=7)
            used, oldest = await repo.deep_dive_usage_since(
                user_id, datetime.now(timezone.utc) - window
            )
            if used >= settings.deep_dive_weekly_limit:
                unlocks = (oldest or datetime.now(timezone.utc)) + window
                local = unlocks.astimezone(_user_tz(user))
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Deep dive limit reached ({settings.deep_dive_weekly_limit} "
                        f"per week). Your next one unlocks {local:%a %b %-d}."
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
            return {"digests": await run_digests_for_all(repo)}
        return await run_digest_pipeline(repo, user_id=user_id, force=True)

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
            return {"refreshes": await run_news_refresh_for_all(repo)}
        return await refresh_news_for_user(repo, user_id)

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
            return {"url": service.connection_portal_url()}
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
        try:
            return await sync_brokerage_positions(repo, user_id=_user_id(request))
        except (SnapTradeError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

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
            remote_deleted = service.delete_user()
        except SnapTradeError as exc:
            remote_error = str(exc)
        local_cleared = await repo.delete_snaptrade_credentials(user_id)
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
        return await _me_payload(repo, user_id)

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
                        "could not cancel your subscription — try again in a "
                        "minute or contact us"
                    ),
                ) from exc
        await repo.delete_user_data(user_id)
        auth_user_deleted = await _delete_supabase_auth_user(settings, auth_id)
        return {"deleted": True, "auth_user_deleted": auth_user_deleted}

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
                detail="Already on Pro — use Manage billing to change your plan.",
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
        return {
            "preferred_channel": getattr(user, "preferred_channel", None),
            # Channels this deployment can send (creds configured) — drives the UI picker.
            "available_channels": sorted(app.state.delivery_adapters.keys()),
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
            return _discord_redirect("/app/settings/delivery", "error")
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

    @app.get("/stocks/{ticker}")
    async def stock_detail(ticker: str, request: Request) -> dict:
        """Everything the stock detail page needs except history and news.

        404 for tickers the user doesn't hold — the page is only reachable
        from the holdings table, and the gate bounds fetch cost."""
        t = _validated_ticker(ticker)
        repo = _require_repo(app)
        settings = get_settings()
        ctx = ToolContext(settings=settings, repo=repo, user_id=_user_id(request))
        pf = await portfolio.get_portfolio({}, ctx)
        rows = [p for p in pf.get("positions", []) if p["ticker"] == t]
        if not rows:
            raise HTTPException(status_code=404, detail="not in your holdings")

        funds = await fundamentals.get_fundamentals([t], repo=repo, settings=settings)
        data = funds.get(t) or {}
        stored = await repo.get_ticker_fundamentals([t])
        fetched_at = stored[t].fetched_at.isoformat() if t in stored else None

        last_price = rows[0]["last_price"]
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

        return {
            "profile": profile,
            "quote": {
                "last_price": last_price,
                "day_change_pct": rows[0]["day_change_pct"],
            },
            "valuation": data.get("valuation"),
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
            "position": {
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
            },
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
