"""FastAPI app factory, routes, and scheduler startup.

Routes are added milestone by milestone. The ``Repo`` and scheduler are created
in the lifespan and stored on ``app.state`` so routes and the scheduler share
one connection pool.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.agent.budget import Budget
from app.agent.loop import run_agent
from app.agent.prompts import CHAT_SYSTEM_PROMPT
from app.config import get_settings
from app.db.repo import Repo
from app.tools.registry import CHAT_TOOLS


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    repo = Repo(settings.database_url) if settings.database_url else None
    app.state.repo = repo
    app.state.scheduler = None  # populated in M4
    try:
        yield
    finally:
        if repo is not None:
            await repo.dispose()


class ChatRequest(BaseModel):
    message: str


def _require_repo(app: FastAPI) -> Repo:
    repo: Repo | None = app.state.repo
    if repo is None:
        raise HTTPException(status_code=503, detail="database not configured")
    return repo


def create_app() -> FastAPI:
    app = FastAPI(title="Portfolio Analyst Agent", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict:
        repo: Repo | None = app.state.repo
        db_ok = await repo.ping() if repo is not None else False
        scheduler = app.state.scheduler
        scheduler_ok = bool(scheduler and getattr(scheduler, "running", False))
        return {"ok": db_ok, "db": db_ok, "scheduler": scheduler_ok}

    @app.post("/chat")
    async def chat(req: ChatRequest) -> dict:
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
