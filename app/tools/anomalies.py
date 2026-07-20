"""scan_anomalies tool: the statistical detectors, on demand from chat.

Thin wrapper over the anomaly scanner used by the scheduled scan — same
z-score / CUSUM / divergence detectors, same thresholds — so chat answers
about "anything unusual?" agree with the alerts the user receives.
"""

from __future__ import annotations

from typing import Any

from app.agent.anomaly.scanner import scan_tickers
from app.tools.tickers import normalize_tickers

# Each ticker costs a live daily-history fetch; keep chat calls bounded.
MAX_TICKERS = 8


async def scan_anomalies(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    tickers = payload.get("tickers")
    if tickers:
        tickers = normalize_tickers(tickers)
    else:
        if ctx is None or getattr(ctx, "repo", None) is None:
            raise RuntimeError("scan_anomalies requires database access")
        positions = await ctx.repo.list_positions(
            user_id=getattr(ctx, "user_id", None)
        )
        tickers = sorted({p.ticker for p in positions})
    if not tickers:
        return {"flags": {}, "clean": [], "note": "No tickers to scan."}

    skipped = tickers[MAX_TICKERS:]
    tickers = tickers[:MAX_TICKERS]

    flags_by_ticker = await scan_tickers(tickers, settings=ctx.settings)
    out: dict[str, Any] = {
        "flags": {
            ticker: [flag.model_dump() for flag in flags]
            for ticker, flags in flags_by_ticker.items()
        },
        # Scanned with nothing flagged — lets the model say "nothing unusual"
        # with confidence instead of guessing from absence.
        "clean": [t for t in tickers if t not in flags_by_ticker],
        "history_days": ctx.settings.anomaly_history_days,
    }
    if skipped:
        out["note"] = (
            f"Scanned the first {MAX_TICKERS} tickers; skipped: "
            f"{', '.join(skipped)}."
        )
    return out
