"""Multi-tenant isolation, verified against a real Postgres.

Skipped unless ``TEST_DATABASE_URL`` is set (explicit opt-in — point it at a
scratch database, e.g. the local Supabase stack, with migrations applied) —
the rest of the suite runs fully offline. This proves the repo scopes reads
by ``user_id`` so one user never sees another's positions.

    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres \
        pytest tests/test_tenant_isolation.py
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db.repo import _OWNER_USER_ID, Repo

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="no TEST_DATABASE_URL; live-DB isolation test is explicit opt-in",
)


@pytest.fixture
async def repo():
    r = Repo(
        os.environ["TEST_DATABASE_URL"],
        ssl=os.getenv("TEST_DB_SSL", "").lower() in ("1", "true"),
    )
    yield r
    await r.dispose()


async def test_positions_are_isolated_per_user(repo: Repo):
    user_b = uuid.uuid4()
    async with repo.engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, email) VALUES (:id, :email)"),
            {"id": user_b, "email": f"user-b-{user_b}@test"},
        )
    try:
        await repo.upsert_position(
            ticker="OWNERCO", quantity=Decimal(1), avg_cost=Decimal(1),
            currency="CAD", account="TFSA",
        )
        await repo.upsert_position(
            ticker="BONLY", quantity=Decimal(2), avg_cost=Decimal(2),
            currency="CAD", account="TFSA", user_id=user_b,
        )

        owner_tickers = {p.ticker for p in await repo.list_positions()}
        b_tickers = {p.ticker for p in await repo.list_positions(user_id=user_b)}

        assert "BONLY" not in owner_tickers  # owner cannot see user B's row
        assert "OWNERCO" not in b_tickers  # and vice versa
        assert b_tickers == {"BONLY"}
    finally:
        async with repo.engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM positions WHERE user_id = :id"), {"id": user_b}
            )
            await conn.execute(
                text("DELETE FROM positions WHERE user_id = :id AND ticker = 'OWNERCO'"),
                {"id": _OWNER_USER_ID},
            )
            await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_b})
