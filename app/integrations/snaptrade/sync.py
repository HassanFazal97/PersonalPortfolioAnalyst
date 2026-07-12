"""Sync Wealthsimple holdings from SnapTrade into the positions table."""

from __future__ import annotations

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


async def sync_wealthsimple_positions(
    repo: Repo,
    *,
    user_id: uuid.UUID | None = None,
    settings: Settings | None = None,
    refresh: bool = True,
) -> dict[str, Any]:
    """Pull Wealthsimple positions via SnapTrade and upsert into Postgres.

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

    if refresh:
        refresh_skipped = 0
        for conn in service.list_connections():
            auth_id = conn.get("id") or conn.get("authorization_id")
            if auth_id and not service.refresh_connection(str(auth_id)):
                refresh_skipped += 1
    else:
        refresh_skipped = 0

    accounts = [a for a in service.list_accounts() if is_investment_account(a)]
    if not accounts:
        raise RuntimeError(
            "No investment accounts found. Open the connect URL and link "
            "Wealthsimple first."
        )

    mapped: list[MappedPosition] = []
    account_summaries: list[dict[str, Any]] = []

    for account in accounts:
        account_id = account.get("id")
        if not account_id:
            continue
        positions = service.get_account_positions(str(account_id))
        rows = map_account_positions(account, positions)
        mapped.extend(rows)
        account_summaries.append(
            {
                "account_id": account_id,
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

    keep: set[tuple[str, str]] = set()
    for row in merged.values():
        keep.add((row.ticker, row.account))
        await repo.upsert_position(
            ticker=row.ticker,
            quantity=row.quantity,
            avg_cost=row.avg_cost,
            currency=row.currency,
            account=row.account,
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
