# Cirvia

**Cirvia** (`cirvia.ca`) is an AI portfolio analyst for Canadian investors. It
answers on-demand questions about real holdings via a hand-written tool-using
agent loop, runs every weekday morning to produce a compressed digest, and logs
every model call and tool call to Postgres so any run is fully replayable.

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
| `DELIVERY_INTERVAL_SECONDS` | Outbound dispatcher poll interval (0 disables) |
| `PUBLIC_BASE_URL` | Public origin, e.g. `https://app.example.com` (Twilio webhook signatures) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | SMS channel (all three required) |
| `RESEND_API_KEY` / `EMAIL_FROM` | Email channel (both required) |
| `SNAPTRADE_CLIENT_ID` / `SNAPTRADE_CONSUMER_KEY` | SnapTrade API keys (Wealthsimple sync) |
| `SNAPTRADE_USER_ID` / `SNAPTRADE_USER_SECRET` | Commercial keys only — leave empty for Personal dashboard keys |
| `SNAPTRADE_AUTH_MODE` | `auto` (default), `personal`, or `commercial` |

Generate a token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## Connect Wealthsimple (SnapTrade)

This app syncs your live Wealthsimple holdings through [SnapTrade](https://snaptrade.com) — the same third-party API used by apps like Blossom. No Wealthsimple password is stored in this repo; you authenticate once through SnapTrade's Connection Portal.

### 1. Get SnapTrade API keys

1. Sign up at [dashboard.snaptrade.com](https://dashboard.snaptrade.com) (free tier works for personal use).
2. Copy your **Client ID** and **Consumer Key** into `.env`:
   ```
   SNAPTRADE_CLIENT_ID=...
   SNAPTRADE_CONSUMER_KEY=...
   ```

### 2. Connect Wealthsimple

```bash
python scripts/connect_wealthsimple.py
```

**Personal keys** (what you get from the dashboard SDK flow): only `CLIENT_ID` and
`CONSUMER_KEY` are needed — leave `SNAPTRADE_USER_ID` and `SNAPTRADE_USER_SECRET`
empty. The script prints a browser URL; open it, log into Wealthsimple, and
authorize read access.

**Commercial keys** (multi-user apps): the first run registers a SnapTrade user
and prints `SNAPTRADE_USER_SECRET` to add to `.env`. Run again for the connect URL.

Or via the API (after secrets are in `.env`):

```bash
curl -s localhost:8000/portfolio/connect-url -H "Authorization: Bearer $TOKEN"
```

### 3. Sync holdings

```bash
python scripts/sync_wealthsimple.py
```

This pulls positions from all linked Wealthsimple accounts (TFSA, RRSP, non-registered), maps tickers to Yahoo format, and upserts into the `positions` table. Stale rows are removed.

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

See **Connect Wealthsimple (SnapTrade)** below for the recommended path. To enter
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

## Deploy to the cloud (production)

The morning digest is driven by an **in-process** APScheduler, so the server must
be running at 07:45 (`TZ`) for the digest to generate. Deploy to an always-on
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
   `TZ=America/Toronto`, and the `SNAPTRADE_*` keys if syncing Wealthsimple.
4. **Smoke test** once deployed (replace `$HOST`/`$TOKEN`):
   ```bash
   curl -s $HOST/health                                   # public, no token
   curl -s -X POST $HOST/chat -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d '{"message":"hi"}'
   curl -s -X POST $HOST/digest/run -H "Authorization: Bearer $TOKEN"
   curl -s $HOST/digest/latest -H "Authorization: Bearer $TOKEN"
   ```

**Belt-and-suspenders scheduling (recommended):** rather than trusting the host
to stay warm, add an external cron (Supabase `pg_cron`, cron-job.org, or a
GitHub Actions scheduled workflow) that `POST`s `/digest/run` at 07:45 Toronto.
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
