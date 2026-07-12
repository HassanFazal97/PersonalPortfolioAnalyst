#!/usr/bin/env python3
"""Sync live brokerage holdings from SnapTrade into the positions table.

Usage:  python scripts/sync_brokerage.py
        python scripts/sync_brokerage.py --no-refresh
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.repo import Repo  # noqa: E402
from app.integrations.snaptrade.sync import sync_brokerage_positions  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sync brokerage holdings via SnapTrade")
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip triggering a SnapTrade holdings refresh before reading positions",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set. Populate .env first.")

    repo = Repo(settings.database_url, ssl=settings.db_ssl)
    try:
        summary = await sync_brokerage_positions(
            repo, settings=settings, refresh=not args.no_refresh
        )
    finally:
        await repo.dispose()

    print(json.dumps(summary, indent=2))
    print(
        f"\nSynced {summary['positions_upserted']} position(s) "
        f"across {summary['accounts_synced']} account(s)."
    )
    if summary["positions_removed"]:
        print(f"Removed {summary['positions_removed']} stale position(s).")


if __name__ == "__main__":
    asyncio.run(main())
