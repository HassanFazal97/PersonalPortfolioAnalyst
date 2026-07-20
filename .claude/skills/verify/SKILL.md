---
name: verify
description: Launch and drive the Cirvia FastAPI app locally to verify changes end-to-end.
---

# Verifying Cirvia locally

## Launch

```bash
DIGEST_CRON="59 23 31 12 *" NEWS_REFRESH_CRON="" ANOMALY_SCAN_CRON="" \
FUNDAMENTALS_REFRESH_CRON="" MACRO_SCAN_INTERVAL_MINUTES=0 DELIVERY_INTERVAL_SECONDS=0 \
.venv/bin/uvicorn app.main:app --port 8399 --log-level warning
```

Gotchas, in order of how much they hurt:

- **`.env` points at the PRODUCTION Supabase DB and real delivery providers
  (Twilio/Resend/Stripe/Anthropic).** Always disable the schedulers with the
  env overrides above — a local `DELIVERY_INTERVAL_SECONDS` dispatcher will
  drain the prod outbound queue and actually send SMS/email.
- `DIGEST_CRON` cannot be empty (the digest scheduler always starts and
  requires a valid 5-field cron); use a far-future cron like `59 23 31 12 *`.
  The other crons accept `""` to disable.
- If `app/db/models.py` has columns newer than the prod schema (unapplied
  migrations), every user-row read 500s — authenticated routes are unusable
  until `python scripts/migrate.py` runs (a deploy decision, don't run it
  against prod casually).
- No Docker/local Postgres on this machine as of 2026-07: DB-backed flows
  can't be driven against a scratch DB.

## Drive

- Auth: `Authorization: Bearer $API_TOKEN` (from `.env`) resolves to the
  owner (quota-exempt, always Pro). There is no HS256 `SUPABASE_JWT_SECRET`,
  so a free/pro end-user JWT cannot be minted locally — end-user-only paths
  (quota 402s, trial states) are exercised via TestClient tests instead.
- DB-free surfaces: `/`, `/pricing`, `/health`, and the `/app/*` HTML shells
  (they're static shells; check for the expected elements/JS with grep).
- `POST /chat` (owner) runs the real agent loop against Anthropic — costs
  real money; keep to 1–2 calls, then inspect `GET /runs/{run_id}` for the
  tool trajectory.

## Test-suite env leakage

Tests read the developer `.env` through pydantic-settings. When simulating
"unconfigured", monkeypatch env vars to `""` (which overrides the file), never
`delenv`. og:url assertions need `PUBLIC_BASE_URL=https://...` and a module
reload (see tests/test_head_meta.py's client fixture).
