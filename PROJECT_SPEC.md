# PORTFOLIO ANALYST AGENT — Project Specification

**Handover document for an autonomous coding agent (Claude Code).**
Read this entire document before writing any code. When this spec and your instincts conflict, follow the spec. When the spec is silent, choose the simplest option that doesn't foreclose later phases.

---

## 1. Mission

Build a personal AI portfolio analyst for a single user (the owner of this repo). The system:

1. Answers on-demand questions about the user's real stock portfolio ("How am I doing today? Should I care about this NVDA news?") via a tool-using agent loop.
2. Proactively runs every weekday morning, decides what's worth investigating, researches it, and delivers a compressed digest to the user's phone via iMessage.
3. Logs every model call and tool call to Postgres so trajectories are fully replayable — this observability layer is a first-class product requirement, not instrumentation garnish.

This is a **learning-grade but production-quality** project: the owner is using it to master agent engineering. Therefore: no agent frameworks (no LangChain, no LlamaIndex, no CrewAI, no SDK "agent" helpers). The agent loop, tool dispatch, budgeting, and orchestration are written by hand. Libraries are fine for everything else (HTTP, DB, scheduling).

**Explicit non-goals:** no trade execution, ever. No multi-user support. No auth beyond a single static API bearer token. No streaming responses in v1.

---

## 2. Design principles (apply everywhere)

1. **Errors flow into the conversation, not up the stack.** A failed tool call returns `is_error: true` with a human-readable message as the tool result; the model decides how to proceed. Only infrastructure failures (DB unreachable, auth invalid) abort a run.
2. **Every run has a budget.** Max iterations, max USD cost, per-tool timeouts. A run that hits its budget ends gracefully with a partial answer and `status='budget_exceeded'`.
3. **Log everything, replay anything.** Full request/response JSON for every model call. Any past run must be reconstructable from Postgres alone.
4. **Tool outputs are truncated and normalized** before reaching the model. Nothing returns more than ~6,000 tokens. All external data is reshaped into stable internal schemas at the tool boundary.
5. **Prompts are versioned constants** in code (`prompts.py`), each with a `PROMPT_VERSION` string stored on every run. Never inline prompt strings elsewhere.
6. **Tickers are stored in Yahoo Finance format everywhere** (`NVDA`, `SHOP.TO`, `RY.TO`). Normalize at input boundaries.
7. **Timezone:** all scheduling and "today" logic is `America/Toronto`. Timestamps in the DB are `timestamptz` (UTC).

---

## 3. Stack

| Layer | Choice | Notes |
|---|---|---|
| API | FastAPI (Python 3.12), uvicorn | async throughout |
| DB | Postgres via Supabase | SQLAlchemy 2.0 async + asyncpg; plain SQL migrations in `db/migrations/` numbered `001_...sql` |
| LLM | Anthropic API, `claude-sonnet-4-6` | model name in config, never hardcoded at call sites |
| Market data | `yfinance` | wrapped behind `tools/market.py`; in-process 60s TTL quote cache |
| News | Finnhub free tier (fallback: yfinance `.news`) | normalized to internal schema |
| Scheduling | APScheduler (in-process, cron trigger) | keep a stub interface so Trigger.dev can replace it later |
| Delivery | Phase A: iPhone Shortcuts pull. Phase B: Mac-side worker + AppleScript push | see §9 |
| Config | pydantic-settings, `.env` | `.env.example` committed, `.env` gitignored |
| Tests | pytest + pytest-asyncio | external APIs mocked; no live network in tests |
| Lint/format | ruff | default config |

---

## 4. Repository layout

```
portfolio-agent/
├── app/
│   ├── main.py                # FastAPI app factory, routes, scheduler startup
│   ├── config.py              # pydantic-settings: keys, model name, budgets, tz
│   ├── agent/
│   │   ├── loop.py            # core agent loop (single entrypoint: run_agent)
│   │   ├── planner.py         # morning-digest planning step (Phase 3)
│   │   ├── synthesizer.py     # digest compression step (Phase 3)
│   │   ├── prompts.py         # ALL prompts + PROMPT_VERSION constants
│   │   └── budget.py          # Budget class: tokens, cost, iterations
│   ├── tools/
│   │   ├── registry.py        # TOOL_SCHEMAS list + async dispatch table
│   │   ├── portfolio.py       # get_portfolio
│   │   ├── market.py          # get_quote, get_price_history (+ cache)
│   │   ├── news.py            # search_news (Finnhub client + normalizer)
│   │   └── digest.py          # send_digest terminal tool (Phase 3)
│   ├── db/
│   │   ├── models.py          # SQLAlchemy models mirroring §6 exactly
│   │   ├── repo.py            # all DB access functions; no raw queries elsewhere
│   │   └── migrations/        # 001_init.sql, 002_..., applied by scripts/migrate.py
│   ├── delivery/
│   │   ├── shortcuts.py       # GET /digest/latest support (Phase A)
│   │   └── imessage.py        # queue for Mac worker (Phase B)
│   └── observability/
│       └── logging.py         # run/model_call/tool_call writers
├── macworker/                 # Phase B only: small poller that runs on the user's Mac
│   ├── worker.py              # polls API for queued messages, sends via osascript
│   └── send.applescript
├── scripts/
│   ├── migrate.py
│   ├── seed_portfolio.py      # interactive CLI to enter real holdings
│   └── replay_run.py          # pretty-print a full trajectory by run_id
├── tests/
├── .env.example
├── pyproject.toml
└── README.md                  # setup instructions, written last
```

---

## 5. The agent loop (`app/agent/loop.py`)

Single async entrypoint:

```python
async def run_agent(
    user_message: str,
    *,
    trigger: str,              # 'chat' | 'digest'
    system_prompt: str,
    tools: list[dict],
    budget: Budget,
    db: Repo,
) -> AgentResult
```

Behavior:

1. Create an `agent_runs` row (`status='running'`), get `run_id`.
2. Loop up to `budget.max_iterations`:
   a. Call the Anthropic Messages API with the system prompt, accumulated `messages`, and `tools`.
   b. Record usage into `budget`; persist the full request/response via `observability`.
   c. If `stop_reason != "tool_use"`: extract text, finalize run as `completed`, return.
   d. Otherwise execute **all** tool_use blocks in the turn via `safe_dispatch`, append the assistant content block and a user turn of tool_results, continue.
3. On budget breach: append a final user message instructing the model to summarize findings so far in one turn *without tools*, make one last call, finalize as `budget_exceeded`.
4. On unhandled exception: finalize as `error` with the traceback stored, re-raise.

`safe_dispatch(name, input) -> (result_str, error_str | None)` must implement, in order: schema validation of input → per-tool timeout (default 10s, configurable) → one retry with 1s backoff on timeout/connection errors only → output truncation to `MAX_TOOL_OUTPUT_TOKENS` (config, default ≈6000 tokens ≈ 24k chars, truncate with an explicit `"[truncated N chars]"` suffix) → JSON-serialize non-string results.

`AgentResult` carries: `run_id`, `answer`, `status`, `iterations`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`.

Cost computation lives in `budget.py` with per-model price constants in config. Default budgets: chat runs — 10 iterations / $0.50; digest runs — 25 iterations / $1.50.

---

## 6. Data model (`db/migrations/001_init.sql`)

```sql
CREATE TABLE positions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker      text NOT NULL,               -- Yahoo format
  quantity    numeric NOT NULL,
  avg_cost    numeric NOT NULL,            -- per share, position currency
  currency    text NOT NULL DEFAULT 'CAD',
  account     text NOT NULL,               -- 'TFSA' | 'RRSP' | 'taxable'
  updated_at  timestamptz DEFAULT now(),
  UNIQUE (ticker, account)
);

CREATE TABLE transactions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker      text NOT NULL,
  side        text NOT NULL CHECK (side IN ('buy','sell')),
  quantity    numeric NOT NULL,
  price       numeric NOT NULL,
  fees        numeric DEFAULT 0,
  account     text NOT NULL,
  executed_at timestamptz NOT NULL
);

CREATE TABLE agent_runs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trigger        text NOT NULL,            -- 'chat' | 'digest'
  user_message   text NOT NULL,
  final_answer   text,
  status         text NOT NULL DEFAULT 'running',
                 -- running|completed|budget_exceeded|max_iterations|error
  iterations     int,
  input_tokens   int,
  output_tokens  int,
  cost_usd       numeric,
  latency_ms     int,
  model          text NOT NULL,
  prompt_version text NOT NULL,
  error_detail   text,
  created_at     timestamptz DEFAULT now()
);

CREATE TABLE model_calls (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id     uuid NOT NULL REFERENCES agent_runs(id),
  iteration  int NOT NULL,
  request    jsonb NOT NULL,               -- full request body sent
  response   jsonb NOT NULL,               -- full response content
  usage      jsonb NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE tool_calls (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id     uuid NOT NULL REFERENCES agent_runs(id),
  iteration  int NOT NULL,
  tool_name  text NOT NULL,
  input      jsonb NOT NULL,
  output     jsonb,
  is_error   boolean DEFAULT false,
  latency_ms int,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE digests (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id       uuid NOT NULL REFERENCES agent_runs(id),
  body         text NOT NULL,              -- final text, <= 900 chars
  digest_date  date NOT NULL UNIQUE,       -- America/Toronto date
  delivered    boolean DEFAULT false,
  delivered_at timestamptz,
  delivery_channel text,                   -- 'shortcuts' | 'imessage'
  created_at   timestamptz DEFAULT now()
);

CREATE TABLE outbound_messages (            -- Phase B queue for Mac worker
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  body       text NOT NULL,
  status     text NOT NULL DEFAULT 'queued', -- queued|sent|failed
  attempts   int DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  sent_at    timestamptz
);

CREATE INDEX ON model_calls (run_id);
CREATE INDEX ON tool_calls (run_id);
CREATE INDEX ON agent_runs (trigger, created_at DESC);
```

---

## 7. Tools

Implement exactly these five. Schemas live in `tools/registry.py`; the description strings below are load-bearing (they steer tool selection) — copy them, then refine only with evidence from real trajectories.

**`get_portfolio`** — no arguments. Returns all positions joined with live quotes: ticker, quantity, avg_cost, currency, account, last_price, market_value, unrealized_pnl, unrealized_pnl_pct, day_change_pct. Description: *"Returns the user's current holdings with live valuations. Always call this before making any claim about what the user owns or how their portfolio is performing."*

**`get_quote`** — `{tickers: string[]}`. Batch snapshot: last price, day change %, previous close, volume. Description instructs the model to batch tickers into one call.

**`get_price_history`** — `{ticker: string, days: int (5–365)}`. Daily OHLCV plus computed fields: period return %, max drawdown %, annualized volatility of daily returns. (Compute these in Python — do not make the model do arithmetic.) Description must include: *"Do NOT use for current price — use get_quote."*

**`search_news`** — `{query: string, lookback_days: int = 3 (max 30), max_results: int = 8 (max 20)}`. Returns normalized `{headline, source, url, published_at, summary}` items. Deduplicate near-identical headlines. Never return full article text.

**`send_digest`** — `{body: string}` (digest runs only; not exposed to chat runs). Validates `len(body) <= 900` chars; on violation returns an error tool_result telling the model to shorten, which is the enforcement mechanism for digest length. On success writes the `digests` row and, in Phase B, enqueues to `outbound_messages`. This is the terminal action of a digest run.

FX: portfolio valuation must handle USD+CAD positions. Fetch `USDCAD=X` via yfinance inside `get_portfolio` and report totals in CAD with the rate noted.

---

## 8. Morning digest pipeline (`agent/planner.py`, `agent/synthesizer.py`)

Scheduled weekdays at **07:45 America/Toronto** via APScheduler. Skip weekends; do not bother with market-holiday detection in v1.

Three stages, all logged under one `agent_runs` row (`trigger='digest'`):

**Stage 1 — Plan (one model call, no tools).** Input: current positions with day/week moves, yesterday's digest body (if any), today's date. Output: strict JSON `{"investigations": [{"question": str, "why": str}]}` — 2 to 4 items. Parse defensively (strip code fences); on parse failure, retry once with an error-corrective message, then fall back to a single generic investigation ("notable news across all holdings, last 24h").

**Stage 2 — Investigate.** Run each investigation through `run_agent` sub-loops (chat toolset, no send_digest), each with a small budget (5 iterations / $0.30). Sequential execution is fine in v1; note concurrency as a TODO.

**Stage 3 — Synthesize + send (one loop with only send_digest exposed).** Input: the investigation findings + yesterday's digest. The prompt requires: ≤900 chars, plain text (no markdown — iMessage), lead with the single most important item, reference continuity where real ("extends yesterday's slide"), include total portfolio day move, end with one "watch today" line. The model must call `send_digest` to finish.

If the whole pipeline fails, send a fallback message through the delivery channel: "Digest failed this morning — check /runs for details." Silent failure is unacceptable for a daily-habit product.

---

## 9. Delivery

**Phase A — Shortcuts pull (ship first).**
`GET /digest/latest` → `{date, body, generated_at}` of today's digest, 404 if none yet. The user configures an iPhone Shortcuts personal automation (08:05 daily → Get Contents of URL with bearer token header → Send Message to self). Document the exact Shortcut steps in README.

**Phase B — Mac worker push (two-way ready).**
`macworker/worker.py`: a ~100-line poller that runs on the user's Mac via launchd. Every 60s: `GET /outbox/pending` → for each message, `osascript send.applescript "<body>"` → `POST /outbox/{id}/ack`. Three failed attempts → `status='failed'`. Include the launchd plist in the repo. The AppleScript targets the user's own number from `.env` on the Mac side.
Incoming-message reading (chat.db) is explicitly **out of scope** for this handover; leave a stubbed `POST /inbound` endpoint that runs a chat agent and enqueues the reply, so the worker can be extended later.

---

## 10. API surface

All endpoints require `Authorization: Bearer $API_TOKEN`.

```
POST /chat                { message }            → AgentResult + tool_call summaries
GET  /runs/{run_id}                              → full ordered trajectory
GET  /runs?trigger=&limit=                       → recent runs, metadata only
GET  /digest/latest                              → today's digest (Phase A)
POST /digest/run                                 → manually trigger the pipeline (testing)
GET  /outbox/pending                             → Phase B worker
POST /outbox/{id}/ack     { status }             → Phase B worker
POST /inbound             { message }            → stub, runs chat agent, enqueues reply
GET  /health                                     → { ok, db, scheduler }
```

---

## 11. Configuration (`.env.example`)

```
ANTHROPIC_API_KEY=
FINNHUB_API_KEY=
DATABASE_URL=postgresql+asyncpg://...
API_TOKEN=                      # long random string
MODEL=claude-sonnet-4-6
CHAT_MAX_ITERATIONS=10
CHAT_MAX_COST_USD=0.50
DIGEST_MAX_ITERATIONS=25
DIGEST_MAX_COST_USD=1.50
MAX_TOOL_OUTPUT_TOKENS=6000
DIGEST_CRON=45 7 * * 1-5
TZ=America/Toronto
```

---

## 12. Testing requirements

- Unit tests for: budget accounting/stop conditions; tool input validation; output truncation; ticker normalization; digest length enforcement (send_digest rejects 901 chars); planner JSON parsing including the fence-stripping and retry path.
- An agent-loop integration test with a **mocked Anthropic client** that scripts a 3-turn trajectory (tool_use → tool_use with one erroring tool → final text) and asserts: correct message assembly, error surfaced as `is_error` tool_result, all rows written to a test DB.
- A digest pipeline test with mocked model + market data proving a digest row is created and ≤900 chars.
- No test may hit the live Anthropic, Yahoo, or Finnhub APIs.

---

## 13. Build order & acceptance criteria

Work in this order; each milestone must pass before the next begins.

**M1 — Foundations.** Config, DB models, migrations runner, seed script, `/health`. ✓ when: `scripts/migrate.py` builds the schema from scratch and `seed_portfolio.py` inserts positions interactively.

**M2 — Tools.** market.py, news.py, portfolio.py with normalization, caching, truncation + their unit tests. ✓ when: each tool callable directly with clean output, tests green.

**M3 — Agent loop.** loop.py, budget.py, safe_dispatch, full observability writes, `POST /chat`, `GET /runs/{id}`, `scripts/replay_run.py`. ✓ when: the five benchmark questions below run end-to-end against live APIs (manual check) and the mocked integration test passes.

**M4 — Digest pipeline.** planner, synthesizer, send_digest, scheduler, `POST /digest/run`, `GET /digest/latest`. ✓ when: a manual trigger produces a ≤900-char digest grounded in real data and stores it.

**M5 — Delivery A.** Bearer auth on all routes, README Shortcut instructions. ✓ when: curl with token retrieves the digest; without token → 401.

**M6 — Delivery B.** outbox endpoints, macworker/, launchd plist, README section. ✓ when: worker poll-send-ack cycle passes against a fake queue (AppleScript execution manually verified by the owner).

**Benchmark questions (M3 manual acceptance):**
1. "What's NVDA at right now?"
2. "What's my total portfolio value in CAD?"
3. "Which of my positions moved the most today, and why?"
4. "Is my SHOP drawdown this month unusual versus its typical volatility?"
5. "Any news in the last 3 days I should care about?"

**Definition of done for the handover:** all milestones ✓, ruff clean, tests green, README covers setup → seeding → first chat → Shortcut setup → Mac worker, and `replay_run.py` can pretty-print any historical trajectory.

---

## 14. Future phases (do NOT build now — but do not foreclose)

- **Memory (Phase 2):** episodic recall of past conclusions, semantic store over gathered research (Qdrant), multi-turn chat state. Keep `run_agent` message assembly factored so a memory-retrieval step can prepend context later.
- **Multi-agent (Phase 4):** specialist news/fundamentals/technical agents under an orchestrator. The planner→investigate→synthesize digest pipeline is the seam where this slots in.
- **Evals (Phase 5):** scoring digests against subsequent market outcomes; prompt-version A/B over logged trajectories. This is why full request JSON is stored — never "optimize" that away.