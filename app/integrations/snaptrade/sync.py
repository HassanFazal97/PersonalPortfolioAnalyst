"""Sync Wealthsimple holdings from SnapTrade into the positions table."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.db.repo import Repo
from app.integrations.snaptrade.client import SnapTradeService
from app.integrations.snaptrade.mapper import (
    MappedPosition,
    is_investment_account,
    map_account_positions,
)


async def sync_wealthsimple_positions(
    repo: Repo,
    *,
    settings: Settings | None = None,
    refresh: bool = True,
) -> dict[str, Any]:
    """Pull all Wealthsimple positions via SnapTrade and upsert into Postgres.

    Positions no longer reported by SnapTrade are removed so the DB mirrors
    live holdings. Returns a summary dict suitable for CLI or API responses.
    """
    settings = settings or get_settings()
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
            "No investment accounts found. Run scripts/connect_wealthsimple.py "
            "and link your Wealthsimple account first."
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

    keep: set[tuple[str, str]] = set()
    for row in mapped:
        keep.add((row.ticker, row.account))
        await repo.upsert_position(
            ticker=row.ticker,
            quantity=row.quantity,
            avg_cost=row.avg_cost,
            currency=row.currency,
            account=row.account,
        )

    removed = await repo.prune_positions_except(keep)

    return {
        "accounts_synced": len(account_summaries),
        "positions_upserted": len(mapped),
        "positions_removed": removed,
        "refresh_skipped": refresh_skipped,
        "accounts": account_summaries,
        "tickers": sorted({row.ticker for row in mapped}),
    }
