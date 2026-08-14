"""Seed the App Store / Play review account.

Usage:  python scripts/seed_review_account.py --email review@cirvia.ca

A reviewer will not link a real brokerage through SnapTrade — they have no
account to link — so an app whose every screen is empty behind a connect
button reads as broken and gets rejected. This gives the review account a
real-looking portfolio, a digest, a watchlist, and the Pro plan.

**Pro is the point.** On Free, Model Picks and the deep-dive screens answer
402, and a reviewer hitting a paywall they cannot pass reports a broken app.
The plan is written through ``apply_subscription_state`` — the same single
writer the Stripe webhook uses — but with no subscription id, so there is
nothing to cancel and no webhook to reconcile afterwards.

The account itself must already exist — sign up once through the normal flow
(so Supabase owns the credentials), then run this against that email.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.repo import Repo  # noqa: E402


async def _user_by_email(repo: Repo, email: str):
    """Look up by email. The repo has no such method — nothing in the app
    needs one, because every request already knows its user id."""
    async with repo._session() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

# A believable Canadian book: a couple of index funds, a bank, an energy name,
# and one US mega-cap, across two account types. Cost bases are set so the
# screen shows a mix of gains and losses rather than a suspicious all-green.
POSITIONS = [
    # ticker,  qty,   avg cost, currency, account
    ("VFV.TO", "42", "298.40", "CAD", "TFSA"),
    ("XIU.TO", "95", "34.10", "CAD", "TFSA"),
    ("TD.TO", "64", "82.15", "CAD", "RRSP"),
    ("ENB.TO", "108", "49.60", "CAD", "RRSP"),
    ("NVDA", "18", "118.40", "USD", "taxable"),
    ("SHOP.TO", "31", "142.80", "CAD", "taxable"),
]

WATCHLIST = ["AAPL", "CNQ.TO", "BN.TO"]

DIGEST_BODY = """PORTFOLIO: -0.6% today (-$318)

TOP RISK
Rate-sensitive names are 38% of the book ahead of Thursday's Bank of Canada
decision; ENB and TD would feel a hawkish surprise most.

NOTABLE
- NVDA -2.1%, extending yesterday's slide after the AI copyright ruling; still
  the largest single-name exposure at 18%.
- VFV +0.8% with the S&P 500's rebound: the index sleeve did the lifting today.
- TD upgraded at a major bank on credit normalization.

WATCH TODAY
Bank of Canada rate decision, 9:45 AM ET, direct read-through to ENB, TD, and
the REIT sleeve.

HOLDINGS
NVDA - $9,120 - 18.2% of book - -2.1% today
Extends yesterday's slide on the copyright ruling; no new company-specific
news this morning.

VFV - $14,480 - 28.9% of book - +0.8% today
Tracking the S&P 500's rebound; nothing name-specific.

TD - $6,240 - 12.4% of book - +1.2% today
Upgraded this morning on credit normalization; watch the BoC decision Thursday.

QUIET: 3 others little changed; largest ENB -0.3%.
"""


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="the review account's email")
    parser.add_argument(
        "--keep-plan",
        action="store_true",
        help="don't force the Pro plan (not recommended: Pro screens 402 on Free)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set. Populate .env first.")

    repo = Repo(settings.database_url, ssl=settings.db_ssl)
    try:
        user = await _user_by_email(repo, args.email)
        if user is None:
            raise SystemExit(
                f"No account for {args.email}. Sign up through the app first so "
                "Supabase owns the credentials, then re-run this."
            )
        user_id = user.id
        print(f"Seeding {args.email} ({user_id})")

        for ticker, qty, cost, currency, account in POSITIONS:
            await repo.upsert_position(
                ticker=ticker,
                quantity=Decimal(qty),
                avg_cost=Decimal(cost),
                currency=currency,
                account=account,
                user_id=user_id,
            )
        print(f"  {len(POSITIONS)} positions")

        for ticker in WATCHLIST:
            await repo.add_watchlist_ticker(user_id, ticker)
        print(f"  {len(WATCHLIST)} watchlist tickers")

        run_id = await repo.create_run(
            trigger="digest",
            user_message="[review account seed]",
            model=settings.model,
            prompt_version="seed",
            user_id=user_id,
        )
        await repo.upsert_digest(
            run_id=run_id,
            body=DIGEST_BODY,
            digest_date=date.today(),
            user_id=user_id,
        )
        print("  today's digest")

        if not args.keep_plan:
            # Through the single writer the Stripe webhook uses, but with no
            # subscription id: nothing to cancel, no webhook to reconcile, and
            # the trial state is settled the same way a real upgrade settles it.
            await repo.apply_subscription_state(
                user_id,
                plan="pro",
                subscription_id=None,
                current_period_end=None,
                cancel_at_period_end=False,
            )
            print("  plan: pro (no Stripe subscription)")

        await repo.update_user_preferences(
            user_id,
            digest_enabled=True,
            digest_send_time=datetime.strptime("09:00", "%H:%M").time(),
            timezone="America/Toronto",
        )
        await repo.update_user_profile(
            user_id,
            archetype="long_term_growth",
            risk_tolerance=5,
            horizon="years",
            experience="1_5y",
            goals=["grow_long_term", "retirement"],
            completed_at=datetime.now(timezone.utc),
        )
        print("  preferences + investor profile")
    finally:
        await repo.dispose()

    print(
        "\nDone. Check every tab signed in as this account before submitting — "
        "an empty screen is the most common review rejection."
    )


if __name__ == "__main__":
    asyncio.run(main())
