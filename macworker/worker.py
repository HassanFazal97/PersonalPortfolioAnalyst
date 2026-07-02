#!/usr/bin/env python3
"""Mac-side delivery worker (Phase B).

Runs on the user's Mac via launchd. One invocation drains the API outbox:
GET /outbox/pending -> for each message, send it as an iMessage via AppleScript
-> POST /outbox/{id}/ack. Uses only the Python standard library so it needs no
virtualenv on the Mac.

Env:
  PA_API_BASE           API base URL (default http://localhost:8000)
  PA_API_TOKEN          bearer token (required)
  PA_IMESSAGE_RECIPIENT the phone number/email to text (required)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("PA_API_BASE", "http://localhost:8000").rstrip("/")
API_TOKEN = os.environ.get("PA_API_TOKEN", "")
RECIPIENT = os.environ.get("PA_IMESSAGE_RECIPIENT", "")
APPLESCRIPT = str(Path(__file__).resolve().parent / "send.applescript")


def _request(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {API_TOKEN}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else {}


def _send_imessage(body: str) -> bool:
    """Return True on a successful AppleScript send."""
    result = subprocess.run(
        ["osascript", APPLESCRIPT, body, RECIPIENT],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"osascript failed: {result.stderr.strip()}", file=sys.stderr)
    return result.returncode == 0


def drain_once() -> int:
    """Send all pending messages. Returns the count processed."""
    pending = _request("GET", "/outbox/pending").get("messages", [])
    for msg in pending:
        ok = _send_imessage(msg["body"])
        status = "sent" if ok else "failed"
        try:
            _request("POST", f"/outbox/{msg['id']}/ack", {"status": status})
        except urllib.error.HTTPError as exc:
            print(f"ack failed for {msg['id']}: {exc}", file=sys.stderr)
    return len(pending)


def main() -> None:
    if not API_TOKEN or not RECIPIENT:
        raise SystemExit("PA_API_TOKEN and PA_IMESSAGE_RECIPIENT must be set")
    try:
        count = drain_once()
        print(f"processed {count} message(s)")
    except urllib.error.URLError as exc:
        # API unreachable this cycle; launchd will retry next interval.
        print(f"outbox poll failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
