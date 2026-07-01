#!/usr/bin/env python3
"""Register a SnapTrade user (if needed) and print the Wealthsimple connect URL.

Usage:
  python scripts/connect_wealthsimple.py
  python scripts/connect_wealthsimple.py --register-only

Prerequisites:
  1. Create a free SnapTrade developer account at https://dashboard.snaptrade.com
  2. Add SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY to .env
  3. After --register-only (or first run), add the printed SNAPTRADE_USER_SECRET
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.integrations.snaptrade.client import (  # noqa: E402
    SnapTradeError,
    SnapTradeService,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect Wealthsimple via SnapTrade")
    parser.add_argument(
        "--register-only",
        action="store_true",
        help="Only register a SnapTrade user and print credentials (skip portal URL)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.snaptrade_client_id or not settings.snaptrade_consumer_key:
        raise SystemExit(
            "Set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY in .env first.\n"
            "Get them from https://dashboard.snaptrade.com → API Keys."
        )

    service = SnapTradeService(settings)

    if not settings.snaptrade_user_secret:
        print("No SNAPTRADE_USER_SECRET found — registering a new SnapTrade user...\n")
        creds = service.register_user()
        print("Add these lines to your .env file:\n")
        print(f"SNAPTRADE_USER_ID={creds['userId']}")
        print(f"SNAPTRADE_USER_SECRET={creds['userSecret']}\n")
        print("Save .env, then run this script again to get the connect URL.")
        return

    if args.register_only:
        print("SNAPTRADE_USER_SECRET is already set. Nothing to register.")
        return

    try:
        url = service.connection_portal_url()
    except SnapTradeError as exc:
        raise SystemExit(str(exc)) from exc

    print("Open this URL in your browser to link Wealthsimple (expires in ~5 minutes):\n")
    print(url)
    print(
        "\nAfter connecting, run:  python scripts/sync_wealthsimple.py"
    )


if __name__ == "__main__":
    main()
