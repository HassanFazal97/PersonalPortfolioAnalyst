# Cirvia Mobile App — React Native (Expo) for iOS + Android

## Context

Cirvia (cirvia.ca) is today a single FastAPI container on Railway that serves both
a JSON API and its entire UI. Mobile users have to use the responsive web app; we
want them to download a real app instead.

The decisive finding from exploring the repo: **there is no JavaScript frontend to
port.** Every screen is hand-written HTML/CSS/vanilla-JS embedded as Python string
constants in `app/webapp.py` (6,031 lines) and `app/landing.py` (2,714 lines). The
only `package.json` in the repo (`ad/`) is an unrelated Remotion video-ad project.
The mobile client is greenfield either way — there are no components, types, or
client library to reuse.

The backend, by contrast, is already mobile-ready in the ways that matter:
stateless Supabase JWT bearer auth with **no cookies anywhere**
(`app/auth/jwt.py`; `require_auth` at `app/main.py:551-625`, installed app-wide at
`app/main.py:1211`), and an aggregated, ETag'd `GET /dashboard/bootstrap`
(`app/main.py:2672`) that collapses ~8 calls into one.

**Decisions already made:**
- Native rewrite in **React Native + Expo**, targeting **iOS and Android at launch**.
- **Web-only billing** — the app never sells subscriptions; no StoreKit/Play Billing.
- **Push notifications in v1** (digest ready, price/macro alerts).

**Intended outcome:** a native app in both stores, with push as the reason to
install it, consuming the existing API unchanged wherever possible.

---

## Architecture decisions

| Question | Decision | Why |
|---|---|---|
| Workflow | Expo managed + `expo-dev-client`, EAS Build. Never eject. | Config plugins (notifications, associated domains, custom scheme) rule out Expo Go; bare RN costs the upgrade path for no gain. |
| Location | `/mobile` at repo root, **not** an npm workspace | Keeps the Python repo's identity and the Docker build untouched. |
| Navigation | `expo-router` (file-based) | Deep links for push taps, Supabase recovery, and OAuth returns come free. |
| Data | TanStack Query v5 + MMKV persister | Gives cold-launch instant render against the ETag'd bootstrap endpoint. |
| Styling | Token module + `StyleSheet` (no NativeWind) | The web design system is already a flat CSS-custom-property list; porting is 1:1 mechanical. |
| Charts | `react-native-svg`, port `renderChart` | The existing chart is ~30 lines of polyline math. Victory/Skia are 10x the dependency for no gain. |
| Streaming chat | **New `POST /chat/start` + `GET /chat/runs/{id}/events`** | The single most important call in this plan — see below. |
| Push | `expo-notifications` + Expo Push Service, as an **additive fan-out** | Not a `preferred_channel`; see below. |

---

## The two hard problems

### 1. Chat streaming does not work as-is on React Native

`POST /chat/stream` (`app/main.py:1501`) is SSE over a POST with a JSON body and a
bearer header. The web client reads `resp.body.getReader()` (`app/webapp.py:3232-3323`).
React Native's `fetch` has no `ReadableStream` body, and `EventSource` can neither
POST nor set headers. All three of {POST, custom header, streaming} conflict.

**Solution: mirror the deep-dive pattern that already exists in this codebase.** Add
two endpoints in `app/main.py` next to the chat routes, reusing `ProgressBroker` and
`sse_response` from `app/streaming.py`:

```
POST /chat/start                 -> 202 {"run_id": "..."}   # claims the active_chats slot, returns immediately
GET  /chat/runs/{run_id}/events  -> SSE                     # plain GET + bearer header
```

This copies the structure proven at `app/main.py:1744` (`GET /deep-dive/{report_id}/events`),
including the ownership check at `app/main.py:1734` and the `cleanup_iterator` unsubscribe wrapper.

Why this rather than `expo/fetch` streaming (which would need zero server change):
**backgrounding**. When iOS suspends the app mid-run, the socket dies. With the
current POST-stream the run still completes server-side (that is deliberate — the
agent is driven in a detached task so a disconnected client is still billed) but the
client has *permanently lost the answer*, because the run id only arrives in the
terminal `done` event. With `run_id` returned up front, the client re-subscribes or
polls `GET /runs/{run_id}` on foreground. A 30-second agent run *will* get
backgrounded routinely on a phone. Secondary benefits: `react-native-sse` is
XHR-based (the most stable networking path in RN) and reconnects automatically.

Two details this requires:
- **A bounded replay buffer** (~500 events per run) emitted as a first `chat_snapshot`
  frame. Verified necessity: `ProgressBroker.publish` silently drops on `QueueFull`
  (`app/streaming.py:93-98`, queue size 256) — and for chat the dropped events would
  be `text_delta`, i.e. the answer itself. Replay also closes the real race between
  the POST returning and the client opening the SSE.
- Extract the current `chat_stream` `drive()` body into a shared helper so `/chat`,
  `/chat/stream`, and `/chat/start` cannot drift.

**Keep `POST /chat/stream` exactly as it is** — the web app uses it and removing it is
needless risk. The `done` event stays authoritative (client discards accumulated
deltas in favour of `done.answer`). Client fallback chain: SSE → blocking `POST /chat`.

The same SSE wrapper serves `GET /deep-dive/{id}/events` with **no server change**,
since that one is already a plain GET.

### 2. Push is a fan-out, not a fourth preferred channel

`Repo.enqueue_outbound` (`app/db/repo.py:1366`) resolves **one** `preferred_channel`
and writes a single row. If push were added to `CHANNELS` in `app/delivery/channels.py`
and a user selected it, they would **lose their email digest** — and a 4KB push payload
cannot carry a digest anyway. Push is a pointer to content, not the content.

So `preferred_channel` semantics stay untouched (no change to the
`users_preferred_channel_check` constraint, no change to `CHANNELS`, no change to the
web channel picker). Instead, add a `push=True` path that writes **one
`outbound_messages` row per registered device token** with `channel='push'`. Verified:
`outbound_messages.channel` is a plain text column with no CHECK constraint
(`app/db/migrations/007_notifications.sql:48`), so this needs no constraint change. The
existing `Dispatcher` (`app/delivery/dispatcher.py`) then drains them with its existing
backoff and permanent-failure handling for free.

Cleanest wiring: add `push=`/`push_title=`/`deep_link=` kwargs to `enqueue_outbound` itself so
the fan-out lives in one place and each of the six call sites is a one-line diff
(`app/agent/digest_pipeline.py:616`, `app/tools/digest.py:135`,
`app/agent/macro/orchestrator.py:327`, `app/agent/anomaly/orchestrator.py:229`,
`app/agent/deep_dive/pipeline.py:270`, `app/trial_notices.py:112`). There is a direct
precedent for a channel-aware body override in the existing `sms_body` kwarg
(`app/db/repo.py:1373`) — copy that shape.

Provider: **Expo Push Service** — one HTTP call covers both APNs and FCM, which fits the
"one adapter = one provider HTTP call" shape of `app/delivery/adapters/base.py`, and its
`DeviceNotRegistered` response maps directly onto the dispatcher's `permanent=True`
signal. The APNs key and FCM service account live in EAS, not in your container, and no
new Python dependency is needed (`httpx` is already a dep — this matters because
`requirements.txt` is a hash-pinned lockfile and adding a dep means regenerating it with
`uv pip compile`, per `docs/DEPLOY.md`).

**A second reason the per-device-row design is the right one:** verified that
`build_adapters(settings)` (`app/delivery/adapters/__init__.py:36`) receives only settings
and is called once in `lifespan` (`app/main.py:166`) — it has no repo access. Because each
`outbound_messages` row carries a single device token in `destination`, the push adapter
stays a pure "one destination → one HTTP call" adapter like the others. A per-user-row
design would instead force a lazy repo callable into the adapter factory.

---

## Server-side work (all additive; the web app keeps working unchanged)

| File | Change |
|---|---|
| `app/main.py` | `POST /chat/start` + `GET /chat/runs/{id}/events` near :1501; `POST/DELETE /me/devices` + `PATCH /me/devices/kinds` near :2455; a `"push"` block in `_notifications_payload` (:2428) **and** filter `push` out of `available_channels` so the web picker at `app/webapp.py:1465` never sees it; `.well-known` routes added to `_AUTH_EXEMPT_PATHS` (:501) |
| `app/db/migrations/029_push_devices.sql` | NEW — `push_devices` table. Follow `007_notifications.sql` conventions exactly: `CREATE TABLE IF NOT EXISTS`, `DO $$`-guarded constraints, and the RLS policy pattern at :84-87 (`USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)`). RLS is on, so the policy is mandatory. `UNIQUE (expo_token)` — not `(user_id, token)` — so a shared device switching accounts *moves* the token rather than duplicating it. |
| `app/db/repo.py` | `upsert_push_device`, `list_push_devices`, `disable_push_device`; extend `enqueue_outbound` (:1366) with the fan-out |
| `app/delivery/adapters/expo_push.py` | NEW `ExpoPushAdapter` (`channel = "push"`); body ≤ ~150 chars, real payload in `data: {kind, deep_link, id}` |
| `app/delivery/adapters/__init__.py` | Register only when configured (matches the existing conditional-registration philosophy) |
| `app/delivery/channels.py` | `PUSH_CHANNEL = "push"` **outside** `CHANNELS`; `mask_destination` handles it |
| `app/billing.py` / `app/delivery/discord_connect.py` | Native return paths for hosted redirects (below) |
| `app/webapp.py` | Delivery settings: a read-only "Mobile app" device list, so web and native agree |
| `app/config.py` | `expo_access_token`, `push_enabled` |
| `.dockerignore` | Add `mobile`, and while there `ad`, `docs`, `evals`. Verified the Dockerfile uses explicit `COPY app ./app` / `COPY scripts ./scripts` (never `COPY . .`), so `mobile/` cannot enter the image — but `mobile/node_modules` would still bloat every Railway build context. |

New tests, mirroring existing ones: `tests/test_chat_start_api.py` (202 shape, 429 on
second concurrent start, replay frame, 404 on someone else's run), `tests/test_push_adapter.py`,
`tests/test_devices_api.py`, `tests/test_push_fanout.py`, `tests/test_wellknown.py`.

**`tests/fakes.py` (49KB fake repo) must gain every new repo method** — otherwise every
existing test that builds the app breaks. Budget for this; it is not optional cleanup.

Also confirm the account-deletion path (`DELETE /me`, `app/main.py:2206`) removes
`push_devices` rows — an `ON DELETE CASCADE` on the `user_id` FK covers it, but verify the
deletion actually goes through the FK rather than an explicit table list.

**CORS: do not add it.** Native clients need no CORS and there is none in the repo today.
It only becomes necessary if a browser client outside `cirvia.ca` ever appears (e.g.
`expo start --web`). Noting it here so it isn't rediscovered as a mystery.

---

## Hosted browser flows, handled natively

- **SnapTrade connect** — `GET /portfolio/connect-url` (`app/main.py:1969`) returns a hosted
  portal URL and there is *no server callback*; the client just polls `GET /portfolio/status`
  then `POST /portfolio/sync`. Ideal for `WebBrowser.openAuthSessionAsync`
  (`ASWebAuthenticationSession` / Custom Tabs). Do **not** use an embedded WebView — brokerage
  IdPs block them. `POST /portfolio/manual` (`app/main.py:2007`) stays a prominent fallback.
- **Discord** — the callback at `app/main.py:2542` 303-redirects to `/app/settings?discord=connected`.
  Add an `"app"` return target in `app/delivery/discord_connect.py` that bounces to
  `cirvia://settings/delivery`.
- **Supabase password reset** — add `cirvia://reset` and `https://cirvia.ca/app/reset` to the
  Supabase redirect allow-list; handle the URL explicitly in the app with `detectSessionInUrl: false`.
- **Universal links / App Links** — serve `/.well-known/apple-app-site-association` and
  `/.well-known/assetlinks.json` as explicit routes (so team ID and fingerprints can be templated
  from `app/config.py`) added to `_AUTH_EXEMPT_PATHS`. Scope AASA to `/app/*` and `/stocks/*`;
  deliberately exclude `/`, `/pricing`, `/track-record` so marketing pages stay in the browser
  where they can convert and legally sell.

---

## Billing inside the app: zero purchase surface in v1

`settings/plan.tsx` shows status only — current plan, trial countdown, renewal state, chat
quota. No price, no upgrade button, no link to checkout. `POST /billing/checkout` and
`/billing/portal` are never called from native in v1.

A trial-expired user is not shown a paywall; they see their real Free-plan state. When a `402`
comes back from `_enforce_usage_limits` (`app/main.py:1083`), render the server's `detail`
prose verbatim **but strip the "Upgrade to Pro…" clause on iOS** — otherwise the app is
soliciting an out-of-app purchase. One regex in the client error layer, behind `Platform.OS`.

`POST /billing/choose-free` **should** be exposed as "Continue on the Free plan" — it is not a
purchase, and it unblocks users stuck in the trial-decision gate with digests paused.

Rationale for being this conservative: external-purchase links are permitted on the US
storefront post-2025-injunction, but that is storefront-scoped and Cirvia targets Canadian
investors, so "safe globally" and "permitted in the US" differ — meaning conditional per-storefront
UI. It is also the most common first-submission rejection. Ship with no purchase surface, get
approved, then add an external link behind a remote flag in v1.1. Keep Android identical to iOS
in v1: one code path.

---

## Client scope

Route tree under `mobile/app/`: `(auth)/sign-in`, `(auth)/reset`, a 7-step `(onboarding)/` flow,
`(tabs)/` with Digest | News | Holdings | Watching | Deep Dive, a `chat` modal, `stock/[ticker]`,
`picks`, `dives/[id]`, and `settings/{account,brokerage,delivery,profile,plan,danger}`.

**Deferred to v1.1: Risk Lab only** (`app/webapp.py:5513`) — Pro-gated, the heaviest
visualization surface (correlation matrix + VaR + Monte Carlo), and the screen least wanted on a
390pt phone. Ship the entry point as a "view on cirvia.ca" note, which is a feature-parity
pointer, not a purchase link. Picks and Deep Dive both stay in v1.

Build the primitive layer (`Card`, `Screen`, `Banner`, `MetricStrip`, `ListRow`, `Skeleton`,
`Sheet`, …) in M0 **before any screen**. This is the difference between screens at 150–250 lines
and screens at 600.

Key client pieces: `src/api/client.ts` (bearer + single-flight refresh + 401 retry-once-then-sign-out),
`src/api/etag.ts` (MMKV-backed conditional GET, since RN's fetch has no HTTP cache — the bootstrap
endpoint's `If-None-Match`/`304` and its `refreshing: [...]` array must both be honoured, and a
section that returns `{error: ...}` must keep its previous value rather than blanking a working
panel), `src/auth/supabase.ts` (SecureStore adapter — it holds a refresh token — plus `AppState`
→ `startAutoRefresh`/`stopAutoRefresh`), and `src/charts/PriceChart.tsx` (a direct port of
`renderChart` at `app/webapp.py:4218`, with a `react-native-gesture-handler` pan crosshair).

On sign-out: `queryClient.clear()` **and** wipe MMKV. Leftover portfolio data after logout is a
legitimate store-review privacy finding.

**TODO — post-onboarding product tour (web parity, M10):** the web dashboard now ships a
coach-mark tour right after onboarding (`_TUTORIAL_*` in `app/webapp.py`), persisted server-side
in `users.tutorial_completed_at` (migration 031) via `POST /me/tutorial/complete` and surfaced as
`tutorial.completed` in `/me`. The native app should reuse that same endpoint and flag — one
completion across platforms — with a native overlay walking the `(tabs)` shell, the chat modal,
and the picks/dives/settings routes (the `push-priming.tsx` interstitial is the existing precedent
for a post-onboarding teaching screen). Post-launch scope; not a store-submission blocker.

---

## Store submission

- Bundle ID `ca.cirvia.app`; register the App ID before building (associated domains need it).
- `ITSAppUsesNonExemptEncryption: false`; iOS privacy manifest must declare required-reason API
  usage (`CA92.1` for UserDefaults-class storage) and collected types: Email, Financial Info,
  Device ID (push token), Diagnostics. Mirror it in Play's Data Safety form.
- **Account deletion is mandatory (Apple 5.1.1(v))** — `DELETE /me` already exists
  (`app/main.py:2206`) and even cancels the Stripe subscription. Surface it in `settings/danger`
  within ≤3 taps.
- **A demo account is non-negotiable.** A reviewer will not link a real brokerage through
  SnapTrade. Seed `review@cirvia.ca` via `POST /portfolio/manual` with holdings, a digest, a deep
  dive, picks, and a watchlist — **on the Pro plan**, so Pro screens render instead of 402ing (a
  reviewer hitting a paywall reads as a broken app).
- Make the "not investment advice" disclaimer visible in-app (Digest footer, Picks header), not
  just in `/terms`.
- Check the Play Console account's testing-period requirement in **week 1**, not week 10 — it can
  add weeks before production access.
- Set up EAS Update on day one so JS-only fixes ship without a review cycle.

---

## Milestones (solo developer)

| # | Milestone | Days |
|---|---|---|
| M0 | Foundations: scaffold, tokens + ~12 UI primitives, auth + `authedFetch`, TanStack Query + MMKV + ETag layer, sign-in against prod | 4–5 |
| M1 | Dashboard vertical slice — bootstrap with 304 + SWR, metric strip, 4 warning banners, all four tabs. **Proves the architecture.** | 6–8 |
| M2 | Streaming chat: server `/chat/start` + run events + replay buffer + tests (~1.5d), then the client | 4–5 |
| M3 | Stock detail + SVG chart port + gesture crosshair + intraday poll | 4–5 |
| M4 | Onboarding + SnapTrade auth session + manual-holdings fallback + delivery setup | 5–6 |
| M5 | Settings, Discord native return, account deletion, status-only plan screen | 4–5 |
| M6 | Push end-to-end: migration 029, adapter, fan-out at 6 call sites, `/me/devices`, permission priming, tap deep links | 5–6 |
| M7 | Deep dives + picks | 4–5 |
| M8 | Universal links, icons/splash, dark mode, a11y, offline states, demo account, store listings | 6–8 |
| M9 | Submission + rejection round-trips + Play testing wait | 5–10 |
| M10 | TODO (post-launch): product tour after onboarding — native coach-marks over the tab shell, reusing `tutorial_completed_at` / `POST /me/tutorial/complete` from the web tour | 2–3 |

**Total ≈ 10–13 weeks** to both stores (M10 excluded — post-launch), assuming no major rejection loop. Add ~40% if React
Native itself is new to you.

**First TestFlight build at end of M3 (~day 15–18):** sign-in, dashboard with all four tabs on
live data, streaming chat, stock detail with chart. No onboarding, no push, no settings. That cut
exercises every architectural piece — auth, ETag/SWR, SSE, SVG — on real devices before 60% of
the UI is written on top of it.

---

## Risks

- **Rewrite cost.** ~6,000 lines of `webapp.py` UI, none reusable. Expect **8,000–12,000 lines of
  new TypeScript** plus ~600–900 lines of new Python. The primitives-first discipline in M0 is
  what keeps this from doubling.
- **Dual maintenance, permanently.** Every user-facing feature costs ~1.7x after launch, roughly
  3–4 extra developer-weeks a year at two features a month, plus review latency. Mitigate by
  pushing shared logic server-side (the `/dashboard/bootstrap` pattern is the model — compute
  banner conditions, trial state, quota copy, and gating once in `_build_section`/`_me_payload`
  and ship flags), and by accepting that native will lag web by a release.
- **Single replica.** `ProgressBroker`, `snapshot.store`, `active_chats`, and APScheduler are all
  in-process, and mobile multiplies concurrent long-lived SSE connections. Fine at current scale,
  but the day a second replica is needed, chat SSE, deep-dive SSE, and the snapshot cache break
  *simultaneously*. Instrument concurrent SSE count now.
- **App Store billing/steering rejection** — high likelihood, medium cost. Budget two review rounds.
- **iOS backgrounding killing agent runs** — high likelihood; precisely why the `run_id`-first
  design above is not optional.
- **The `enqueue_outbound` fan-out is the highest-consequence diff in the project.** That function
  is deliberately designed to write a `status='skipped'` row rather than raise when no channel
  resolves (`app/db/repo.py:1375-1378`), so a bug here means **nobody gets their digest, silently**.
  Ship the push adapter behind a dry-run flag (log-only) for the first week and cover the fan-out
  with tests before enabling it.
- **Push permission spent too early.** Digest push is the app's core loop; prompt after the first
  successful sync, behind an explainer, not at first launch.
- **Expo SDK churn** — ~3 releases/year, 1–2 days each. Don't eject; ejecting makes it worse.

---

## Addendum: pre-existing issues a mobile launch will expose

These are things a third design pass turned up in the current backend. They are not caused by the
mobile app, but a store-distributed client makes each of them matter more.

### A live bug in account deletion — FIXED (migration 029)

**The bug.** After `DELETE /me`, the caller's JWT stayed valid for its remaining ~1h, and deleting
the Supabase auth user could not revoke it. The next request on that token fell through to
`get_or_create_user` and **silently provisioned a brand-new empty account for the person who had
just deleted theirs** — and a fresh no-card trial with it, the next time they synced a portfolio.
(The trial is armed at first sync by `maybe_start_trial`, not at provisioning, so the trial effect
was one step removed rather than immediate.)

The auth cache was not the root cause. Even on a cold cache the already-issued JWT is still validly
signed with a valid `exp`, so it re-verifies and re-provisions identically.

**The fix.** `deleted_auth_ids`, a dated tombstone table (`app/db/migrations/029_deleted_auth_ids.sql`).
`get_or_create_user` now takes the token's `iat` and refuses to provision when the uid is tombstoned
and the token was minted at or before the deletion, raising `DeletedAccountError`, which
`require_auth` turns into a 401. A token minted *after* the delete is treated as a genuine new
sign-in: the tombstone is cleared and provisioning proceeds.

Two deliberate choices worth remembering:
- **Dated, not permanent.** A permanent ban list would lock out a user whose Supabase auth user
  outlived the delete (which happens whenever no service-role key is configured, since
  `_delete_supabase_auth_user` is best-effort) — they could never sign up again with that identity.
- **Fails closed on an undateable token.** A tombstoned uid presenting a token with no `iat` is
  refused rather than allowed, since a token we cannot date is not evidence of a new sign-in.

`authcache.evict_tokens_for(auth_id)` was added alongside so a cached verification can't keep
serving claims without ever re-entering full verification — which is where `iat` comes from.

Mobile would have made this fire far more often, since apps hold a session across launches and
retry in the background, but it was reachable from the web.

### No rate limiting exists anywhere

The only 429s in the codebase are single-flight guards (`app/main.py:1457`, `:1513`, `:1636`) and
the verification-code caps. That is defensible while every client is your own web page; it is not
once the API is reachable from a store-distributed binary. An in-process token bucket is exact
under the one-replica constraint you already have, so this adds no new architectural limitation.

Two related details: exempt `/health` and `/webhooks/*` (throttling Stripe or Twilio retries would
be a self-inflicted outage), and note that the Dockerfile starts uvicorn **without**
`--proxy-headers`, so `request.client.host` is currently Railway's proxy rather than the caller —
any IP-keyed limit needs that fixed first.

### The dispatcher will not keep up with push fan-out

`Dispatcher.tick` (`app/delivery/dispatcher.py:64-90`) sends **strictly sequentially** — `batch_size`
25 on a 30s tick, roughly 50 sends/minute. Push multiplies rows by devices-per-user and concentrates
them at the morning-digest spike. Fix with bounded concurrency (`asyncio.Semaphore` + `gather`),
which is safe because `claim_due_outbound` already leases rows `FOR UPDATE SKIP LOCKED`
(`app/db/repo.py:1432-1455`), plus a configurable batch size.

This is also a further point for Expo Push over raw FCM: **Expo accepts up to 100 messages per
HTTP request**, whereas FCM v1 has no batch endpoint (the `/batch` API was deprecated in 2024) and
requires one request per token.

### A correction to the deep-link section above

Supabase password-reset and email-confirm tokens arrive in the URL **fragment** (`#access_token=…`)
in the implicit flow. Fragments are never sent to the server, so **no FastAPI route can read them** —
the hand-off to the app has to be a client-side bridge page that reads `location.hash` and
redirects to the app scheme. Plan for a small bearer-exempt `/app/auth/bridge` page rather than a
server-side redirect. (If the client uses PKCE, the callback carries `?code=` as a query param
instead, which a route *can* see — but still bounce it to the app rather than exchanging it
server-side.)

### Two additions worth adopting

- **`GET /client/config`** — a small, uncached, auth-optional endpoint returning billing
  capabilities (`purchase_enabled`, `show_pricing`, `show_external_links`) and
  min-supported-version. The point is that your App Store anti-steering posture becomes a server
  env var rather than an app release, which matters because Apple's and Google's external-link
  rules are actively changing. Keep this **out** of `_me_payload`, which is cached as the `"me"`
  snapshot section and re-served through `/dashboard/bootstrap` — varying it by client would be a
  cache-poisoning bug.
- **API versioning without a router refactor** — a ~20-line pure-ASGI middleware that strips a
  `/v1` prefix from `scope["path"]` before routing. Web keeps calling unversioned paths, mobile
  pins `/v1`, and because the rewrite happens before routing, `require_auth` and the whole
  `_AUTH_EXEMPT_PATHS` set keep working untouched. Converting 90+ inline routes to `APIRouter`s
  would be a ~3,000-line diff through the file that also owns auth and lifespan — not worth it.

---

## Verification

- **Backend, locally:** run the app per the `verify` skill (note `.venv/bin/uvicorn` has a stale
  shebang — use `.venv/bin/python -m uvicorn`, and set `SSL_CERT_FILE` to certifi or authed routes
  500). Exercise `POST /chat/start` + `GET /chat/runs/{id}/events` with `curl -N` and a real
  Supabase JWT; confirm a second concurrent start returns 429 and another user's run returns 404.
- **Migration:** `python scripts/migrate.py` against a local Postgres, then re-run it to confirm
  idempotency; verify the RLS policy actually isolates `push_devices` by connecting with the app
  role and a different `app.current_user_id`.
- **Push:** register a device from a physical phone, trigger `POST /digest/run`, and confirm both
  the normal channel row and the push rows appear in `outbound_messages` and that the dispatcher
  marks them sent. Test `DeviceNotRegistered` handling by revoking the token.
- **Regression:** `pytest` for the existing suite, and manually confirm the **web** chat still
  streams via `POST /chat/stream` and the web delivery picker still shows only SMS/email/Discord.
- **On-device:** the M1 dashboard must render from MMKV cache before the network settles on a cold
  launch; kill the app mid-chat and confirm the answer is recovered on reopen; verify universal
  links open the app and push taps route to the right screen.
