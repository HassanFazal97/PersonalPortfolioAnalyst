# Multi-Tenant Roadmap — Cirvia → SaaS

Direction: evolve the single-user personal agent into a multi-tenant product
where users sign up, connect a brokerage, and receive scheduled texts about
their own portfolio.

This is a planning doc, not a spec. No code changes implied yet.

## Where the code stands today (the honest baseline)

| Concern | Today | Multi-tenant needs |
|---|---|---|
| Tenancy | No `user_id` anywhere | `user_id` FK on every table + RLS |
| Auth | One shared `API_TOKEN` bearer (`app/main.py:82`) | Per-user accounts, sessions |
| Scheduling | One in-process APScheduler, one cron job | Per-user fan-out by timezone/send-time |
| Delivery | iMessage via personal Mac worker | Twilio SMS + consent/compliance |
| Cost | `agent_runs.cost_usd` per run (good!) | Per-user caps + Stripe billing |
| Broker secrets | Single set in `.env` | Per-user, encrypted at rest |

Doors already left open: `app/scheduler.py` is explicitly a swappable stub, and
SnapTrade commercial mode is multi-user by design.

## Suggested migration order

1. **`user_id` everywhere + RLS** — fix `positions UNIQUE (ticker, account)` →
   `(user_id, ticker, account)` and `digests.digest_date UNIQUE` →
   `(user_id, digest_date)`. Row-Level Security so a bug can't cross tenants.
2. **Real auth** — replace the shared token with per-user identity
   (Supabase Auth / Clerk). Endpoints go from "is this the token" to "which user."
3. **Twilio + consent** — start A2P 10DLC registration *immediately* (slow), and
   build TCPA opt-in + STOP/HELP before texting anyone.
4. **Per-user scheduling** — see deep dive below. This removes the "single
   instance only" constraint for generation.
5. **Stripe billing + per-user cost caps** — extend existing `cost_usd` tracking.

Non-negotiables that come with touching finance: "not financial advice"
disclaimers, privacy policy, encrypted broker secrets, and (eventually) SOC 2.

---

## Deep dive: per-user scheduling

### The problem with today's model
`DigestScheduler` runs **one** APScheduler cron job in the API process. For N
users that breaks on three axes:

- **Timezones / send-times** — users want their digest at *their* 9:00am, not one
  global time.
- **Resilience** — if the process restarts mid-batch, some users silently get
  nothing. An in-memory scheduler has no durable record of "who still needs one."
- **Scale & isolation** — one slow/failed user's digest shouldn't block or crash
  everyone else's, and generation is CPU/API-bound so you want to run several in
  parallel.

### The target shape: enqueuer → queue → workers

Decouple *deciding who's due* from *doing the work*.

```
                  every minute
                       │
              ┌────────▼─────────┐
              │    ENQUEUER      │   singular (cron / pg_cron / Trigger.dev)
              │ "who is due now?"│   finds due users, pushes 1 job each
              └────────┬─────────┘
                       │ enqueue job {user_id, local_date}
              ┌────────▼─────────┐
              │      QUEUE       │   durable (Postgres table or Redis/managed)
              └────────┬─────────┘
             ┌─────────┼─────────┐
        ┌────▼───┐ ┌───▼────┐ ┌──▼─────┐
        │worker 1│ │worker 2│ │worker N│   scale horizontally
        └────┬───┘ └───┬────┘ └──┬─────┘
             │ generate digest for user_id
             │ INSERT digest (user_id, local_date)  ← unique = idempotent
             │ enqueue DELIVERY job (separate step)
```

Only the **enqueuer** must be a single instance. Web API and workers can both
scale — the constraint that forced one container today goes away.

### Data model additions
```sql
-- on users
digest_send_time  time    NOT NULL DEFAULT '09:00',
timezone          text    NOT NULL DEFAULT 'America/Toronto',  -- IANA name
digest_enabled    boolean NOT NULL DEFAULT true,

-- digests: swap the global unique for per-user
UNIQUE (user_id, digest_date)   -- digest_date = user's LOCAL date
```

### The enqueuer query (runs each minute)
"Find users whose local time is now, who are enabled, and who don't already have
today's digest." The `(user_id, digest_date)` unique constraint is the safety
net — even if the enqueuer double-fires or a worker retries, the second INSERT
just conflicts and no-ops. **Idempotency is a property of the schema, not the
code.**

DST is handled for free by computing each user's local time via `zoneinfo` /
IANA names — never store fixed UTC offsets.

### Queue choice (pick one)

| Option | Pros | Cons | When |
|---|---|---|---|
| **Postgres table + `SELECT … FOR UPDATE SKIP LOCKED`** | No new infra; you already run Postgres; fully durable & transactional | You hand-roll retries/visibility | **Recommended to start** — simplest, matches your scale |
| **Trigger.dev** | `scheduler.py` was written to swap to it; managed retries/observability | Vendor dependency, cost | If you want scheduling as a managed concern |
| **Redis + Arq/RQ/Celery** | Battle-tested, fast | New infra to run & monitor | Once volume outgrows a PG queue |

For a solo founder at launch scale, a **Postgres-backed job table with
`SKIP LOCKED`** is the least moving parts and reuses infra you already pay for.
Your existing `outbound_messages` table is already 80% of a queue — generalize
that pattern into a `jobs` table with `type`, `payload jsonb`, `status`,
`attempts`, `run_after`, and a dead-letter after N tries.

### Delivery is its own step
Keep *generation* and *sending* as separate jobs. A digest that generated fine
but failed to send should retry the **send**, not regenerate (and re-spend
Anthropic money). This also cleanly separates "server was down" from "Twilio
rejected the number."

### Migration path from today
1. Generalize `outbound_messages` → a `jobs` table (durable queue).
2. Split the container into **web** and **worker** processes (same image, diff
   entrypoint) + one **enqueuer** (cron).
3. Move digest generation out of the in-process scheduler into a worker that
   consumes `digest` jobs.
4. Retire `DigestScheduler`; the enqueuer becomes the only scheduled thing, and
   it only *enqueues* — it never does work.

---

## Phased build plan

Sequenced so **every phase ends deployable** — you never have a half-broken
`main`. Effort estimates are rough, for one focused solo builder. Do phases in
order; the parallel track (compliance) starts on day one because it's calendar-
gated, not effort-gated.

### Phase 0 — Ship single-user (do this first, regardless)
The real-world test that generation + delivery + SnapTrade hold up daily. Every
piece is reusable.
- [ ] Supabase project; `DATABASE_URL` (Session pooler) + `DB_SSL=true`
- [ ] Deploy the existing `Dockerfile` to Railway (Hobby plan, 1 replica)
- [ ] Set env vars; generate `API_TOKEN`
- [ ] Smoke test `/health`, `/chat`, `/digest/run`, `/digest/latest`
- [ ] iPhone Shortcut pulling `/digest/latest`
- [ ] External cron backstop (cron-job.org) POSTing `/digest/run` at 09:00
- **Deployable end state:** your own daily digest, in production.

### Parallel track — Compliance (START ON DAY 1, runs in background)
Calendar-gated; nothing here blocks coding but everything here blocks *launch*.
- [ ] Register a Twilio account
- [ ] File **A2P 10DLC** brand + campaign registration (days–weeks to approve)
- [ ] Draft privacy policy + "not financial advice" disclaimer
- [ ] Draft TCPA opt-in consent language + STOP/HELP copy
- [x] Create Stripe account, start business verification (live-mode ready)

### Phase 1 — Multi-tenant data model (~2–4 days)
- [ ] `users` table (id, email, timezone, digest_send_time, digest_enabled)
- [ ] Add `user_id` FK to `positions`, `transactions`, `agent_runs`, `digests`,
      `outbound_messages`
- [ ] `positions` unique → `(user_id, ticker, account)`
- [ ] `digests` unique → `(user_id, digest_date)`
- [ ] Enable **RLS**; policies scoping every table by `user_id`
- [ ] Backfill your own data as user #1; migration is idempotent
- [ ] Tests: prove user A cannot read user B's rows
- **Deployable end state:** same app, still single active user, but tenant-ready
  underneath.

### Phase 2 — Auth & accounts (~2–4 days)
- [ ] Wire Supabase Auth (or Clerk); issue per-user sessions
- [ ] Replace `require_auth` shared-token check with per-user identity
- [ ] Thread `user_id` from request → agent run → tool calls → digest
- [ ] Keep a service token for the enqueuer/workers (internal calls)
- **Deployable end state:** multiple people can log in; each sees only their data.

### Phase 3 — Onboarding & per-user brokerage (~3–5 days)
- [ ] SnapTrade **commercial** mode: register a SnapTrade user per app user
- [ ] Store per-user `SNAPTRADE_USER_SECRET` **encrypted at rest**
- [ ] Connect-brokerage flow in onboarding (reuse existing connect-url logic)
- [ ] Per-user sync (existing sync, scoped by `user_id`)
- [ ] Onboarding UI/flow: signup → connect → set send-time + timezone
- **Deployable end state:** a new person can self-serve from zero to synced book.

### Phase 4 — Per-user scheduling (~4–7 days) — the big one
See the deep dive above.
- [ ] Generalize `outbound_messages` → durable `jobs` table (type, payload,
      status, attempts, run_after, dead-letter)
- [ ] Enqueuer: every-minute cron, finds due users by local time, one job each
- [ ] Split image into **web** + **worker** entrypoints; add singular enqueuer
- [ ] Worker consumes `digest` jobs → generates → INSERT (idempotent on unique)
- [ ] Retire `DigestScheduler`
- [ ] Remove the "single instance only" constraint for web + workers
- **Deployable end state:** each user gets a digest at *their* 9:00am, resilient
  to restarts.

### Phase 5 — Multi-channel delivery (SMS/Email/Discord) — DONE (July 2026)
Built broader than originally scoped: users pick one preferred channel (SMS via
Twilio, email via Resend, or a Discord webhook), verify the destination with a
one-time code, and an in-process dispatcher drains `outbound_messages` with
per-channel adapters and retry backoff. Migrations `007_notifications.sql` +
`008_retire_imessage.sql`; code under `app/delivery/`.
- [x] Twilio send in a delivery dispatcher (separate from generation)
- [x] STOP/HELP/START inbound webhook → `opted_out_at` on the sms registration
- [x] Opt-in capture wired into onboarding (consent checkbox, timestamped)
- [x] Retire the iMessage Mac-worker path
- [ ] Ops: buy Twilio number, point webhook, toll-free/10DLC paperwork
- **Deployable end state:** users receive real texts/emails/Discord messages,
  compliantly.

### Phase 6 — Billing & cost control (~3–5 days)
- [x] Stripe subscriptions + webhooks (built July 2026: Checkout + Customer
      Portal + `/webhooks/stripe` flipping `users.plan`; `app/billing.py`,
      migration `015_billing.sql`, docs in PRICING_AND_ONBOARDING.md §4)
- [x] Per-user monthly cost cap enforced against `agent_runs.cost_usd`
- [ ] Per-user chat rate limiting (beyond the Free daily cap)
- [x] Graceful "cap reached" behavior (402 with upgrade message; digests skip)
- **Deployable end state:** paying customers; your Anthropic bill is bounded.

### Phase 7 — Polish for public launch (open-ended)
- [ ] Marketing/landing page
- [ ] Real onboarding UI polish, error states
- [ ] Support for additional brokerages (SnapTrade covers many already)
- [ ] Basic admin/support tooling

**Critical-path note:** Phase 5 can't *finish* until the parallel-track 10DLC
clears — which is exactly why that paperwork starts in Phase 0, not Phase 5.
