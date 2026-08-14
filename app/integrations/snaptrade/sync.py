"""Sync brokerage holdings from SnapTrade into the positions table."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from app.config import Settings, get_settings
from app.db.repo import Repo
from app.integrations.snaptrade.client import SnapTradeError, SnapTradeService
from app.integrations.snaptrade.mapper import (
    MappedPosition,
    is_investment_account,
    map_account_positions,
)
from app.integrations.snaptrade.onboarding import service_for_user


async def sync_brokerage_positions(
    repo: Repo,
    *,
    user_id: uuid.UUID | None = None,
    settings: Settings | None = None,
    refresh: bool = True,
) -> dict[str, Any]:
    """Pull brokerage positions via SnapTrade and upsert into Postgres.

    Scoped to ``user_id`` so each tenant's book stays isolated. Positions no
    longer reported by SnapTrade are pruned for that user only.
    """
    settings = settings or get_settings()
    try:
        service = await service_for_user(repo, user_id, settings) if user_id else SnapTradeService(settings)
    except SnapTradeError:
        if user_id is not None:
            raise
        service = SnapTradeService(settings)

    # The SnapTrade SDK is synchronous (requests): every remote call runs
    # via to_thread so a sync — inline from POST /portfolio/sync or from the
    # background positions job — never blocks the event loop. The per-item
    # calls fan out concurrently: each is an independent HTTP request, and
    # serial round trips were the bulk of this endpoint's latency.
    if refresh:
        auth_ids = [
            str(a)
            for conn in await asyncio.to_thread(service.list_connections)
            if (a := conn.get("id") or conn.get("authorization_id"))
        ]
        refreshed = await asyncio.gather(
            *(asyncio.to_thread(service.refresh_connection, a) for a in auth_ids)
        )
        refresh_skipped = sum(1 for ok in refreshed if not ok)
    else:
        refresh_skipped = 0

    accounts = [
        a
        for a in await asyncio.to_thread(service.list_accounts)
        if is_investment_account(a) and a.get("id")
    ]
    if not accounts:
        raise RuntimeError(
            "No investment accounts found. Open the connect URL and link "
            "your brokerage first."
        )

    positions_by_account = await asyncio.gather(
        *(
            asyncio.to_thread(service.get_account_positions, str(a["id"]))
            for a in accounts
        )
    )

    mapped: list[MappedPosition] = []
    account_summaries: list[dict[str, Any]] = []
    for account, positions in zip(accounts, positions_by_account):
        rows = map_account_positions(account, positions)
        mapped.extend(rows)
        account_summaries.append(
            {
                "account_id": account.get("id"),
                "name": account.get("name"),
                "raw_type": account.get("raw_type"),
                "positions": len(rows),
            }
        )

    # Distinct brokerage accounts can collapse into the same (ticker, account)
    # bucket — e.g. VFV held in both an RRSP and an FHSA. upsert_position
    # replaces rather than adds, so merge those rows first (sum quantities,
    # weighted-average the cost) or the last account synced would win.
    merged: dict[tuple[str, str], MappedPosition] = {}
    for row in mapped:
        key = (row.ticker, row.account)
        prev = merged.get(key)
        if prev is None:
            merged[key] = row
            continue
        total = prev.quantity + row.quantity
        avg = (
            (prev.avg_cost * prev.quantity + row.avg_cost * row.quantity) / total
            if total > 0
            else prev.avg_cost
        )
        merged[key] = MappedPosition(
            ticker=row.ticker,
            quantity=total,
            avg_cost=avg,
            currency=prev.currency,
            account=row.account,
        )

    keep = set(merged.keys())
    await repo.upsert_positions(
        [
            {
                "ticker": row.ticker,
                "quantity": row.quantity,
                "avg_cost": row.avg_cost,
                "currency": row.currency,
                "account": row.account,
            }
            for row in merged.values()
        ],
        user_id=user_id,
    )

    removed = await repo.prune_positions_except(keep, user_id=user_id)

    if user_id is not None:
        await repo.update_snaptrade_status(
            user_id,
            last_sync_at=datetime.now(),
            last_sync_error=None,
        )

    return {
        "accounts_synced": len(account_summaries),
        "positions_upserted": len(merged),
        "positions_removed": removed,
        "refresh_skipped": refresh_skipped,
        "accounts": account_summaries,
        "tickers": sorted({row.ticker for row in mapped}),
    }
