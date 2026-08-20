"""One-shot forecast-ledger backfill over stored pipeline history.

Runs the same extraction + resolution as the nightly job, with the lookback
widened to cover everything already in digests / deep_dive_reports / alerts /
stock_picks_runs. Idempotent (claim_key), so re-running is safe.

Usage:  python scripts/backfill_forecasts.py [--days 365] [--no-llm]

--no-llm skips the Haiku prose pass (digest bodies, dive findings) and
backfills only the $0 deterministic sources.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.forecasts.jobs import run_forecast_ledger  # noqa: E402
from app.auth.context import set_current_user_id  # noqa: E402
from app.config import DEFAULT_USER_ID, get_settings  # noqa: E402
from app.db.repo import Repo  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set. Populate .env first.")

    client = None
    if not args.no_llm and settings.anthropic_api_key:
        from app.agent.anthropic_client import shared_client

        client = shared_client()

    repo = Repo(settings.database_url, ssl=settings.db_ssl)
    set_current_user_id(DEFAULT_USER_ID)
    try:
        stats = await run_forecast_ledger(
            repo, settings, client=client, lookback_days=args.days
        )
    finally:
        set_current_user_id(None)
        await repo.dispose()
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
