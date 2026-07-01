"""FastAPI app factory, routes, and scheduler startup.

Routes are added milestone by milestone. M1 provides only ``GET /health``.
The ``Repo`` and scheduler are created in the lifespan and stored on
``app.state`` so routes and the scheduler share one connection pool.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db.repo import Repo


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


def create_app() -> FastAPI:
    app = FastAPI(title="Portfolio Analyst Agent", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict:
        repo: Repo | None = app.state.repo
        db_ok = await repo.ping() if repo is not None else False
        scheduler = app.state.scheduler
        scheduler_ok = bool(scheduler and getattr(scheduler, "running", False))
        return {"ok": db_ok, "db": db_ok, "scheduler": scheduler_ok}

    return app


app = create_app()
