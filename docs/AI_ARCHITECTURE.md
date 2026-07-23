# AI Architecture

How Cirvia's AI machinery is put together, and where each piece lives. No
agent frameworks anywhere — the loop, orchestration, budgets, streaming,
retrieval, and evals are all hand-written and inspectable.

## The agent loop (`app/agent/loop.py`)

Single entrypoint `run_agent()`: call model → execute requested tools →
feed results back → repeat until the model answers or the budget trips.

- **Tool dispatch** (`safe_dispatch`): JSON-schema validation, per-tool
  timeouts, one retry on transient failures, output truncation. Tool errors
  become `is_error` tool_results the model adapts to — only infrastructure
  failures abort a run.
- **Budgets** (`app/agent/budget.py`): every run carries iteration + USD caps
  sized by plan; an exhausted run degrades to a tools-off summary turn instead
  of dying. Per-run cost feeds monthly fair-use caps and user-facing quotas.
- **Observability** (`app/observability/logging.py`): every model call and
  tool call is persisted (`agent_runs` / `model_calls` / `tool_calls`), each
  run stamped with the `PROMPT_VERSION` that produced it — any trajectory is
  replayable via `GET /runs/{id}`.
- **Prompt caching**: the system prefix carries a `cache_control` breakpoint,
  so loop iterations 2+ read the static prefix at 0.1× input price.
- **Two injection seams**: `on_event` (streaming, below) and `dispatch`
  (the eval harness swaps in recorded fixture tools per case).

## Streaming (`app/streaming.py`, `app/agent/events.py`)

Chat runs stream over SSE (`POST /chat/stream`): the loop emits typed events
(`tool_start`/`tool_end` with friendly labels, `text_delta`, `server_tool`,
terminal `done` with cost + quota) through an optional `on_event` callback, a
queue-draining generator frames them as SSE, and the dashboard renders live
agent steps before the answer arrives. A dead browser can never abort a run —
the driver task owns persistence and billing; the UI falls back to the JSON
endpoint on transport failure. Long jobs (Deep Dive) publish coarser progress
through an in-process `ProgressBroker`, with a persisted snapshot so a page
refresh mid-run rehydrates exactly.

## Multi-agent Deep Dive (`app/agent/deep_dive/`)

A four-stage research pipeline over the user's whole portfolio:

```
                       ┌─ fundamentals analyst ─┐
plan (structured JSON) ├─ technical analyst    ─┤   critic (adversarial      synthesizer
one call, per-agent    ├─ risk analyst         ─┼─▶ fact-checker re-runs  ─▶ (structured
research questions     └─ news/macro analyst   ─┘   tools on claims)         JSON report)
                          (parallel run_agent sub-loops,
                           own toolsets + budgets)
```

- Specialists run **in parallel** (`asyncio.gather`), each a full `run_agent`
  sub-loop with a role prompt, a tool subset (the risk analyst gets the quant
  engine; news/macro gets server-side web search), and its own small budget.
- The **critic** re-checks the most load-bearing quantitative claims against
  first-party tools and marks each `verified`/`challenged` — verification
  badges the UI renders on every finding.
- Failure degrades, never aborts: a dead specialist → `partial` report with
  `failed_specialists`; a dead critic → findings marked `unverified`.
- One anchor `agent_runs` row accumulates every stage's tokens/cost, so the
  run reports its true total; the weekly Pro quota counts report rows.

## Semantic memory / RAG (`app/memory/`, `app/tools/recall.py`)

Everything the product tells a user — morning digests, persisted news, chat
answers — is chunked and embedded (Voyage `voyage-3.5-lite`, plain httpx, no
SDK) into a pgvector `memory_chunks` table (HNSW, cosine). At chat time the
`recall_memory` tool embeds the query asymmetrically (`input_type="query"`)
and runs hybrid retrieval: vector similarity + ticker (jsonb containment) +
date-window + source-type filters, tenant-scoped by both an explicit filter
and row-level security.

- Ingestion is fire-and-forget and fail-open: an embedding outage can never
  break a digest or chat; `scripts/backfill_memory.py` heals gaps idempotently.
- The table is a pure derived cache — an embedding-model change is truncate +
  re-backfill, never data loss.

## Eval harness (`evals/`)

Eval-driven development for the prompts: `python -m evals.run --suite all`.

- **Golden chat cases** (`evals/golden/chat_cases.yaml`): frozen portfolio
  context + recorded tool fixtures, replayed through the REAL agent loop with
  fake tools (the `dispatch` seam) and real model calls. Case mix includes
  hallucination traps (asking about unheld tickers) and advice-refusal probes.
- **Deterministic checks in code** (must-mention / must-not-mention /
  expected tool trajectory), then an **LLM judge** does rubric-anchored
  absolute scoring: binary criteria + hallucination detection against the
  fixtures as ground truth. The judge prompt is versioned separately from
  product prompts so judge changes can't masquerade as product changes.
- **Regression gate**: results are compared per `PROMPT_VERSION` against a
  checked-in baseline; a newly-failing case is re-run at N=3 and must fail
  2/3 to confirm (bounds nondeterminism). Exit codes gate CI
  (`.github/workflows/evals.yml`, manual + weekly — not per-PR, cost).
- **Classifier suite**: exact-match accuracy + confusion matrix for the Haiku
  news-signal tagger over labeled headlines. A full run costs ~$0.20.

## Background intelligence

- **Morning digest** (`app/agent/digest_pipeline.py`): plan → investigate
  (sub-agent loops) → synthesize, terminating only via the `send_digest` tool,
  with a guaranteed fallback delivery on failure.
- **Macro alerts** (`app/agent/macro/`): four web-searching specialists run
  once globally, then a cheap per-user Haiku pass maps events to holdings.
- **Anomaly alerts** (`app/detectors/`): model-free statistics (z-score,
  CUSUM, benchmark divergence); Haiku only narrates what the math found.
- **News classification** (`app/tools/classify.py`): batched Haiku tagging
  (warning/opportunity/neutral + salience) with a shared headline cache.

## Cost discipline (the theme that ties it together)

Model choice per task (Sonnet for reasoning, Haiku for classification),
prompt caching in the loop, per-run budgets, per-stage budgets inside
pipelines, monthly per-user caps, quotas surfaced in the UI, and embeddings
priced/tracked like model calls (`EMBEDDING_PRICES`, `Budget.record_flat_cost`).
Every dollar a run spends is attributed and queryable.
