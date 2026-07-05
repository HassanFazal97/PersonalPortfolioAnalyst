# Deploy & Activation Runbook

How to deploy the Portfolio Analyst Agent and turn on multi-user auth + RLS.
Host is **Railway** (single container). The image runs migrations, then serves.

> **One replica only.** The morning digest and macro scan are driven by an
> in-process scheduler; a second instance would double-fire. Keep it at 1
> replica / 1 uvicorn worker (see `Dockerfile`).

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Claude API |
| `FINNHUB_API_KEY` | recommended | company news (falls back to yfinance) |
| `DATABASE_URL` | yes | app runtime DB connection (`postgresql+asyncpg://…`) |
| `DB_SSL` | yes (Supabase) | `true` |
| `API_TOKEN` | yes | service/owner bearer token (cron, Mac worker, single-user) |
| `SUPABASE_URL` | multi-user | `https://<ref>.supabase.co` — enables per-user JWT auth via JWKS |
| `SUPABASE_JWT_SECRET` | legacy only | HS256 shared-secret fallback; leave unset on asymmetric projects |
| `SUPABASE_JWT_AUD` | no | JWT audience, default `authenticated` |
| `MIGRATION_DATABASE_URL` | RLS switch | owner connection used only for migrations (see below) |
| `BROKER_SECRETS_KEY` | Phase 3 | Fernet key for encrypting per-user SnapTrade secrets |
| `MACRO_SCAN_INTERVAL_MINUTES` | no | `0` disables in-process macro scan; e.g. `60` for hourly |
| `MACRO_MAX_ITERATIONS` / `MACRO_MAX_COST_USD` | no | macro scan budget caps |
| `MODEL` / `CLASSIFIER_MODEL` / `MACRO_MODEL` | no | model overrides |
| `TZ` / `DIGEST_CRON` | no | schedule (default `America/Toronto`, `45 7 * * 1-5`) |
| `SNAPTRADE_*` | no | Wealthsimple sync |

Auth mode is implicit: if neither `SUPABASE_URL` nor `SUPABASE_JWT_SECRET` is
set, only `API_TOKEN` works (single-user). Set `SUPABASE_URL` to accept per-user
Supabase JWTs alongside the service token.

---

## Migrations

The container runs `python scripts/migrate.py && uvicorn …` on boot, so
migrations apply automatically. `scripts/migrate.py` is idempotent (tracks
applied versions in `schema_migrations`) and connects via
`MIGRATION_DATABASE_URL` if set, else `DATABASE_URL`.

To run manually against Supabase from your laptop:
```bash
DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<pw>@aws-0-us-east-1.pooler.supabase.com:5432/postgres \
DB_SSL=true python scripts/migrate.py
```
Use the **Session pooler** (port 5432) or a direct connection — not the
transaction pooler (asyncpg prepared statements aren't supported there).

Current migrations: `001_init`, `002_multi_tenant`, `003_alerts`, `004_auth`.

---

## Deploy (single-user, no RLS enforcement)

1. Push to `main` (Railway auto-deploys from GitHub).
2. Set env vars: `ANTHROPIC_API_KEY`, `FINNHUB_API_KEY`, `DATABASE_URL`,
   `DB_SSL=true`, `API_TOKEN`.
3. Wait for the deploy to go green; check `GET /health` → `{"db": true, …}`.

Data is already scoped per user in application code (`WHERE user_id = …`), so
this is safe for a single user. RLS is enabled in the schema but **dormant** —
the app connects as the table owner, which bypasses it.

---

## Activate multi-user auth (Supabase JWT)

1. Set `SUPABASE_URL=https://<ref>.supabase.co` and redeploy.
2. Verify token resolution with `/auth/whoami`:
   ```bash
   # service/owner token
   curl -H "Authorization: Bearer $API_TOKEN" https://<host>/auth/whoami
   # -> {"user_id":"00000000-…-0001","email":"owner@localhost","is_owner":true}

   # a real Supabase user access token (mint via the auth API with your
   # publishable key, or Dashboard → Authentication → Users)
   curl -H "Authorization: Bearer <supabase-access-token>" https://<host>/auth/whoami
   # -> {"user_id":"<app uuid>","email":"<their email>","is_owner":false}
   ```
   Supabase's asymmetric (ES256) tokens are verified against the project JWKS at
   `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`; key rotation needs no redeploy.

At this point auth works but RLS still isn't enforced (still on the owner role).

---

## Turn on RLS enforcement (restricted DB role)

Makes tenant isolation a database guarantee, not just app-code discipline.
Because migrations need DDL (owner) but the app should be restricted, the two
use different connections.

1. **Push** the code that supports `MIGRATION_DATABASE_URL` before switching.
2. **Create the role** (Supabase SQL editor, as owner). Pick your own strong
   password (e.g. `openssl rand -base64 24`) — no ownership, no `BYPASSRLS`:
   ```sql
   create role portfolio_app with login password '<STRONG_PASSWORD>';
   grant usage on schema public to portfolio_app;
   grant select, insert, update, delete on all tables in schema public to portfolio_app;
   grant usage, select on all sequences in schema public to portfolio_app;
   alter default privileges in schema public
     grant select, insert, update, delete on tables to portfolio_app;
   alter default privileges in schema public
     grant usage, select on sequences to portfolio_app;
   ```
3. **Set Railway variables:**
   - `MIGRATION_DATABASE_URL` = the owner URL (`postgres.<ref>:…`).
   - `DATABASE_URL` = the restricted role (pooler username is `<role>.<ref>`):
     ```
     postgresql+asyncpg://portfolio_app.<ref>:<STRONG_PASSWORD>@aws-0-us-east-1.pooler.supabase.com:5432/postgres
     ```
   Redeploy.
4. **Verify:** `GET /health` → `db:true`; owner `/chat` still returns your
   positions; a Supabase user `/chat` returns "No positions on record". If
   `db:false`, the role can't connect or is missing a grant — revert
   `DATABASE_URL` to the owner URL and re-check the grants.

How it works: a SQLAlchemy `after_begin` hook sets `app.current_user_id` per
transaction from the authenticated request (owner for background jobs); the RLS
policies filter on it. Under the owner role this is a no-op; under
`portfolio_app` it enforces.

---

## Rotate secrets

Treat as compromised anything pasted into a terminal transcript or chat:
- **DB password** — Supabase → Settings → Database → Reset; update `DATABASE_URL`
  / `MIGRATION_DATABASE_URL`.
- **`API_TOKEN`** — regenerate, update the Railway var and any caller (Shortcut,
  cron, Mac worker).

The Supabase **publishable** key and `SUPABASE_URL` are public — safe to share.
Never expose the Supabase **secret** key or the JWT signing key.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `/auth/whoami` → 404 | old code deployed — push and redeploy |
| `/auth/whoami` → 401 with a JWT | `SUPABASE_URL` unset/wrong, token expired, or wrong project |
| `/health` `db:false` after role switch | restricted role password mismatch or missing grant |
| Migrations fail on boot after role switch | `MIGRATION_DATABASE_URL` not set to the owner connection |
| Supabase signup rejects the email | Supabase blocks example/reserved domains — use a real domain or create the user in the dashboard |
