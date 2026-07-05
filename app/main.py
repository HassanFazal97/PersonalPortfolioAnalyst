"""FastAPI app factory, routes, and scheduler startup.

Routes are added milestone by milestone. The ``Repo`` and scheduler are created
in the lifespan and stored on ``app.state`` so routes and the scheduler share
one connection pool.
"""

from __future__ import annotations

import hmac
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.agent.budget import Budget
from app.agent.digest_pipeline import run_digest_pipeline
from app.agent.loop import run_agent
from app.agent.macro.orchestrator import run_macro_scan
from app.agent.prompts import CHAT_SYSTEM_PROMPT
from app.auth.context import set_current_user_id
from app.auth.jwt import AuthError, verify_supabase_jwt
from app.config import DEFAULT_USER_ID, get_settings
from app.db.repo import Repo
from app.delivery.imessage import MAX_ATTEMPTS, pending_payload
from app.delivery.shortcuts import get_latest_digest
from app.integrations.snaptrade.client import SnapTradeError, SnapTradeService
from app.integrations.snaptrade.sync import sync_wealthsimple_positions
from app.scheduler import DigestScheduler, IntervalScheduler
from app.tools.registry import CHAT_TOOLS


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

    if repo is not None:
        async def _run_digest() -> None:
            await run_digest_pipeline(repo)

        scheduler = DigestScheduler(
            _run_digest, cron=settings.digest_cron, timezone=settings.tz
        )
        scheduler.start()
        app.state.scheduler = scheduler

        if settings.macro_scan_interval_minutes > 0:
            async def _run_macro() -> None:
                await run_macro_scan(repo)

            macro_scheduler = IntervalScheduler(
                _run_macro,
                minutes=settings.macro_scan_interval_minutes,
                timezone=settings.tz,
            )
            macro_scheduler.start()
            app.state.macro_scheduler = macro_scheduler

    try:
        yield
    finally:
        if app.state.macro_scheduler is not None:
            app.state.macro_scheduler.shutdown()
        if app.state.scheduler is not None:
            app.state.scheduler.shutdown()
        if repo is not None:
            await repo.dispose()


class ChatRequest(BaseModel):
    message: str


class AckRequest(BaseModel):
    status: str


class InboundRequest(BaseModel):
    message: str


_bearer = HTTPBearer(auto_error=False)

# Exempt from bearer auth so platform liveness probes and uptime pingers — which
# cannot attach the token — can reach it. /health returns no sensitive data.
# Every other route stays authed-by-default via the app-level dependency.
_AUTH_EXEMPT_PATHS = {"/health"}

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

    # 2) Supabase per-user JWT.
    if settings.supabase_jwt_secret:
        try:
            claims = verify_supabase_jwt(
                supplied, settings.supabase_jwt_secret, audience=settings.supabase_jwt_aud
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


def create_app() -> FastAPI:
    app = FastAPI(
        title="Portfolio Analyst Agent",
        lifespan=lifespan,
        dependencies=[Depends(require_auth)],
    )

    @app.get("/health")
    async def health() -> dict:
        repo: Repo | None = app.state.repo
        db_ok = await repo.ping() if repo is not None else False
        scheduler = app.state.scheduler
        scheduler_ok = bool(scheduler and getattr(scheduler, "running", False))
        return {"ok": db_ok, "db": db_ok, "scheduler": scheduler_ok}

    @app.post("/chat")
    async def chat(req: ChatRequest, request: Request) -> dict:
        settings = get_settings()
        repo = _require_repo(app)
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
            user_id=_user_id(request),
        )
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

    @app.get("/runs/{run_id}")
    async def get_run(run_id: uuid.UUID) -> dict:
        repo = _require_repo(app)
        run, model_calls, tool_calls = await repo.get_run_trajectory(run_id)
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
    async def list_runs(trigger: str | None = None, limit: int = 50) -> dict:
        repo = _require_repo(app)
        runs = await repo.list_runs(trigger=trigger, limit=limit)
        return {"runs": [_run_meta(r) for r in runs]}

    @app.post("/digest/run")
    async def digest_run() -> dict:
        repo = _require_repo(app)
        return await run_digest_pipeline(repo)

    @app.get("/digest/latest")
    async def digest_latest() -> dict:
        settings = get_settings()
        repo = _require_repo(app)
        latest = await get_latest_digest(repo, tz=settings.tz)
        if latest is None:
            raise HTTPException(status_code=404, detail="no digest for today yet")
        return latest

    # ---- Macro alerts --------------------------------------------------

    @app.post("/macro/scan")
    async def macro_scan() -> dict:
        """Run the macro/geopolitical specialists now and enqueue any new alerts."""
        repo = _require_repo(app)
        return await run_macro_scan(repo)

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

    # ---- Phase B: Mac worker outbox ------------------------------------

    @app.get("/outbox/pending")
    async def outbox_pending() -> dict:
        repo = _require_repo(app)
        return {"messages": await pending_payload(repo)}

    @app.post("/outbox/{msg_id}/ack")
    async def outbox_ack(msg_id: uuid.UUID, req: AckRequest) -> dict:
        repo = _require_repo(app)
        if req.status not in ("sent", "failed"):
            raise HTTPException(status_code=400, detail="status must be 'sent' or 'failed'")
        result = await repo.ack_outbound(
            msg_id, status=req.status, max_attempts=MAX_ATTEMPTS
        )
        if result is None:
            raise HTTPException(status_code=404, detail="message not found")
        return {"id": str(msg_id), "status": result}

    @app.post("/inbound")
    async def inbound(req: InboundRequest, request: Request) -> dict:
        """Stub: run a chat agent for an incoming message and enqueue the reply.
        Incoming-message reading (chat.db) is out of scope; this endpoint lets
        the Mac worker be extended to two-way later."""
        settings = get_settings()
        repo = _require_repo(app)
        user_id = _user_id(request)
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
        await repo.enqueue_outbound(result.answer, user_id=user_id)
        return {"run_id": str(result.run_id), "queued_reply": result.answer}

    # ---- Wealthsimple sync (SnapTrade) ---------------------------------

    @app.get("/portfolio/connect-url")
    async def portfolio_connect_url() -> dict:
        """Return a SnapTrade Connection Portal URL for linking Wealthsimple."""
        try:
            service = SnapTradeService(get_settings())
            return {"url": service.connection_portal_url()}
        except SnapTradeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/portfolio/sync")
    async def portfolio_sync() -> dict:
        """Pull live Wealthsimple holdings from SnapTrade into positions."""
        repo = _require_repo(app)
        try:
            return await sync_wealthsimple_positions(repo)
        except (SnapTradeError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

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
