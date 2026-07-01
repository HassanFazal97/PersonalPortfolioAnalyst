# Portfolio Analyst Agent

A personal, single-user AI portfolio analyst. It answers on-demand questions
about your real holdings via a hand-written tool-using agent loop, runs every
weekday morning to produce a compressed digest, and logs every model call and
tool call to Postgres so any run is fully replayable.

No agent frameworks — the loop, tool dispatch, budgeting, and orchestration are
written by hand. See `PROJECT_SPEC.md` for the full design.

## Requirements

- Python 3.12+
- A Postgres database (Supabase, or a local Postgres)
- An Anthropic API key
- (Optional) a Finnhub API key — without it, news falls back to yfinance

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
| `DIGEST_CRON` | Cron for the morning digest (`45 7 * * 1-5`) |
| `TZ` | `America/Toronto` |
| `IMESSAGE_RECIPIENT` | Phase B only: your own number, on the Mac |

Generate a token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## Migrate the database

```bash
python scripts/migrate.py
```

Applies numbered SQL in `app/db/migrations/` and tracks them in
`schema_migrations` (idempotent — safe to re-run).

## Seed your portfolio

```bash
python scripts/seed_portfolio.py
```

Interactive: enter ticker (Yahoo format — `NVDA`, `SHOP.TO`, `RY.TO`), quantity,
average cost, currency, and account (`TFSA` / `RRSP` / `taxable`). Upserts on
`(ticker, account)`.

## Run the API

```bash
uvicorn app.main:app --reload
```

Every endpoint requires `Authorization: Bearer $API_TOKEN`.

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

It runs plan → investigate → synthesize and delivers a ≤900-char digest. The
scheduler also runs it automatically on weekdays at 07:45 (`DIGEST_CRON`, `TZ`).

Fetch today's digest:

```bash
curl -s localhost:8000/digest/latest -H "Authorization: Bearer $TOKEN" | jq
# 404 until today's digest has been generated
```

## Delivery — Phase A: iPhone Shortcut (pull)

Deliver the digest to yourself with an iPhone Shortcuts personal automation
(no Mac required):

1. **Shortcuts app → Automation → New (＋) → Personal Automation → Time of Day.**
2. Set **08:05**, **Daily**, and turn **Run Immediately** on (disable "Ask
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
nothing that morning. The scheduled 07:45 generation runs before the 08:05 pull.

## Testing & linting

```bash
pytest        # no live network — all external APIs are mocked
ruff check .
```
