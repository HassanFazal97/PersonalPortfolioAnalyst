#!/usr/bin/env python3
"""Print the SnapTrade Connection Portal URL to link a brokerage.

Usage:
  python scripts/connect_brokerage.py

Prerequisites:
  1. Create a SnapTrade account at https://dashboard.snaptrade.com
  2. Choose SDKs and copy CLIENT_ID + CONSUMER_KEY into .env
  3. Personal keys (dashboard SDK flow): no user registration needed.
     Commercial keys: run with --register-only first to get USER_SECRET.
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
    is_personal_key_mode,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect a brokerage via SnapTrade")
    parser.add_argument(
        "--register-only",
        action="store_true",
        help="Commercial keys only: register a SnapTrade user and print credentials",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.snaptrade_client_id or not settings.snaptrade_consumer_key:
        raise SystemExit(
            "Set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY in .env first.\n"
            "Get them from https://dashboard.snaptrade.com → API Keys."
        )

    service = SnapTradeService(settings)

    if is_personal_key_mode(settings):
        print("Personal SnapTrade key detected — no user registration needed.\n")
    elif not settings.snaptrade_user_secret:
        print("Commercial key: registering a SnapTrade user...\n")
        try:
            creds = service.register_user()
        except SnapTradeError as exc:
            raise SystemExit(str(exc)) from exc
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

    print("Open this URL in your browser to link your brokerage (expires in ~5 minutes):\n")
    print(url)
    print("\nAfter connecting, run:  python scripts/sync_brokerage.py")


if __name__ == "__main__":
    main()
