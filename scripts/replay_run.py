"""Pretty-print a full agent trajectory by run_id, reconstructed from Postgres.

Usage:  python scripts/replay_run.py <run_id>
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db.repo import Repo  # noqa: E402

RULE = "=" * 72


def _short(value, limit: int = 800) -> str:
    text = value if isinstance(value, str) else json.dumps(value, indent=2, default=str)
    return text if len(text) <= limit else text[:limit] + f"\n  ... [{len(text) - limit} more chars]"


async def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/replay_run.py <run_id>")
    run_id = uuid.UUID(sys.argv[1])

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set. Populate .env first.")

    repo = Repo(settings.database_url)
    try:
        run, model_calls, tool_calls = await repo.get_run_trajectory(run_id)
    finally:
        await repo.dispose()

    if run is None:
        raise SystemExit(f"No run found with id {run_id}")

    print(RULE)
    print(f"RUN {run.id}  [{run.trigger}]  status={run.status}")
    print(f"model={run.model}  prompt_version={run.prompt_version}")
    print(
        f"iterations={run.iterations}  tokens={run.input_tokens}in/{run.output_tokens}out"
        f"  cost=${run.cost_usd}  latency={run.latency_ms}ms"
    )
    print(f"user_message: {run.user_message}")
    print(RULE)

    tools_by_iter: dict[int, list] = {}
    for tc in tool_calls:
        tools_by_iter.setdefault(tc.iteration, []).append(tc)

    for mc in model_calls:
        print(f"\n--- iteration {mc.iteration} | MODEL CALL ---")
        stop = mc.response.get("stop_reason") if isinstance(mc.response, dict) else None
        print(f"stop_reason={stop}  usage={mc.usage}")
        content = mc.response.get("content", []) if isinstance(mc.response, dict) else []
        for block in content:
            btype = block.get("type")
            if btype == "text":
                print(f"  [text] {_short(block.get('text', ''))}")
            elif btype == "tool_use":
                print(f"  [tool_use] {block.get('name')}({_short(block.get('input'), 200)})")
        for tc in tools_by_iter.get(mc.iteration, []):
            flag = "ERROR" if tc.is_error else "ok"
            print(f"\n  --- TOOL {tc.tool_name} [{flag}] {tc.latency_ms}ms ---")
            print(f"  input:  {_short(tc.input, 200)}")
            print(f"  output: {_short(tc.output)}")

    print(f"\n{RULE}")
    print(f"FINAL ANSWER:\n{run.final_answer}")
    if run.error_detail:
        print(f"\nERROR DETAIL:\n{run.error_detail}")
    print(RULE)


if __name__ == "__main__":
    asyncio.run(main())
