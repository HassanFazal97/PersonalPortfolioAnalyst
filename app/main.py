"""FastAPI app factory, routes, and scheduler startup.

Routes are added milestone by milestone. The ``Repo`` and scheduler are created
in the lifespan and stored on ``app.state`` so routes and the scheduler share
one connection pool.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, time
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent.budget import Budget
from app.agent.digest_pipeline import run_digest_pipeline, run_digests_for_all
from app.agent.loop import run_agent
from app.agent.macro.orchestrator import run_macro_scan, run_macro_scans_for_all
from app.agent.prompts import CHAT_SYSTEM_PROMPT
from app.auth.context import set_current_user_id
from app.auth.jwt import AuthError, jwks_url_for, verify_supabase_jwt
from app.config import DEFAULT_USER_ID, get_settings, monthly_cost_cap
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
from app.landing import (
    CONTACT_HTML,
    LANDING_HTML,
    PRICING_HTML,
    PRIVACY_HTML,
    TERMS_HTML,
)
from app.plans import max_digest_holdings
from app.scheduler import DeliveryScheduler, DigestScheduler, IntervalScheduler
from app.tools import portfolio
from app.tools.registry import CHAT_TOOLS, ToolContext
from app.webapp import (
    NOT_CONFIGURED_HTML,
    dashboard_page,
    delivery_settings_page,
    login_page,
    onboarding_page,
    reset_page,
    settings_page,
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
            _run_digest, cron=settings.digest_cron, timezone=settings.tz
        )
        scheduler.start()
        app.state.scheduler = scheduler

        if settings.macro_scan_interval_minutes > 0:
            async def _run_macro() -> None:
                await run_macro_scans_for_all(repo)

            macro_scheduler = IntervalScheduler(
                _run_macro,
                minutes=settings.macro_scan_interval_minutes,
                timezone=settings.tz,
            )
            macro_scheduler.start()
            app.state.macro_scheduler = macro_scheduler

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
                dispatcher.tick,
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
    if request.url.path in _AUTH_EXEMPT_PATHS:
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
        user_id = await repo.get_or_create_user(auth_id=auth_id, email=claims.get("email"))
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


def _fmt_time(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value[:5]
    return value.strftime("%H:%M")


async def _me_payload(repo: Repo, user_id: uuid.UUID) -> dict:
    settings = get_settings()
    user = await repo.get_user(user_id)
    is_owner = user_id == _OWNER_USER_ID
    if user is None:
        return {
            "user_id": str(user_id),
            "email": None,
            "plan": "pro" if is_owner else "free",
            "timezone": "America/Toronto",
            "digest_send_time": "07:45",
            "digest_enabled": True,
            "preferred_channel": None,
            "digest_tickers": [],
            "digest_tickers_limit": None if is_owner else settings.free_max_digest_holdings,
            "digest_tickers_editable": False,
            "is_owner": is_owner,
        }
    plan = user.plan
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
        "plan": plan,
        "timezone": user.timezone,
        "digest_send_time": _fmt_time(user.digest_send_time),
        "digest_enabled": user.digest_enabled,
        "preferred_channel": user.preferred_channel,
        "digest_tickers": digest_tickers,
        "digest_tickers_limit": cap,
        "digest_tickers_editable": editable,
        "is_owner": is_owner,
    }


async def _validate_digest_tickers(
    repo: Repo, user_id: uuid.UUID, tickers: list[str]
) -> list[str]:
    """Validate and normalize a digest watchlist update."""
    settings = get_settings()
    user = await repo.get_user(user_id)
    plan = getattr(user, "plan", "free") if user is not None else "free"
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


async def _enforce_usage_limits(repo: Repo, user_id: uuid.UUID, settings) -> None:
    """Guard a chat against the per-user monthly cost cap and the Free daily
    chat limit. Owner/service token is exempt. Raises 402 when over."""
    if user_id == _OWNER_USER_ID:
        return
    user = await repo.get_user(user_id)
    plan = getattr(user, "plan", "free") if user is not None else "free"
    if await repo.monthly_cost_usd(user_id) >= monthly_cost_cap(plan, settings):
        raise HTTPException(
            status_code=402,
            detail="Monthly usage limit reached. Upgrade to Pro or try again next month.",
        )
    if plan == "free" and await repo.count_chats_today(user_id) >= settings.free_daily_chat_limit:
        raise HTTPException(
            status_code=402,
            detail="Daily chat limit reached on the Free plan. Upgrade to Pro for unlimited chat.",
        )


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
        return {
            "ok": db_ok,
            "db": db_ok,
            "scheduler": scheduler_ok,
            "macro_scheduler": macro_scheduler_ok,
            "delivery_scheduler": delivery_ok,
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
            budget = Budget(
                max_iterations=settings.chat_max_iterations,
                max_cost_usd=settings.chat_max_cost_usd,
                model=settings.model,
            )
            result = await run_agent(
                req.message,
                trigger="chat",
                system_prompt=CHAT_SYSTEM_PROMPT,
                tools=CHAT_TOOLS,
                budget=budget,
                db=repo,
                user_id=user_id,
            )
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
        }

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
        await repo.delete_user_data(user_id)
        auth_user_deleted = await _delete_supabase_auth_user(settings, auth_id)
        return {"deleted": True, "auth_user_deleted": auth_user_deleted}

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
