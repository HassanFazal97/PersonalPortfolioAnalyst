"""Measure dashboard endpoint latency (the before/after yardstick for perf work).

Usage:
    .venv/bin/python scripts/perf_dashboard.py --base http://localhost:8399 \
        --token <bearer>  [--rounds 5]

Pass a REAL Supabase access token (devtools → Application → localStorage →
sb-*-auth-token → access_token) to exercise the full JWT + user-resolution
path; the owner API_TOKEN short-circuits get_or_create_user (app/main.py)
and under-reports auth overhead.

Prints per-endpoint p50/p95 over N rounds, plus the wall time of one
"dashboard load": all endpoints fired concurrently (matches the parallel
client) and the old serial shape (me → rest) for comparison.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
from time import perf_counter

import httpx

ENDPOINTS = [
    "/me",
    "/portfolio",
    "/portfolio/metrics",
    "/portfolio/status",
    "/watchlist",
    "/digest/latest",
    "/news?limit=20",
    "/chat/history",
    "/me/notifications",
    "/deep-dive?limit=1",
    "/dashboard/bootstrap",  # 404 until Phase 2 lands; reported as such
]


async def _timed(client: httpx.AsyncClient, path: str) -> tuple[float, int]:
    t0 = perf_counter()
    resp = await client.get(path)
    return (perf_counter() - t0) * 1000, resp.status_code


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8399")
    ap.add_argument("--token", required=True)
    ap.add_argument("--rounds", type=int, default=5)
    args = ap.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"}
    async with httpx.AsyncClient(
        base_url=args.base, headers=headers, timeout=60
    ) as client:
        samples: dict[str, list[float]] = {p: [] for p in ENDPOINTS}
        statuses: dict[str, int] = {}
        for _ in range(args.rounds):
            for path in ENDPOINTS:
                ms, status = await _timed(client, path)
                samples[path].append(ms)
                statuses[path] = status

        print(f"{'endpoint':32} {'status':>6} {'p50 ms':>9} {'p95 ms':>9}")
        for path in ENDPOINTS:
            vals = sorted(samples[path])
            p50 = statistics.median(vals)
            p95 = vals[min(len(vals) - 1, int(len(vals) * 0.95))]
            print(f"{path:32} {statuses[path]:>6} {p50:>9.1f} {p95:>9.1f}")

        live = [p for p in ENDPOINTS if statuses[p] == 200]

        t0 = perf_counter()
        await asyncio.gather(*(_timed(client, p) for p in live))
        parallel_ms = (perf_counter() - t0) * 1000

        t0 = perf_counter()
        await _timed(client, "/me")
        await asyncio.gather(
            *(_timed(client, p) for p in live if p != "/me")
        )
        serial_ms = (perf_counter() - t0) * 1000

        print(f"\nfull load, all parallel:      {parallel_ms:>8.1f} ms")
        print(f"full load, /me-gated (old):   {serial_ms:>8.1f} ms")


if __name__ == "__main__":
    asyncio.run(main())
