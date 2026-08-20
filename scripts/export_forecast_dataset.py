"""Export resolved forecasts as (context, trace, claim, outcome) JSONL.

The flywheel's exit valve: each line pairs one resolved claim with the full
reasoning trace of the run that produced it (model_calls store the complete
request — system prompt + messages — and tool_calls the evidence gathered),
ready for outcome-filtered fine-tuning work later. Written now, years before
any training run, so the export path is exercised and its gaps surface early.

Usage:  python scripts/export_forecast_dataset.py [--out forecasts.jsonl]
        [--outcome hit|miss] [--limit 5000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.context import set_current_user_id  # noqa: E402
from app.config import DEFAULT_USER_ID, get_settings  # noqa: E402
from app.db.repo import Repo  # noqa: E402


def _claim_payload(f) -> dict:
    return {
        "id": str(f.id),
        "source": f.source,
        "claim_type": f.claim_type,
        "claim_text": f.claim_text,
        "tickers": f.tickers,
        "primary_ticker": f.primary_ticker,
        "direction": f.direction,
        "horizon_days": f.horizon_days,
        "as_of_date": f.as_of_date.isoformat(),
        "confidence_verbal": f.confidence_verbal,
        "probability": float(f.probability) if f.probability is not None else None,
        "extractor": f.extractor,
        "extractor_version": f.extractor_version,
        "pipeline_prompt_version": f.pipeline_prompt_version,
        "source_content_hash": f.source_content_hash,
    }


def _outcome_payload(f) -> dict:
    return {
        "status": f.status,
        "outcome": f.outcome,
        "realized_value": float(f.realized_value) if f.realized_value is not None else None,
        "benchmark_value": float(f.benchmark_value) if f.benchmark_value is not None else None,
        "brier": float(f.brier) if f.brier is not None else None,
        "resolution_detail": f.resolution_detail,
        "resolver_version": f.resolver_version,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="forecast_dataset.jsonl")
    parser.add_argument("--outcome", choices=["hit", "miss"], default=None)
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set. Populate .env first.")

    repo = Repo(settings.database_url, ssl=settings.db_ssl)
    set_current_user_id(DEFAULT_USER_ID)
    written = 0
    try:
        forecasts = await repo.list_forecasts(status="resolved", limit=args.limit)
        # One trajectory fetch per distinct producing run, not per claim.
        trajectories: dict = {}
        with open(args.out, "w") as fh:
            for f in forecasts:
                if args.outcome and f.outcome != args.outcome:
                    continue
                if f.run_id not in trajectories:
                    run, model_calls, tool_calls = await repo.get_run_trajectory(f.run_id)
                    trajectories[f.run_id] = {
                        "run": {
                            "trigger": run.trigger if run else None,
                            "model": run.model if run else None,
                            "prompt_version": run.prompt_version if run else None,
                        },
                        "context": model_calls[0].request if model_calls else None,
                        "trace": [
                            {"iteration": mc.iteration, "response": mc.response}
                            for mc in model_calls
                        ],
                        "tools": [
                            {
                                "iteration": tc.iteration,
                                "tool": tc.tool_name,
                                "input": tc.input,
                                "output": tc.output,
                            }
                            for tc in tool_calls
                        ],
                    }
                fh.write(
                    json.dumps(
                        {
                            "claim": _claim_payload(f),
                            "outcome": _outcome_payload(f),
                            **trajectories[f.run_id],
                        },
                        default=str,
                    )
                    + "\n"
                )
                written += 1
    finally:
        set_current_user_id(None)
        await repo.dispose()
    print(f"wrote {written} tuples to {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
