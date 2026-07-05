# Plan: Pricing + In-App Onboarding

Decisions (2026-07-05): **freemium** (Free + Pro), Pro at **CAD $9/mo (≈ $90/yr)**,
onboarding UI **server-rendered inside this FastAPI app**, **pricing page now /
Stripe later**.

---

## 1. Pricing model

Two tiers. The split is tunable — this is a sensible starting point.

| | Free | Pro — $9/mo ($90/yr) |
|---|---|---|
| Connected accounts | 1 | Unlimited |
| Morning digest | Weekly (Mon) | Daily (weekdays) |
| Macro alerts | — | ✓ |
| On-demand chat | 5 questions/day | Unlimited |
| Holdings sync | ✓ | ✓ |

The owner account is effectively Pro/unlimited. Billing is deferred, so "upgrade"
initially routes to a waitlist/CTA; the plan flag and gating are built now so
turning on Stripe later only flips the flag.

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
- Pro → "Go Pro" → until Stripe lands, a waitlist/`mailto` CTA (or a "start free,
  upgrade in-app" flow).
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

## 4. Billing (later — Phase 6)

Deferred by choice. When ready: Stripe Checkout + customer portal, a webhook that
flips `users.plan` on `checkout.session.completed` / subscription updates, and a
per-user cost cap against `agent_runs.cost_usd`. The plan flag + gating built in
step 1 mean this is mostly wiring, not rework.

---

## Build order (each step ships independently)

1. **`/pricing` page** — pure marketing, no auth/schema. Ship immediately.
2. **Plan flag + gating** — `006_plans.sql`, config limits, chat cap + digest
   cadence + alerts gating, `GET/PATCH /me`, `GET /portfolio`.
3. **Onboarding + dashboard pages** — Supabase JS auth, connect flow,
   preferences, dashboard. (`SUPABASE_ANON_KEY` config.)
4. **Stripe** — checkout + webhooks flip the plan (separate phase).

## Verification
- `/pricing` reachable without a token; nav/footer link it; content correct.
- Gating: a Free user's 6th chat of the day is refused with an upgrade message; a
  Pro user is unlimited; macro scan skips Free users. (Unit tests with FakeRepo.)
- Onboarding end-to-end against Supabase + a real Wealthsimple connection: sign in
  → connect → sync → preferences saved → dashboard shows holdings.
