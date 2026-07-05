"""Multi-tenant isolation, verified against a real Postgres.

Skipped unless ``DATABASE_URL`` is set and migrations (incl. 002_multi_tenant)
have been applied — the rest of the suite runs fully offline. This proves the
repo scopes reads by ``user_id`` so one user never sees another's positions.
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db.repo import _OWNER_USER_ID, Repo

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="no DATABASE_URL; live-DB isolation test"
)


@pytest.fixture
async def repo():
    settings = get_settings()
    r = Repo(settings.database_url, ssl=settings.db_ssl)
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
