# Plan: Pricing + In-App Onboarding

Decisions (2026-07-05, updated 2026-07-20): **freemium** (Free + Pro), Pro at
**USD $15/mo ($120/yr — 4 months free)**, onboarding UI **server-rendered
inside this FastAPI app**. Stripe billing shipped — see §4. Every new signup
gets a **7-day no-card Pro trial** (§1a).

---

## 0. Unit economics & cost controls (the load-bearing part)

Two structural guarantees keep cost < revenue regardless of tier lines:

1. **Macro scans the world once, not per user.** Geopolitical/Fed/energy events
   are global; only the mapping to a user's holdings is per-user. The scheduled
   scan runs the 4 web-searching specialists **once** (owner-attributed), then
   each Pro user gets a cheap **Haiku** synthesis (events → their tickers). Turns
   macro from ~$0.30–0.60 *per user* into one shared scan + ~$0.02/user.
2. **Per-user monthly cost cap** against `agent_runs.cost_usd`. Free cap ~$0.75,
   Pro cap ~$6 (config). Over cap → macro/digest skip the user and chat is
   refused with an upgrade message. A power user cannot run us negative. Owner /
   service token is exempt.

Plus: Free daily chat limit; macro is **Pro-only**.

**SnapTrade plan: Daily data ($1/user/mo, read-only).** Matches our read-only
model; half the price of Real-time (which bundles trading we never use); daily
refresh aligns with the daily digest. ~$0.05 one-time manual sync at onboarding.
Note this $1/user is a *fixed* COGS the moment someone connects — heaviest on
Free (a connected free user ≈ $1 SnapTrade + ~$0.75 Anthropic ≈ $1.75/mo at $0
revenue). Consider a time-limited trial vs perpetual-free later.

Target: Pro price **$12–15/mo** for a comfortable ≥50% margin after the fixes;
the number lives in config and is easy to change.

## 1. Pricing model

Two tiers. The split is tunable — this is a sensible starting point.

| | Free | Pro — $15/mo USD ($120/yr) |
|---|---|---|
| Connected accounts | 1 | Unlimited |
| Morning digest | Weekly (Mon) | Daily (weekdays) |
| Macro alerts | — | ✓ |
| On-demand chat | 5 questions/day | Unlimited |
| Holdings sync | ✓ | ✓ |

The owner account is effectively Pro/unlimited (by decree, not subscription —
the webhook never downgrades it). Stripe billing is live; upgrades run through
hosted Checkout from `/app/settings`.

### 1a. No-card Pro trial (shipped 2026-07-20)

Every new signup gets `TRIAL_DAYS` (default 7) of the full Pro experience with
no card on file (`users.trial_ends_at`, migration `017_trial.sql`; helpers in
`app/plans.py`). While active, `effective_plan()` resolves to `pro` everywhere:
daily digests, macro alerts, Pro chat quota, uncapped digest holdings.

When the trial lapses **digests pause entirely** (neither cadence; the digest
pipeline returns `skipped_trial_decision`, macro/anomaly recipients exclude the
user) until the user logs in and decides:
- **Upgrade** → Stripe Checkout; the webhook sets `plan='pro'` and clears
  `trial_ends_at`.
- **Continue on Free** → `POST /billing/choose-free` clears `trial_ends_at`;
  the weekly Free digest resumes.

The decision surfaces as a non-dismissible dashboard banner and the settings
plan card (`/me` exposes `effective_plan` + a `trial` block). Nothing is ever
charged automatically — there is no card to charge. Existing users
(`trial_ends_at IS NULL`) are unaffected.

### Schema + gating
- **Migration `006_plans.sql`**: `users.plan text not null default 'free'`
  (+ optional `plan_since timestamptz`). Owner row → `'pro'`.
- **Config**: per-plan limits as constants (accounts, daily chat cap, digest
  cadence, alerts on/off) so they're easy to change.
- **Gating points** (small, targeted):
  - `POST /chat`: for Free, count today's `agent_runs` (trigger='chat') for the
    user; over the cap → 402/429 with an upgrade message.
  - Digest enqueuer: Free = weekly cadence, Pro = daily (keys off `users.plan`).
  - Macro scan (`run_macro_scans_for_all`): skip Free users.
  - Brokerage sync: Free capped at 1 account.
- `repo.get_user` already returns the row; add `plan` to it and a
  `repo.count_chats_today(user_id)` helper.

---

## 2. Pricing page (`/pricing`) — build first (no auth, low risk)

Server-rendered, same layout as the rest of the site: two-column Free vs Pro
comparison, annual toggle copy, FAQ on billing, CTAs:
- Free → "Start free" → `/app` (onboarding).
- Pro → "Go Pro" → `/app/settings?billing=upgrade` (signed-out visitors pass
  through sign-in first, then land on the highlighted plan card).
Add `/pricing` to the nav and footer; add it to `_AUTH_EXEMPT_PATHS`.

---

## 3. In-app onboarding (server-rendered + Supabase JS)

**Architecture.** New HTML pages served by this FastAPI app (public shells, like
the marketing pages). A small browser bundle uses `supabase-js` (CDN) with the
**publishable key** + `SUPABASE_URL` for sign-in, then calls the existing API
with the Supabase JWT (`Authorization: Bearer …`). The API stays the security
boundary; the pages themselves are auth-exempt HTML.

**New config**: `SUPABASE_ANON_KEY` (the publishable `sb_publishable_…` key —
public, safe to embed). Injected into the page (or a `/app/config.js`).

**Pages**
- `/app` — sign in / sign up (Supabase email+password or magic link). On success,
  route to onboarding or dashboard based on `/portfolio/status`.
- `/app/onboarding` — stepper:
  1. **Account** — confirm email (from `/auth/whoami`).
  2. **Connect brokerage** — `POST /portfolio/snaptrade/register` →
     `GET /portfolio/connect-url` → redirect to SnapTrade's Connection Portal.
     On return, poll `GET /portfolio/status` until `connected`, then
     `POST /portfolio/sync`.
  3. **Preferences** — digest send-time + timezone + enable (needs new endpoints,
     below).
  4. **Done** → dashboard.
- `/app/dashboard` — holdings summary, latest digest, recent alerts, and a chat
  box. Uses `GET /portfolio` (new, below), `GET /digest/latest`, `GET /alerts`,
  `POST /chat`.

**New API endpoints**
- `GET /me` → `{email, plan, timezone, digest_send_time, digest_enabled}`.
- `PATCH /me` → update `timezone`, `digest_send_time`, `digest_enabled`
  (repo: `update_user_preferences`).
- `GET /portfolio` → holdings for the dashboard (wraps the existing
  `get_portfolio` tool with the request's `user_id`).

**SnapTrade redirect.** The Connection Portal needs a redirect back to
`/app/onboarding?step=connected`. Confirm `connection_portal_url()` accepts a
custom redirect and wire it (fallback: user clicks "I've connected" → poll
status).

---

## 4. Billing (shipped — 2026-07-20)

Stripe Checkout (hosted) + Customer Portal + a signature-verified webhook. All
Stripe logic lives in `app/billing.py`; the webhook flips `users.plan`.

- **Endpoints**: `POST /billing/checkout` (authed → Checkout URL),
  `POST /billing/portal` (authed → Portal URL), `POST /webhooks/stripe`
  (bearer-exempt; `Stripe-Signature` is the auth).
- **Events registered** (exactly these four): `checkout.session.completed`,
  `customer.subscription.created` / `.updated` / `.deleted`. Every event
  re-fetches the subscription from the API and syncs to *current* state —
  ordering and redelivery are harmless. Idempotency via the `stripe_events`
  ledger (migration `015_billing.sql`).
- **Status → plan**: `active` / `trialing` / `past_due` → `pro` (past_due =
  dunning grace while Smart Retries run; dashboard auto-cancels after the final
  retry); everything else → `free`. Downgrade clears subscription fields but
  keeps `stripe_customer_id` for easy re-subscribe. Guards: the owner is never
  downgraded; a stale (superseded) subscription's terminal event is ignored.
- **Config**: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
  `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_PRO_ANNUAL` (optional),
  `STRIPE_AUTOMATIC_TAX` (off until GST/HST registration — revisit near the
  CRA $30k small-supplier threshold). Billing is enabled only when secret key +
  monthly price + `PUBLIC_BASE_URL` are all set; otherwise the UI keeps its
  "coming soon" copy.
- **Account deletion** (`DELETE /me`) cancels any active subscription first and
  aborts (502) if the cancel fails — no zombie subscriptions. Refunds stay
  manual (dashboard), per the pricing FAQ.

---

## Build order (each step ships independently)

1. **`/pricing` page** — pure marketing, no auth/schema. Ship immediately.
2. **Plan flag + gating** — `006_plans.sql`, config limits, chat cap + digest
   cadence + alerts gating, `GET/PATCH /me`, `GET /portfolio`.
3. **Onboarding + dashboard pages** — Supabase JS auth, connect flow,
   preferences, dashboard. (`SUPABASE_ANON_KEY` config.)
4. **Stripe** — checkout + webhooks flip the plan. ✅ shipped (see §4).

## Verification
- `/pricing` reachable without a token; nav/footer link it; content correct.
- Gating: a Free user's 6th chat of the day is refused with an upgrade message; a
  Pro user is unlimited; macro scan skips Free users. (Unit tests with FakeRepo.)
- Onboarding end-to-end against Supabase + a real Wealthsimple connection: sign in
  → connect → sync → preferences saved → dashboard shows holdings.
