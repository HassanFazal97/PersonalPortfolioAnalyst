"""Interactive CLI to enter real holdings into the ``positions`` table.

Usage:  python scripts/seed_portfolio.py

Prompts for ticker / quantity / avg cost / currency / account per position,
normalizes the ticker to Yahoo format, and upserts on (ticker, account).
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.repo import Repo  # noqa: E402
from app.tools.tickers import normalize_ticker  # noqa: E402

VALID_ACCOUNTS = {"TFSA", "RRSP", "taxable"}


def _prompt_decimal(label: str) -> Decimal:
    while True:
        raw = input(label).strip()
        try:
            return Decimal(raw)
        except InvalidOperation:
            print("  Not a number, try again.")


def _prompt_account() -> str:
    while True:
        raw = input("Account (TFSA/RRSP/taxable): ").strip()
        # Preserve canonical casing for the known set.
        for valid in VALID_ACCOUNTS:
            if raw.lower() == valid.lower():
                return valid
        print(f"  Must be one of {sorted(VALID_ACCOUNTS)}.")


def _prompt_currency() -> str:
    raw = input("Currency [CAD]: ").strip().upper()
    return raw or "CAD"


async def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set. Populate .env first.")

    repo = Repo(settings.database_url, ssl=settings.db_ssl)
    count = 0
    try:
        print("Enter positions. Leave ticker blank to finish.\n")
        while True:
            raw_ticker = input("Ticker (Yahoo format, blank to stop): ").strip()
            if not raw_ticker:
                break
            try:
                ticker = normalize_ticker(raw_ticker)
            except ValueError as exc:
                print(f"  {exc}")
                continue
            quantity = _prompt_decimal("Quantity: ")
            avg_cost = _prompt_decimal("Average cost per share: ")
            currency = _prompt_currency()
            account = _prompt_account()

            await repo.upsert_position(
                ticker=ticker,
                quantity=quantity,
                avg_cost=avg_cost,
                currency=currency,
                account=account,
            )
            count += 1
            print(f"  saved {ticker} ({account})\n")
    finally:
        await repo.dispose()
    print(f"Done. {count} position(s) upserted.")


if __name__ == "__main__":
    asyncio.run(main())
