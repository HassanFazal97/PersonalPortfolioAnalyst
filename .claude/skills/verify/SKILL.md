---
name: verify
description: Launch and drive the Cirvia FastAPI app locally to verify changes end-to-end.
---

# Verifying Cirvia locally

## Launch

`.env` is the **dev profile**: it points at the local Supabase stack, sets
`RUN_SCHEDULERS=0` (no schedulers, no delivery dispatcher), and leaves all
outbound providers (Twilio/Resend/SnapTrade/Discord) blank. Prod credentials
live in `.env.prod` — never launch the app with `ENV_FILE=.env.prod`.

```bash
supabase start   # if not already running (local DB :54322, Auth/API :54321)
SSL_CERT_FILE=$(.venv/bin/python -c 'import certifi; print(certifi.where())') \
.venv/bin/python -m uvicorn app.main:app --port 8399 --log-level warning
```

Confirm the startup log prints `RUN_SCHEDULERS=0 — serving requests only`.

Always `.venv/bin/python -m uvicorn`, never `.venv/bin/uvicorn` — the venv
carries both 3.12 and 3.13 trees and the uvicorn entry script's shebang points
at 3.12, where nothing is installed (same reason as `python -m pytest`).

Gotchas:

- `SSL_CERT_FILE` (above) is required for outbound HTTPS (Anthropic, quotes) —
  the py3.13 system CA store on this machine is broken.
- If `app/db/models.py` has columns newer than the local schema, run
  `python scripts/migrate.py` (applies to the local stack; idempotent).
- Fresh local DB? `python scripts/seed_portfolio.py` seeds positions.
- To exercise scheduler behavior specifically, override per-run:
  `RUN_SCHEDULERS=1 DIGEST_CRON="59 23 31 12 *" …` — deliveries then only go
  to local adapters (none registered), so nothing real sends.

## Drive

- Owner auth: `Authorization: Bearer $API_TOKEN` (from `.env`, value
  `dev-local-token`) resolves to the owner (quota-exempt, always Pro).
- End-user auth: sign up in the browser at `http://localhost:8399/app` — local
  Supabase Auth has email confirmations disabled, so any fake email works.
  Free/pro/trial states can be driven with real end-user JWTs now.
- DB-free surfaces: `/`, `/pricing`, `/health`, and the `/app/*` HTML shells
  (static shells; check for the expected elements/JS with grep).
- `POST /chat` (owner) runs the real agent loop against Anthropic — costs
  real money; keep to 1–2 calls, then inspect `GET /runs/{run_id}` for the
  tool trajectory.

## Test suite

Tests never read `.env`: `tests/conftest.py` pins `ENV_FILE=tests/env.test`
(safe placeholders) and scrubs inherited secret env vars. To simulate
"unconfigured", monkeypatch env vars to `""` (process env overrides the file).
og:url assertions need `PUBLIC_BASE_URL=https://...` and a module reload (see
tests/test_head_meta.py's client fixture). The live-DB tenant-isolation test
is explicit opt-in:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres \
.venv/bin/python -m pytest tests/test_tenant_isolation.py
```
