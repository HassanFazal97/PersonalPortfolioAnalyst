# Cirvia

**Cirvia** (`cirvia.ca`) is an AI portfolio analyst for Canadian investors. It
answers on-demand questions about real holdings via a hand-written tool-using
agent loop (with live token/tool streaming), runs every weekday morning to
produce a compressed digest, and logs every model call and tool call to Postgres
so any run is fully replayable.

On top of that core it layers several capabilities:

- **Chat** — grounded Q&A over your real book, streamed step-by-step. Free and Pro.
- **Morning digest** — a pre-market brief; Pro digests add a per-holding
  breakdown, delivered channel-aware (short by SMS, full by email/Discord/web).
- **Quant risk engine** (Pro) — portfolio-level risk decomposition, tail risk
  (VaR/CVaR), and risk-adjusted performance, computed in pure numpy and narrated
  by the model.
- **Deep Dive** (Pro) — a team of specialist agents researches the whole
  portfolio in parallel, an adversarial critic re-checks their claims, and a
  final agent writes a structured report.
- **Semantic memory** — recall over everything Cirvia has told you before (past
  digests, news, and chat answers) via embeddings.
- **Price-anomaly & macro alerts** — statistical detectors and macro specialists
  surface what changed.

No agent frameworks — the loop, tool dispatch, budgeting, and orchestration are
written by hand. See `PROJECT_SPEC.md` for the full design and
[`docs/AI_ARCHITECTURE.md`](docs/AI_ARCHITECTURE.md) for a tour of the AI
machinery: the agent loop, SSE streaming, the multi-agent Deep Dive pipeline,
pgvector semantic memory, and the eval harness.

Prompt quality is gated by an **eval harness** (`evals/`): golden chat cases
replayed through the real loop with recorded tool fixtures, scored by
deterministic checks plus a rubric-anchored LLM judge, and compared against a
per-`PROMPT_VERSION` baseline (regressions confirmed at N=3 before failing the
run). `python -m evals.run --suite all` — a full run costs ~$0.20.

## Requirements

- Python 3.12+
- A Postgres database (Supabase, or a local Postgres) with the **`pgvector`**
  extension available (used by semantic memory; `migrate.py` enables it)
- An Anthropic API key
- (Optional) a Finnhub API key — without it, news falls back to yfinance
- (Optional) a Voyage AI API key — enables semantic memory/recall; the feature
  stays off if unset
- `numpy` (and `scipy`) are installed with the package and power the quant risk
  engine

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# then edit .env — see Configuration below
```

### Configuration (`.env`)

| Key | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API access |
| `FINNHUB_API_KEY` | News (optional; yfinance fallback if empty) |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `API_TOKEN` | Long random string; required on every request |
| `MODEL` | Defaults to `claude-sonnet-4-6` |
| `CHAT_MAX_ITERATIONS` / `CHAT_MAX_COST_USD` | Chat run budget |
| `DIGEST_MAX_ITERATIONS` / `DIGEST_MAX_COST_USD` | Digest run budget |
| `MAX_TOOL_OUTPUT_TOKENS` | Per-tool output cap (~6000) |
| `DIGEST_CRON` | Cron for the morning digest (`0 9 * * 1-5`) |
| `DEEP_DIVE_CRON` | Cron for the weekly Pro deep-dive fan-out (empty = manual only) |
| `ANOMALY_SCAN_CRON` | Cron for price-anomaly scans, e.g. `30 16 * * 1-5` (empty = manual only) |
| `FUNDAMENTALS_REFRESH_CRON` | Nightly pre-warm of per-ticker fundamentals (`30 18 * * 1-5`; empty = lazy refresh only) |
| `VOYAGE_API_KEY` | Voyage AI embeddings for semantic memory/recall (optional; recall disabled if empty) |
| `EMBEDDING_MODEL` | Voyage embedding model (`voyage-3.5-lite`) |
| `TZ` | `America/Toronto` |
| `DELIVERY_INTERVAL_SECONDS` | Outbound dispatcher poll interval (0 disables) |
| `PUBLIC_BASE_URL` | Public origin, e.g. `https://app.example.com` (Twilio webhook signatures) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | SMS channel (all three required) |
| `RESEND_API_KEY` / `EMAIL_FROM` | Email channel (both required) |
| `SNAPTRADE_CLIENT_ID` / `SNAPTRADE_CONSUMER_KEY` | SnapTrade API keys (brokerage sync) |
| `SNAPTRADE_USER_ID` / `SNAPTRADE_USER_SECRET` | Commercial keys only — leave empty for Personal dashboard keys |
| `SNAPTRADE_AUTH_MODE` | `auto` (default), `personal`, or `commercial` |

Generate a token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## Connect a brokerage (SnapTrade)

This app syncs your live brokerage holdings (Wealthsimple, Questrade, and any other brokerage SnapTrade supports) through [SnapTrade](https://snaptrade.com) — the same third-party API used by apps like Blossom. No brokerage password is stored in this repo; you authenticate once through SnapTrade's Connection Portal.

### 1. Get SnapTrade API keys

1. Sign up at [dashboard.snaptrade.com](https://dashboard.snaptrade.com) (free tier works for personal use).
2. Copy your **Client ID** and **Consumer Key** into `.env`:
   ```
   SNAPTRADE_CLIENT_ID=...
   SNAPTRADE_CONSUMER_KEY=...
   ```

### 2. Connect your brokerage

```bash
python scripts/connect_brokerage.py
```

**Personal keys** (what you get from the dashboard SDK flow): only `CLIENT_ID` and
`CONSUMER_KEY` are needed — leave `SNAPTRADE_USER_ID` and `SNAPTRADE_USER_SECRET`
empty. The script prints a browser URL; open it, pick your brokerage, log in, and
authorize read access.

**Commercial keys** (multi-user apps): the first run registers a SnapTrade user
and prints `SNAPTRADE_USER_SECRET` to add to `.env`. Run again for the connect URL.

Or via the API (after secrets are in `.env`):

```bash
curl -s localhost:8000/portfolio/connect-url -H "Authorization: Bearer $TOKEN"
```

### 3. Sync holdings

```bash
python scripts/sync_brokerage.py
```

This pulls positions from all linked brokerage accounts (TFSA, RRSP, non-registered), maps tickers to Yahoo format, and upserts into the `positions` table. Stale rows are removed.

```bash
curl -s -X POST localhost:8000/portfolio/sync -H "Authorization: Bearer $TOKEN"
```

Re-run sync whenever your holdings change, or before the morning digest if you want the freshest book.

### Manual entry (alternative)

```bash
python scripts/seed_portfolio.py
```

Interactive fallback if you prefer not to use SnapTrade.

## Migrate the database

```bash
python scripts/migrate.py
```

Applies numbered SQL in `app/db/migrations/` and tracks them in
`schema_migrations` (idempotent — safe to re-run).

## Seed your portfolio

See **Connect a brokerage (SnapTrade)** below for the recommended path. To enter
holdings manually instead:

## Run the API

```bash
uvicorn app.main:app --reload
```

Every endpoint requires `Authorization: Bearer $API_TOKEN` — except `/health`,
which is public so platform liveness probes and uptime pingers can reach it.

### First chat

```bash
TOKEN=... # your API_TOKEN
curl -s localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is my total portfolio value in CAD?"}' | jq
```

Response includes the answer, run status, token/cost accounting, and a summary
of tool calls made. Benchmark questions to try:

1. "What's NVDA at right now?"
2. "What's my total portfolio value in CAD?"
3. "Which of my positions moved the most today, and why?"
4. "Is my SHOP drawdown this month unusual versus its typical volatility?"
5. "Any news in the last 3 days I should care about?"

**Streaming.** `POST /chat/stream` runs the same agent and streams
Server-Sent Events — `run_start`, per-tool `tool_start`/`tool_end` (with a
friendly label + input hint), model `text_delta` tokens, and a terminal `done`
event carrying the authoritative answer, cost, and refreshed quota. The web
dashboard uses this to show the agent working live and silently falls back to
plain `POST /chat` if the transport fails. The digest and Deep Dive pipelines
pass no callback and stay on the non-streaming path unchanged.

### Inspect a run (full trajectory)

```bash
curl -s localhost:8000/runs/<run_id> -H "Authorization: Bearer $TOKEN" | jq
python scripts/replay_run.py <run_id>   # pretty-printed from Postgres
```

## Morning digest

Trigger it manually:

```bash
curl -s -X POST localhost:8000/digest/run -H "Authorization: Bearer $TOKEN" | jq
```

It runs plan → investigate → synthesize and delivers a labeled brief
(`PORTFOLIO` / `TOP RISK` / optional `NOTABLE` / `WATCH TODAY`). The scheduler
also runs it automatically on weekdays at 09:00 (`DIGEST_CRON`, `TZ`); cadence is
per plan (Free weekly on Mondays, Pro daily on weekdays).

**Pro digests add a per-holding breakdown.** A deterministic scaffold computes
each holding's stats (day/week move, P&L $ and %), aggregated by ticker across
accounts, and splits them into movers/newsworthy (detailed, each with one
grounded sentence) vs a one-line quiet summary. Delivery is **channel-aware**:
the short core (≤1000 chars) is what goes out by **SMS**, while the full body
(core + `HOLDINGS` section, up to ~4000 chars) is stored and delivered to
**email/Discord** and rendered on the dashboard's *Today's digest* card. Tunable
via `DIGEST_MOVER_THRESHOLD_PCT` and `DIGEST_HOLDINGS_MAX_CHARS`.

Fetch today's digest:

```bash
curl -s localhost:8000/digest/latest -H "Authorization: Bearer $TOKEN" | jq
# 404 until today's digest has been generated
```

## Portfolio risk engine (Pro)

Three Pro-only chat tools expose a portfolio-level quant engine. All numbers are
computed in **pure numpy** under `app/quant/` (I/O-free) from a date-aligned,
CAD-based daily log-returns matrix (USD holdings carry their USD/CAD FX risk);
**the model only narrates the precomputed JSON, never recomputes it**, and always
describes — never advises.

- **`analyze_portfolio_risk`** — Ledoit-Wolf (constant-correlation) shrunk
  covariance → Euler risk decomposition: true portfolio volatility, the
  diversification ratio/benefit, each holding's *risk* contribution vs its
  *capital* weight (hidden concentration), the effective number of independent
  bets, and the most-correlated pairs.
- **`estimate_downside_risk`** — Value at Risk and Conditional VaR (Expected
  Shortfall) at 95%/99% over 1-day and 1-month horizons, in % and CAD (headline
  VaR is Cornish-Fisher fat-tail-adjusted with a validity guard, falling back to
  historical); worst realized day/week/month, max drawdown, and beta-scaled
  market-shock scenarios (−10/−20/−34%).
- **`assess_risk_adjusted_performance`** — Sharpe and Sortino, annualized
  return/volatility, tracking error and information ratio vs the benchmark,
  portfolio beta, and sector-weight exposure.

Ask in chat: "what's actually driving my risk?", "how much could I lose in a
crash?", "what's my Sharpe ratio?". Free chats never receive these tools.

## Deep Dive (Pro)

A multi-agent research report over the whole portfolio. `POST /deep-dive` (202,
returns `{report_id, run_id}`) kicks off a four-stage pipeline:

1. **Plan** — one structured call proposes per-specialist research questions
   tailored to the actual holdings.
2. **Research** — four specialists (**fundamentals, technical, risk,
   news/macro**) run in parallel, each its own budgeted sub-agent with its own
   toolset.
3. **Verify** — an adversarial critic re-checks the load-bearing quantitative
   claims against first-party tools (no web search).
4. **Synthesize** — a final agent merges everything into a structured report
   (`headline`, `overview`, per-specialist `sections` with claim/evidence/
   confidence/verification, `risks`, `opportunities`) plus a short summary that
   is also delivered by SMS/email.

Progress streams over SSE (`GET /deep-dive/{id}/events`, with a reconnect
snapshot) and the report renders on the dashboard. Bounded by
`DEEP_DIVE_MAX_COST_USD` (~$1/run) and `DEEP_DIVE_WEEKLY_LIMIT` (2/week per Pro
user); `DEEP_DIVE_CRON` optionally runs a weekly fan-out. Reports live in
`deep_dive_reports` (per-user, RLS-isolated). Free users get a 403 with an
upgrade prompt.

```bash
curl -s -X POST localhost:8000/deep-dive -H "Authorization: Bearer $TOKEN" | jq
curl -s localhost:8000/deep-dive -H "Authorization: Bearer $TOKEN" | jq   # list
```

## Semantic memory & recall

When `VOYAGE_API_KEY` is set, Cirvia embeds each new digest, stored news item,
and chat answer (Voyage AI embeddings, `input_type="document"`) into a pgvector
`memory_chunks` table — fire-and-forget and fail-open, so an embedding outage
never breaks a digest or chat. The chat agent then gains a **`recall_memory`**
tool (all plans) that semantically searches the user's *own* history and cites
each snippet's date: "what did you tell me about NVDA last month?", "what was in
my digest last week?". It searches history only — live questions still use the
live tools. `scripts/backfill_memory.py` (re)embeds existing rows idempotently
(the recovery path after an outage), capped by `MEMORY_BACKFILL_MAX_COST_USD`.

## Fundamentals & stock detail pages

The dashboard holdings table shows per-holding metrics (portfolio weight,
forward P/E, dividend yield, % off the 52-week high, next earnings date), and
clicking a holding opens `/app/stock/<ticker>` — price chart, valuation /
growth / financial-health cards (or fund cards for ETFs), analyst targets,
your aggregated position, and stored news for that ticker.

Data comes from one yfinance `.info` snapshot per ticker per day, cached in
the global `ticker_fundamentals` table (24h TTL, stale-while-revalidate on
read, nightly pre-warm via `FUNDAMENTALS_REFRESH_CRON`). Derived metrics that
yfinance reports inconsistently are computed in-house: PEG (forward P/E ÷
earnings growth), dividend yield (rate ÷ live price), P/FCF, % off 52-week
high, and a cov/var beta vs `FUNDAMENTALS_BETA_BENCHMARK` when Yahoo has no
beta (common for `.TO` tickers). `GET /portfolio` is untouched — metrics
arrive on a second `GET /portfolio/metrics` call so the holdings table renders
instantly.

## Price-anomaly alerts (statistical, model-free)

Deterministic detectors (ported from Shizen) run over each holding's daily log
returns — a rolling z-score for one-day spikes, CUSUM for slow sustained drifts,
and an optional correlation-divergence check against a benchmark ETF
(`ANOMALY_BENCHMARK_TICKER`). **Math decides, the LLM only narrates**: flagged
holdings are aggregated per user (noisy-OR), one cheap Haiku call writes the
alert body (deterministic fallback if it fails), and the alert lands in the
normal `alerts` + delivery pipeline as category `price_anomaly`. Detection
itself costs $0. Recipients: Pro users + the owner. A 3-day per-ticker cooldown
plus daily fingerprints keep a volatile week from spamming.

```bash
curl -s -X POST localhost:8000/anomaly/scan -H "Authorization: Bearer $TOKEN" | jq
# scheduled: set ANOMALY_SCAN_CRON="30 16 * * 1-5" (after the TSX/NYSE close)
```

Thresholds were chosen with `python scripts/calibrate_detectors.py` (cached
real 5-year history; `--sweep` for the grid, `--refresh` to re-download):

| Detector | Scenario | FP/yr | Median lag (days) | Misses |
|---|---|---:|---:|---:|
| zscore(W=60, k=3.0) | spike | 3.89 | 1 | 2/18 |
| zscore(W=60, k=3.0) | level_shift | 3.89 | 15 | 4/18 |
| zscore(W=60, k=3.0) | variance_burst | 3.89 | 2 | 0/18 |
| cusum(warmup=60, δ=0.5, h=8.0) | spike | 2.73 | 13 | 7/18 |
| cusum(warmup=60, δ=0.5, h=8.0) | level_shift | 2.73 | 11 | 1/18 |
| cusum(warmup=60, δ=0.5, h=8.0) | variance_burst | 2.73 | 5 | 0/18 |

(FP/yr = organic flags per 252 trading days on unmodified history; lag from
synthetic injections scaled to each ticker's trailing σ. CUSUM h=8 over h=6
halves false alarms at identical drift lag — spikes are zscore's job.)

## Deploy to the cloud (production)

The morning digest is driven by an **in-process** APScheduler, so the server must
be running at 09:00 (`TZ`) for the digest to generate. Deploy to an always-on
host — free tiers that spin down on idle will be asleep and silently skip it.

**Single instance only.** Run exactly one container with one uvicorn worker. A
second process (extra replica or `--workers >1`) fires the digest twice and
collides on the `digests.digest_date` unique constraint.

1. **Database:** create a [Supabase](https://supabase.com) project. Use the
   **Session pooler** connection string (IPv4, port 5432) as `DATABASE_URL` and
   set `DB_SSL=true`.
2. **Host:** any Docker host works (the repo ships a `Dockerfile`). Railway is
   the simplest always-on option; Fly.io (`min_machines_running=1`) or a paid
   Render web service are equivalent. Point it at this repo — the image runs
   `scripts/migrate.py` on boot, then `uvicorn`.
3. **Env vars** (set on the host, never committed): `ANTHROPIC_API_KEY`,
   `FINNHUB_API_KEY`, `DATABASE_URL`, `DB_SSL=true`, `API_TOKEN`,
   `TZ=America/Toronto`, the `SNAPTRADE_*` keys if syncing a brokerage, and
   `VOYAGE_API_KEY` if you want semantic memory/recall enabled.
4. **Smoke test** once deployed (replace `$HOST`/`$TOKEN`):
   ```bash
   curl -s $HOST/health                                   # public, no token
   curl -s -X POST $HOST/chat -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d '{"message":"hi"}'
   curl -s -X POST $HOST/digest/run -H "Authorization: Bearer $TOKEN"
   curl -s $HOST/digest/latest -H "Authorization: Bearer $TOKEN"
   ```

`/health` also reports per-job completion staleness under `"jobs"` (each
scheduled job — `morning_digest`, `macro_scan`, `anomaly_scan`,
`delivery_dispatch` — records heartbeats to the `job_heartbeats` table):
`live`/`degraded`/`offline` derived from missed fires, `disabled` when a job
is off. `"ok"` stays db-only so a stale digest never flaps the platform
liveness probe; watch `"jobs_ok"` on your uptime dashboard instead.

**Belt-and-suspenders scheduling (recommended):** rather than trusting the host
to stay warm, add an external cron (Supabase `pg_cron`, cron-job.org, or a
GitHub Actions scheduled workflow) that `POST`s `/digest/run` at 09:00 Toronto.
`/digest/latest` keys on the Toronto date and the digest is idempotent per day,
so a redundant trigger is harmless.

## Delivery — notification channels

Users pick one preferred channel — **SMS (Twilio)**, **Email (Resend)**, or
**Discord (webhook)** — during onboarding (or later from the dashboard's
Delivery card), verify it with a one-time 6-digit code, and the in-process
dispatcher delivers digests and macro alerts there.

How it works:

- `send_digest` and the macro orchestrator enqueue to `outbound_messages`;
  the queue resolves the user's preferred channel at enqueue time (no verified
  channel → the row is recorded as `skipped` and the digest stays
  dashboard-only).
- The dispatcher (`app/delivery/dispatcher.py`) drains the queue every
  `DELIVERY_INTERVAL_SECONDS`, routing rows to provider adapters
  (`app/delivery/adapters/`). Transient failures back off (1m/5m/30m/2h, max
  `DELIVERY_MAX_ATTEMPTS`); permanent ones (bad number, deleted webhook) fail
  immediately with the reason in `last_error`.
- A channel only appears in the UI when its provider creds are configured.
  Discord needs no global creds — users paste their own webhook URL.

### SMS setup (Twilio)

1. Buy a number in the Twilio console and set `TWILIO_ACCOUNT_SID`,
   `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.
2. Point the number's inbound SMS webhook at
   `$PUBLIC_BASE_URL/webhooks/twilio/sms` (handles STOP/START/HELP; requests
   are verified via `X-Twilio-Signature`, and STOP flips the user's
   registration to opted-out so the queue skips them).
3. Compliance is on you operationally: Canadian toll-free verification or US
   A2P 10DLC brand/campaign registration if texting US numbers. Consent is
   captured in-product (required checkbox, timestamped in
   `notification_channels.consent_at`).

### Email setup (Resend)

Set `RESEND_API_KEY` and `EMAIL_FROM` (verify your sending domain in Resend
first; the sandbox `onboarding@resend.dev` works for testing to your own
address).

## Delivery — iPhone Shortcut (pull fallback)

`GET /digest/latest` remains available if you'd rather pull the digest with an
iPhone Shortcuts personal automation:

1. **Shortcuts app → Automation → New (＋) → Personal Automation → Time of Day.**
2. Set **09:15**, **Daily**, and turn **Run Immediately** on (disable "Ask
   Before Running").
3. Add action **Get Contents of URL**:
   - URL: `https://<your-host>/digest/latest`
   - Method: `GET`
   - Headers: add `Authorization` = `Bearer <your API_TOKEN>`
4. Add action **Get Dictionary Value** → key `body` (from the previous result).
5. Add action **Send Message** → Recipient: yourself → Message: the `body`
   value from step 4.
6. Save. Optionally test with **Run**.

If no digest exists yet the endpoint returns 404; the Shortcut simply sends
nothing that morning. The scheduled 09:00 generation runs before the 09:15 pull.

> The original Mac-worker iMessage push (Phase B) was retired in favor of the
> multi-channel dispatcher above (migration `008_retire_imessage.sql`).

## Observability & replay

Every model call and tool call is stored in Postgres (`model_calls`,
`tool_calls`) under an `agent_runs` row, with full request/response JSON. Any run
is reconstructable from the DB alone:

```bash
python scripts/replay_run.py <run_id>
```

## Testing & linting

```bash
pytest        # no live network — all external APIs are mocked
ruff check .
```
