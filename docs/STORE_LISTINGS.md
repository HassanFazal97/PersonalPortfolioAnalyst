# Store listings (M8) — copy, forms, and screenshot plan

Draft collateral for both stores. Character limits are noted inline; everything here
fits them. Pricing and upgrade language is deliberately absent everywhere — v1 ships
zero purchase surface (see `MOBILE_APP_PLAN.md`, "Billing inside the app"), and the
listing should match the binary.

## Identity

| | |
|---|---|
| App name (iOS, ≤30) | `Cirvia: AI Portfolio Analyst` (28) |
| Subtitle (iOS, ≤30) | `An analyst that shows its work` (30) |
| Title (Play, ≤30) | `Cirvia: AI Portfolio Analyst` |
| Category | Finance |
| Age rating | 4+ / Everyone |
| Privacy policy URL | https://cirvia.ca/privacy |
| Support URL | https://cirvia.ca/contact |
| Marketing URL | https://cirvia.ca |

Keywords (iOS, ≤100 chars, 79 used):
`portfolio,stocks,investing,digest,analyst,dividends,watchlist,brokerage,tsx`
(Don't spend keyword characters on "AI" or "Cirvia" — both are already in the name.)

## Short description (Play, ≤80 chars)

> Your portfolio, briefed every morning by an AI analyst that shows its work. (76)

## Promotional text (iOS, ≤170 chars)

> Wake up to a portfolio digest that cites its evidence. Cirvia reads the filings,
> the prices, and the news — and shows you exactly why it says what it says. (152)

## Full description (both stores, ≤4000 chars)

> **Cirvia is the AI analyst that shows its work.**
>
> Every morning, Cirvia reads what happened to your holdings — prices, filings,
> news, valuations — and sends you a digest that explains what matters and why.
> No black-box scores. Every claim comes with the evidence behind it.
>
> **Your portfolio, actually understood**
> Connect your brokerage in minutes through SnapTrade, or enter holdings manually.
> Cirvia is read-only by design: it can never trade, move money, or touch your
> account. It only looks.
>
> **A morning digest worth opening**
> What moved, why it moved, and what's coming — earnings dates, valuation shifts,
> unusual action. Delivered as a push notification, text, email, or Discord
> message, on your schedule and timezone.
>
> **Ask the analyst anything**
> Chat about any holding and watch Cirvia work through the question step by step,
> citing the numbers it used. Tap any stock for the full picture: chart, position,
> valuation verdict with its evidence table, and the news that matters.
>
> **Deep dives and daily picks**
> Full research reports on the companies you own, and a daily picks list with a
> public track record — every call logged, right or wrong, at cirvia.ca.
>
> Cirvia is research, not financial advice. Markets involve risk; decisions and
> outcomes are yours.

(~1,450 chars — room to grow, nothing to cut.)

## Play Data Safety form

Mirrors the iOS privacy manifest in `mobile/app.json` exactly — three collected
types, no tracking, no third-party sharing. (`MOBILE_APP_PLAN.md` mentions
Diagnostics, but the shipped manifest doesn't declare it and no crash/analytics SDK
is in the app — if one is ever added, update BOTH the manifest and this form.)

| Question | Answer |
|---|---|
| Does your app collect or share user data? | Collects, does not share |
| Data encrypted in transit? | Yes |
| Can users request data deletion? | Yes — in-app account deletion (Settings → Danger zone), plus web |
| **Personal info → Email address** | Collected, linked to identity, required, purpose: App functionality |
| **Financial info → Other financial info** (holdings, transactions) | Collected, linked to identity, required, purpose: App functionality |
| **Device or other IDs** (push token) | Collected, linked to identity, optional (only if notifications enabled), purpose: App functionality |
| Everything else (location, contacts, browsing, etc.) | Not collected |

## App Review notes (both stores)

> Cirvia is a read-only portfolio analysis app. It cannot trade or move money.
>
> **Demo account** (fully seeded — holdings, a morning digest, a deep-dive report,
> picks, and a watchlist, on the Pro plan so nothing is gated):
> Email: `review@cirvia.ca`
> Password: _(set when the account is created — see below)_
>
> Brokerage linking uses SnapTrade OAuth; the demo account uses manually entered
> holdings instead, so no brokerage credentials are needed to review any screen.
>
> There are no purchases, subscriptions, or upgrade links anywhere in the app.
> Account deletion is in Settings → Danger zone (two taps from the tab bar).
> Investment disclaimer appears in the digest footer and picks header.

Before submitting: sign up `review@cirvia.ca` through the app (Supabase owns the
credentials), then run `python scripts/seed_review_account.py --email
review@cirvia.ca` against prod, and put the real password in both review-notes
fields. Verify the account renders every screen the day you submit — a stale demo
account is a rejection.

## Screenshot plan

Same six shots both stores, portrait. iOS: 6.9" (1320×2868) required, 6.5"
(1284×2778) optional. Play: min 320px, max 3840px, 16:9 to 9:16; also needs the
1024×500 feature graphic.

Order sells the story — lead with the digest, not the sign-in:

1. **Morning digest** — the hero. Caption: "Your portfolio, briefed every morning."
2. **Dashboard** — metric strip + holdings + warning banners. "Everything that moved, and why."
3. **Chat mid-answer** — reasoning visible. "Ask anything. Watch it work."
4. **Stock detail** — chart + valuation verdict + evidence table. "Verdicts with the evidence attached."
5. **Deep dive report** — "Full research on what you own."
6. **Delivery settings** — push/SMS/email/Discord. "Delivered wherever you are."

Capture from the seeded review account (`npx expo run:ios` on the largest
simulator), so the data is realistic and consistent across shots. Status bar: use
simctl `status_bar` override (9:41, full battery/signal) before capturing.

## Remaining non-copy submission blockers (tracked in MOBILE_APP_PLAN.md)

- `IOS_TEAM_ID` + `ANDROID_CERT_FINGERPRINTS` in Railway (universal links 404 until set).
- Three `REPLACE_WITH_*` fields in `mobile/eas.json`; EAS secrets for the two Supabase values.
- Register App ID `ca.cirvia.app` before the first build.
- Supabase Auth redirect allowlist must include `https://cirvia.ca/app/auth/bridge`
  and `https://www.cirvia.ca/app/auth/bridge` (the mobile password-reset bridge).
- Play Console testing-period requirement — check in week 1.
