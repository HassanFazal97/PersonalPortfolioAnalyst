# Deploy checklist — Forecast Ledger (F1) + scheduler re-enable

Prod: Railway service behind cirvia.ca, single-service topology (one replica,
schedulers in-process). Everything below was read from the code on this
branch; env var names and defaults are exact (`app/config.py`, wiring in
`app/main.py` lifespan, health specs in `app/jobs.py`).

## 1. Goal + current state

**Current state:** `RUN_SCHEDULERS=0` is set in prod. That flag gates the
*entire* scheduler block (`app/main.py` — one `if repo is not None and
settings.run_schedulers:` wraps every job), so today **nothing** scheduled
runs: no digests/SMS (intended), but also no price sync, no fundamentals, no
news, no picks. The flag was designed for a web-vs-worker split topology
(`app/config.py` comment near `run_schedulers`), not as a per-job switch —
using it as a mute button muted the data plane too.

**Goal state:** `RUN_SCHEDULERS=1` with only the cheap data-accumulation jobs
plus the new forecast-ledger job enabled, so the ledger accumulates training
data while **no job texts/emails/pushes the operator** and LLM spend stays
near zero (~$2/day if picks_run is enabled, else ~$0.05/day).

**The tension:** the ledger extracts claims *from pipeline outputs* (picks
runs, digests, deep dives, alerts — `app/agent/forecasts/jobs.py`). With all
generation off, there is nothing to extract. Recommended minimum generator:
**picks_run** (~$2/run typical, $5 hard cap via `PICKS_MAX_COST_USD`, one
global run per weekday, maps into the ledger **deterministically at $0**, and
also feeds the public /track-record page). Digest generation is the optional
second source — see Open decisions.

## 2. Job inventory

Defaults below are the code defaults (`app/config.py`); "" means disabled.
Cost classes: **$0** = pure data/math (yfinance/SEC/DB), **LLM** = Anthropic
spend, **MSG** = can enqueue outbound SMS/email/push (the thing to keep off).

| Job (health name) | Env var | Default | Cost class | Recommended prod setting | Rationale |
|---|---|---|---|---|---|
| morning_digest | `DIGEST_CRON` | `0 9 * * 1-5` | LLM ≤$1.50/user/run + **MSG** | `""` (blank = disabled) | **Fixed on this branch (Aug 20):** the digest scheduler is now guarded like every other job, so `""` cleanly disables it. (Pre-fix builds crash on `""` — the old `0 5 31 2 *` never-fires workaround still works if you must deploy older code.) |
| macro_scan | `MACRO_SCAN_INTERVAL_MINUTES` | `0` | LLM ≤$2/scan + **MSG** (alerts) | leave unset (0) | Already off by default. |
| anomaly_scan | `ANOMALY_SCAN_CRON` | `""` | $0 math + ≤$0.10 Haiku + **MSG** (alerts) | leave unset | Enqueues price-anomaly alerts to the operator's channels. |
| delivery_dispatch | `DELIVERY_INTERVAL_SECONDS` | `30` | $0 (drains queue only) | leave default (30) | Harmless when nothing enqueues; needed for any transactional sends (channel verification). Enqueue sites are digest, anomaly, macro, deep_dive, trial_notices only — all off below. |
| fundamentals_refresh | `FUNDAMENTALS_REFRESH_CRON` | `30 18 * * 1-5` | $0 (yfinance) | leave default | Nightly held-ticker fundamentals warm; default-on already. |
| daily_prices_sync | `DAILY_PRICES_CRON` | `40 18 * * 1-5` | $0 (yfinance) | leave default | **Required by the ledger** — resolution scores against `daily_prices` adjusted closes. |
| news_refresh | `NEWS_REFRESH_CRON` | `50 8 * * *` | LLM ≤$0.05/run (Haiku) | leave default | Persists news_items only, never messages. ~$1.50/mo; keeps the dashboard feed and future digest prose warm. |
| deep_dive | `DEEP_DIVE_CRON` | `""` | LLM ≤$1/run + **MSG** | leave unset | Manual runs still work via API. |
| picks_sync | `PICKS_SYNC_CRON` | `""` | $0 (yfinance universe sync) | `0 20 * * 1-5` | Config-recommended slot, after the held-ticker jobs. Feeds picks_run + valuation. |
| valuation_refresh | `VALUATION_REFRESH_CRON` | `""` | $0 (pure math) | `30 20 * * 1-5` | Config-recommended slot, right after picks_sync (reads what it wrote). |
| picks_run | `PICKS_CRON` | `""` | **LLM ~$2/run typical, $5 cap** — no messaging | `0 7 * * 1-5` (recommended; operator decision) | The ledger's primary $0-to-extract claim source + public track record. ~$42/mo at typical cost. |
| congress_trades_sync | `CONGRESS_TRADES_SYNC_CRON` | `""` | $0 (HTTP only) | `""` — **dead upstream (Aug 24)**: Stock Watcher S3/sites/mirrors all gone; blanked in prod. Existing rows are frozen history; SEC EDGAR (form4/13f) is the live notable-trades source now. |
| form4_sync | `FORM4_SYNC_INTERVAL_MINUTES` | `0` | $0 (SEC HTTP only) | leave `0` for now | **Wired on this branch (Aug 20)** — polls Form 4 for held/watched US tickers. Enable later (e.g. `30`) once the notable-trades surface matters. |
| thirteenf_sync | `THIRTEENF_SYNC_CRON` | `""` | $0 (SEC HTTP only) | leave `""` for now | **Wired on this branch (Aug 20)** — daily poll of the configured whale-fund roster (`THIRTEENF_MANAGER_CIKS`). Cheap to enable anytime (e.g. `0 21 * * 1-5`). |
| **forecast_ledger** | `FORECAST_LEDGER_CRON` | `""` | LLM ≤$0.50/night hard cap (`EXTRACT_MAX_COST_USD`); $0 when only structured sources exist | `10 19 * * 1-5` | New (F1). Must run after DAILY_PRICES_CRON (18:40) so the day's bars exist. Prose pass (Haiku) only fires when digests/deep-dives exist. |
| trial_notices | `TRIAL_NOTICES_CRON` | `0 10 * * *` | $0 gen but **MSG** (SMS/email/push) | `""` (**must be explicitly blanked** — default is non-empty) | Scans trial users and enqueues outbound. Its scheduler *is* guarded (`if settings.trial_notices_cron:`), so blanking is safe. |
| quote_warm | `QUOTE_WARM_INTERVAL_SECONDS` | `90` | $0 (yfinance) | leave default | No-op without dashboard traffic in the last 30 min; market hours only. |
| positions_refresh | `POSITIONS_REFRESH_INTERVAL_MINUTES` | `45` | $0 (SnapTrade) | leave default | No-op without recently-active connected users; market hours only. |

**Net new LLM spend at the recommended settings:** picks_run ~$2/weekday
(~$42/mo) + news_refresh ≤$0.05/day + forecast_ledger ~$0 (deterministic
sources only until digests/dives exist; hard-capped $0.50/night regardless).
No job can text, email, or push.

### ⚠️ Startup-crash warning: `DIGEST_CRON=""` — FIXED on this branch

Historical note: before Aug 20 the digest scheduler was built unconditionally,
so `DIGEST_CRON=""` raised `ValueError` in `CronTrigger.from_crontab("")`
during lifespan startup and Railway crash-looped. **This branch adds the
`if settings.digest_cron:` guard (app/main.py), making `""` the legal off
switch**, and fixes the `/health` spec so morning_digest reports `disabled`
instead of always-enabled. If you ever deploy a pre-fix build, fall back to
the never-firing `0 5 31 2 *` workaround.

## 3. Step-by-step deploy checklist

Assumes the F1 branch is merged/pushed to `main` (Railway auto-deploys from
GitHub; the image's CMD runs `python scripts/migrate.py && exec uvicorn …`,
so migration `035_forecasts` — and `034_notable_investor_trades` if the
previous deploy never shipped — auto-apply at boot, per `Dockerfile` and
`docs/DEPLOY.md` → Migrations).

**Step 1 — set the variables (before pushing the code, or in the same batch;
Railway restarts the service on variable changes, and staged CLI sets apply
together):**

```bash
railway variables \
  --set "RUN_SCHEDULERS=1" \
  --set "DIGEST_CRON=" \
  --set "TRIAL_NOTICES_CRON=" \
  --set "FORECAST_LEDGER_CRON=10 19 * * 1-5" \
  --set "PICKS_SYNC_CRON=0 20 * * 1-5" \
  --set "VALUATION_REFRESH_CRON=30 20 * * 1-5" \
  --set "PICKS_CRON=0 7 * * 1-5" \
  --set "CONGRESS_TRADES_SYNC_CRON=0 17 * * *"
```

Notes:
- `PICKS_CRON` line: omit if the ~$2/day decision is "no" (see Open decisions).
- `CONGRESS_TRADES_SYNC_CRON` line: optional, $0.
- Do **not** set `DAILY_PRICES_CRON`, `FUNDAMENTALS_REFRESH_CRON`,
  `NEWS_REFRESH_CRON`, `DELIVERY_INTERVAL_SECONDS` — their defaults are
  already correct (see table).
- Confirm none of `MACRO_SCAN_INTERVAL_MINUTES`, `ANOMALY_SCAN_CRON`,
  `DEEP_DIVE_CRON` are set to enabled values in the dashboard from earlier
  experiments: `railway variables | grep -E "CRON|INTERVAL|SCHEDULER"`.

**Step 2 — deploy:** push `main` (or `railway redeploy` if the variable change
didn't already trigger one). Keep the service at **1 replica / UVICORN_WORKERS
unset** — with `RUN_SCHEDULERS=1` a second instance double-fires crons
(`docs/DEPLOY.md` → Topology).

**Step 3 — verify migration 035 applied.** Deploy logs should show
`apply 035_forecasts` (or `skip 035_forecasts (already applied)` on a
restart). Belt-and-suspenders from the laptop:

```bash
ENV_FILE=.env.prod .venv/bin/python - <<'EOF'
import asyncio, asyncpg
from app.config import get_settings
async def main():
    s = get_settings()
    dsn = (s.migration_database_url or s.database_url).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn, ssl="require" if s.db_ssl else None)
    print(await conn.fetchval("SELECT version FROM schema_migrations WHERE version='035_forecasts'"))
    print("forecasts rows:", await conn.fetchval("SELECT count(*) FROM forecasts"))
    await conn.close()
asyncio.run(main())
EOF
```

**Step 4 — verify /health.** No auth needed:

```bash
curl -s https://cirvia.ca/health | python3 -m json.tool
```

Expect: `"scheduler": true` (RUN_SCHEDULERS took), and under `"jobs"`:
- `forecast_ledger`, `picks_sync`, `picks_run`: present, state `unknown`
  until each first success, then `live`;
- `daily_prices_sync`, `fundamentals_refresh`, `news_refresh`: `live`/`unknown`;
- `anomaly_scan`, `macro_scan`: `disabled`;
- `morning_digest`, `trial_notices`: `disabled` (both fixed on this branch —
  the digest health spec now respects a blank cron, and valuation_refresh /
  congress_trades_sync / trial_notices / form4_sync / thirteenf_sync all
  gained health-spec entries in `app/jobs.py`).
- `valuation_refresh`, `congress_trades_sync`: `live`/`unknown` if you set
  their crons in Step 2, else `disabled`.
- `form4_sync`, `thirteenf_sync`: `disabled` (until you opt in later).

**Step 5 — one-shot backfill over stored history** (idempotent via
`claim_key`; run from the laptop against prod). The Haiku prose pass makes
outbound HTTPS calls, and the local py3.13 CA store is broken — set
`SSL_CERT_FILE` (documented in `.claude/skills/verify/SKILL.md`; same quirk
noted in `docs/MOBILE_APP_PLAN.md`):

```bash
cd /Users/fazalh/Desktop/PersonalPortfolioAnalyst
ENV_FILE=.env.prod \
SSL_CERT_FILE=$(.venv/bin/python -c 'import certifi; print(certifi.where())') \
.venv/bin/python scripts/backfill_forecasts.py --days 365
```

Add `--no-llm` to backfill only the $0 deterministic sources (picks payloads,
deep-dive typed risks, alerts) and skip the Haiku pass over digest bodies.
The script prints a stats JSON (`inserted`, `resolved`, `extraction_cost_usd`).

**Step 6 — curl the owner calibration route** (owner = `API_TOKEN` bearer):

```bash
curl -s https://cirvia.ca/forecasts/calibration \
  -H "Authorization: Bearer $API_TOKEN" | python3 -m json.tool
```

Expect `{"counts": {...by status...}, "calibration": {...}}`; a 403 means the
token resolved to a non-owner user. Response is cached ~server-side TTL, so
don't expect instant movement after the nightly job.

**Step 7 — next-morning check:** after the first scheduled night, re-check
`/health` (`forecast_ledger.state == "live"`) and confirm **zero outbound**:

```bash
ENV_FILE=.env.prod .venv/bin/python - <<'EOF'
import asyncio, asyncpg
from app.config import get_settings
async def main():
    s = get_settings()
    dsn = s.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn, ssl="require" if s.db_ssl else None)
    rows = await conn.fetch("SELECT status, count(*) FROM outbound_messages WHERE created_at > now() - interval '2 days' GROUP BY 1")
    print([tuple(r) for r in rows])
    await conn.close()
asyncio.run(main())
EOF
```

Anything with status `sent` in that window is a leak — investigate before
leaving it running.

## 4. Rollback — silence everything instantly

```bash
railway variables --set "RUN_SCHEDULERS=0"
```

One variable; the service restarts serving requests only (the same state as
today). All other variables can stay — they're inert without the master flag.
The forecast ledger simply stops accumulating; nothing breaks.

## 5. Open decisions for the operator

1. **picks_run at ~$2/weekday (~$42/mo): yes/no.** It's the only generator
   in the recommended set, and its claims map into the ledger at $0 (no Haiku
   needed). Without it the ledger sits empty except for the backfill. It also
   keeps /track-record fresh. To decline: drop the `PICKS_CRON` line in
   Step 1. A cheaper trial: keep it but set `PICKS_UNIVERSE_LIMIT` for smoke
   sizing, or run it manually a few times via the API first.

2. **Digest generation without delivery — yes, it works, and it's the richer
   ledger source.** Generation and delivery are decoupled at
   `Repo.enqueue_outbound` (`app/db/repo.py`): the digest row is always
   upserted first, and the outbound row is written as **`skipped`** ("no
   preferred notification channel" / "not verified" / "opted out") when the
   user has no usable channel — generation always succeeds. So re-enabling
   `DIGEST_CRON=0 9 * * 1-5` while the operator's account has
   `preferred_channel` unset (or the channel opted out) yields digests that
   feed the ledger's Haiku prose pass at digest LLM cost (≤$1.50/run cap,
   recipients = digest-enabled users with positions, which today is just the
   owner — note `list_digest_recipients` falls back to the owner even with
   nobody enabled) and **zero SMS/email**. Two caveats:
   - **Push is a separate fan-out**: `enqueue_outbound(push=True)` writes one
     row per registered, non-disabled device whose `kinds` include `digest`,
     *regardless* of the preferred-channel decision. If the mobile app is
     installed with digest pushes enabled, digests will still push. Disable
     the device kinds (or `PUSH_ENABLED=false`, which unregisters the
     adapter) first.
   - Opting out / clearing `preferred_channel` is a DB/user-settings change,
     not an env var — do it before flipping the cron.

3. **trial_notices while digest channels are silenced:** kept blanked above.
   If real trials start, re-enable `TRIAL_NOTICES_CRON=0 10 * * *` — it only
   messages users inside trial windows, and dedupes by kind.

4. **The missing `if settings.digest_cron:` guard** in `app/main.py` is worth
   a one-line PR so `DIGEST_CRON=""` becomes a legal off switch and the
   `morning_digest` health spec can honor `enabled`. Until then the Feb-31
   cron is the contract.
