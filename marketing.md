# Cirvia Marketing — Operating Doc

**Last reviewed:** 2026-08-13 · **Phase:** Foundation complete → loop starts (week 3) · **Picks measured:** check `/stocks/picks/track-record` (headline stats unlock at ≥30)

This is the marketing *operating doc*: the angle, the hooks, the weekly loop, and the guardrails.
Strategy roadmap and product backlog live in [docs/ROADMAP.md](docs/ROADMAP.md) — this file references it, never duplicates it.
Ready-to-adapt copy (Reddit comments, the r/CanadianInvestor post, X bio/thread/first weeks) lives in [marketing-drafts.md](marketing-drafts.md).

---

## 1. Positioning & Angle

**The claim, everywhere:** *Cirvia is the AI analyst that shows its work.* Entry prices frozen at pick time. Misses never deleted. Every return dividend-adjusted and benchmarked against the S&P 500 over the identical span. An adversarial critic re-checks every claim against first-party data before it ships.

Why this is the spine (and not "great TFSA tool" or "watch me build"):
- **It can't be copied in a weekend.** Frozen entries, published misses, and adversarial verification are structural. Feature checklists aren't.
- **It manufactures content automatically.** The picks cron produces a dated, benchmarked artifact every trading day. Marketing = distributing an artifact that already exists.
- **It's compliance-armored by construction.** Complete, dated, benchmarked, misses included — exactly what Canadian securities marketing rules demand anyway.

The other angles are **channel wrappers** for the same claim, not alternatives:

| Channel | Wrapper (the hook) | Claim (the close) | Link target |
|---|---|---|---|
| Twitter/X | Founder build-in-public: the story of engineering honesty | "…which is why the record can't be faked" | /track-record, /methodology |
| Reddit | Canadian utility: TFSA/RRSP, Wealthsimple/Questrade pain | "…and here's the methodology, tear it apart" | /methodology only (never the homepage) |
| Email | The record itself, weekly, dated | wins *and* misses, benchmarked | /track-record recap permalink |

**Pre-proof rule (until ≥30 picks measured, ~week 6):** don't headline the record — headline the *machinery*. "Most tools show you a backtest. We're accumulating a live record in public — entry prices frozen, misses kept. Judge us in 30 days." The waiting period is itself the story.

**We never claim:** market-beating returns, "buy/sell" calls, advice of any kind. Cirvia informs; it never advises and never trades.

---

## 2. Message Pillars & Hook Bank

Tags: ✅ works pre-proof · 🔓 needs ≥30 picks measured.

**P1 — Radical transparency** (the record)
- 🔓 "Our worst pick this month was ___. It's still on the page. Nothing gets deleted."
- 🔓 Weekly: "Model Picks, week NN: X of Y beat the S&P 500 over the same span. Worst pick first: ___."
- ✅ "Every AI stock tool shows you its wins. Ours is built so it *can't* hide the losses — entry price freezes the moment a pick publishes."

**P2 — Honesty engineering** (build-in-public, founder voice)
- ✅ "My homepage hides its own performance stats until there are 30 measured picks. Small-n numbers are marketing, not evidence."
- ✅ "I built an adversarial critic whose only job is to attack my AI's claims — verify against source data only, no web search. Challenged picks get demoted."
- ✅ "Returns on our track record are computed at read time from dividend-adjusted closes. There's no evaluation job that could be gamed."

**P3 — Canadian utility** (the Reddit door-opener)
- ✅ "XEQT plus three Canadian bank stocks isn't diversification — it's one bet. Here's the correlation math."
- ✅ "What a 95% one-month VaR actually means for a $50k TFSA, in plain English."
- ✅ "Wealthsimple tells you what you hold. It doesn't tell you what could hurt you tomorrow morning. That gap is what I built for."

**P4 — Grounded AI** (anti-hallucination)
- ✅ "Every number is computed in Python from source data. The LLM only narrates. If a valuation figure doesn't match the fact sheet, a deterministic pass repairs it — no model in the loop."
- ✅ "You can watch the agent work: every tool call streams live. Ask about your portfolio and see exactly which data it pulled."
- ✅ "AI that asserts vs AI that proves — why we log every model and tool call so any analysis is replayable."

Voice check (per [PRODUCT.md](PRODUCT.md)): measured, precise, plain language, no hype. No "🚀", no "🧵👇", no engagement bait.

---

## 3. Channel Playbooks

### 3.1 Twitter/X — personal founder account (~2.5 hrs/week)

Persona: you, building Cirvia. Cadence: 3–4 posts/week + batched replies.

- **Monday anchor (45 min):** pre-proof → one honesty-engineering thread (P2). Post-proof → the weekly track-record recap (P1), worst pick named first, link to /track-record. Same content becomes the recap email and permalink — write once, publish three ways.
- **Midweek post (30 min):** one computed Canadian-investor insight (P3). Screenshot real product output — sample/demo data only, never user data.
- **Replies (15 min/day, 3–4 days):** CanFinTwit — threads about Wealthsimple, Questrade, XEQT, TFSA room, bank stocks. Add computed value. Link only if asked.
- Pin a "what I'm building and why the record can't be faked" thread. Bio links to /track-record.

> **Never:** quote returns without span + benchmark + past-performance line · "will outperform" or projected returns · buy followers/engagement · growth-hack thread formats that break the measured voice.

### 3.2 Reddit — aged account (~2 hrs/week)

The asset is account age + karma; the risk is burning it. **Rule zero: 90/10.** Nine value-only contributions for every one Cirvia mention, and mentions only where a tool question was explicitly asked or in a mod-cleared format. Always disclose: *"I'm the developer."* Always frame informational, not advice.

| Sub | Posture | What survives | Never |
|---|---|---|---|
| r/PersonalFinanceCanada | Comment-only, permanently | Helpful answers on portfolio risk, TFSA/RRSP mechanics — builds karma + market language | Any link or tool mention; PFC removes promotion, full stop |
| r/CanadianInvestor | 2–3 weeks of comments first, then ONE post | Text post, mod-messaged in advance: "I built this — tear apart my methodology," linking /methodology | Link-drops in comments; reposting the launch post; stealth "just found this tool" |
| r/Wealthsimple, r/Questrade | Most tolerant | Answering "how do I analyze my portfolio performance?" threads genuinely, plus a disclosed one-line mention (read-only, via SnapTrade); one intro post each, spaced weeks apart | Same-day identical cross-posts; answering every thread with your tool |
| r/fican, r/dividendscanada | Optional, comment-only | Drawdown/dividend-safety discussion | Promotion |

Time: 3 sessions × 25 min commenting; one carefully written post every 2–3 weeks (45 min).

**The highest-trust move available:** when a skeptic lands a fair critique, thank them and fold it into /methodology publicly, then say so in the thread.

> **Never:** alt accounts or astroturfing · DMing people · posting before reading the sub's self-promo rules · arguing with skeptics.

### 3.3 Email — starting from zero, under CASL (~1 hr/week)

Two consent lanes, kept separate:
1. **Product signups** (express consent at signup / existing business relationship): the day-0/2/5 lifecycle track — already specced as [ROADMAP Phase 2 #2](docs/ROADMAP.md); not duplicated here.
2. **Public recap list (the asset to build):** single-field opt-in on /track-record and /sample-digest:
   > *"Get the weekly Model Picks recap — every pick, every miss, benchmarked. Weekly. Unsubscribe anytime."*
   Clearly-described single purpose = valid CASL express consent. Every send: sender identification + mailing address + one-click unsubscribe (the Resend digest infra already does this pattern).

The weekly email **is** the Monday anchor content — one artifact, three channels.

> **Never:** auto-enroll app signups into the marketing list without a checkbox · buy/scrape lists · "buy"/"outperform" language · omit the past-performance disclaimer.

---

## 4. Weekly Operating Loop (~5.5 hrs)

- [ ] **Mon (45m):** anchor thread — honesty-engineering (pre-proof) or track-record recap (post-proof)
- [ ] **Mon (30m):** recap email + permalink (reuses anchor content; starts week 4)
- [ ] **Wed (30m):** Canadian-insight post (P3), with product-output screenshot
- [ ] **3× (25m each):** Reddit value sessions (PFC + r/CanadianInvestor + WS/QT subs)
- [ ] **Daily-ish (15m × 4):** Twitter replies in CanFinTwit
- [ ] **Fri (15m):** metrics review — `GET /funnel` deltas, top referrers, opt-ins; one keep/kill call

---

## 5. Marketing-Enabling Backlog

Ranked by leverage. Each row points at [docs/ROADMAP.md](docs/ROADMAP.md) — do not grow this table; everything else lives there.

| # | Item | Roadmap ref | Why it's here |
|---|---|---|---|
| 1 | **/methodology page** | Phase 1 #7 | The compliant link target for every channel. Nothing else works without it. |
| 2 | ~~**Referrer + UTM capture in funnel middleware**~~ **Done** (`app/main.py:1265`) | new, ~S | Logs `referer` + all five `utm_*` params. Every checkpoint in §6 depends on this. |
| 3 | **Weekly recap permalink + CASL opt-in form** | Phase 3 #6, pulled forward to week 4 | Roadmap gates *amplification* on 3-month history; *accumulating* the archive + list should start now. |
| 4 | ~~**"Model Picks" rename on all public surfaces**~~ **Done Aug 13** | Regulatory posture section | Compliance prerequisite before any public post mentions picks. Surfaces said "Top Picks" — a superlative claim in the same family as "Best Stocks"; renamed across `landing.py`, `webapp.py`, `trial_notices.py`. Internal module/docstring names still say "Best Stocks" — code-only, not public. |
| 5 | **One real public sample Deep Dive** | Phase 1 #8 | The shareable "whoa" artifact for threads and the r/CanadianInvestor post. |
| 6 | **Weekly Portfolio Report Card** | Phase 2 #3 | The user-screenshot artifact. Later — respect the time budget. |

**Blocker check (Phase 0): both cleared.** Billing live in prod (Stripe env vars confirmed in Railway, Jul 30). `hello@cirvia.ca` receiving verified Aug 13 — ImprovMX catch-all on the GoDaddy DNS, test send logged `DELIVERED` (details in [ROADMAP item 3](docs/ROADMAP.md)).

---

## 6. 90-Day Plan & Milestones

**Weeks 1–2 — Foundation (no public promotion):**
- [x] Ship backlog #1, #2, #4; confirm Phase 0 blockers cleared — **all done Aug 13**
- [ ] Twitter bio + pinned thread live — account not yet created (`x@cirvia.ca` now works for signup)
- [ ] Begin Reddit comment-only participation (PFC + r/CanadianInvestor), zero links — **not started; this is the long-lead item, see below**
- [x] **Baseline `GET /funnel`, read from prod Aug 13:** signup **0** / connected **0** / trial **0** / upgraded **0**. Only event ever recorded is `dashboard_viewed` (1). Supporting tables: 3 `users`, 40 `positions` — all predating migration 025, which is why they carry no funnel rows.

> **Instrumentation caveat on the baseline.** `signup` and `portfolio_connected` have never fired once in prod. The emitting code exists (`app/main.py:2011`, `:2080`) but is unverified end-to-end. The §6 decision rule — pause the loop if day-30 connect rate is <30% — reads from counters that have never incremented, so a broken emitter is indistinguishable from no traction. **Verify with one real signup + sync before day 30**, or the kill/keep call is made on noise.

**Lead-time note:** Reddit is the only Foundation item that can't be compressed — r/CanadianInvestor wants 2–3 weeks of comment history *before* the one post, and that clock starts only when commenting starts. It's unblocked by everything else (comment-only, zero links, no product claims).

**Weeks 3–6 — The loop starts (pre-proof messaging):**
- [ ] Weekly loop (§4) running
- [ ] Week 4: ship backlog #3; send first recap email (however few subscribers)
- [ ] Weeks 4–5: first disclosed posts in r/Wealthsimple and r/Questrade (spaced)
- [ ] Weeks 5–6: ship backlog #5; one thread walking through the Deep Dive

**Weeks 7–12 — Proof unlocks (≥30 picks measured, stat strip live):**
- [ ] Monday anchor becomes the true track-record recap (wins and misses, benchmarked)
- [ ] Weeks 7–8: the ONE r/CanadianInvestor "tear apart my methodology" post, mod-cleared
- [ ] Weeks 8–12: keep the loop; test one 15-second Remotion clip from `ad/` (one render, measure, no pipeline)
- [ ] Week 12: launch kit prepared — PH/HN/r/CanadianInvestor launch moment fires at ~3 months of cohort history per [ROADMAP Phase 3 #11](docs/ROADMAP.md), i.e. month 4–5

**Checkpoints** (from `GET /funnel` + page-view log; modest on purpose — starting from zero):

| Day | Target |
|---|---|
| 14 | Foundation shipped · baseline recorded · 10+ Reddit value comments · pinned thread live |
| 30 | 10 signups · ≥5 connected (**connect rate ≥50% is the number to watch**) · 25 recap opt-ins · first non-direct referrer |
| 60 | 40 signups · 20 connected · ≥5 trials · first paid upgrade · 75 opt-ins · one Reddit post ≥25 upvotes that survived moderation |
| 90 | 100 signups · ≥3 paying · 150 opt-ins · /track-record or /methodology in top-3 referrer paths before signup · launch kit ready |

**Decision rule:** if day-30 connect rate is **<30%**, pause the loop and shift the hours to ROADMAP activation items (instant first analysis, manual portfolio entry). Traffic into a leaky connect step is wasted.

---

## 7. Compliance Guardrails — pre-publish checklist (every public artifact)

- [ ] No "buy," "sell," "will outperform," or projected returns
- [ ] Any performance shown is complete, dated, benchmarked same-span, **misses included**
- [ ] "Past performance is not indicative of future results" present wherever performance appears
- [ ] Says **"Model Picks"** — never "Best Stocks" — in public copy
- [ ] Informational framing; "not financial advice" where performance or holdings analysis appears
- [ ] Emails: CASL sender ID + mailing address + unsubscribe link; consent lane noted (signup vs public opt-in)
- [ ] Screenshots: sample/demo data only — no user data, dollar values, or identifiable holdings
- [ ] Copy quotes real product numbers: Free = weekly Monday digest, 3 chat questions/week, 1 account; Pro = **CAD $20/mo or $160/yr ("4 months free")**, daily weekday digest, 10 questions/day; 7-day no-card Pro trial starting at first portfolio sync (verify against `app/config.py` before publishing)

---

## 8. Metrics & Review Ritual

- **Source of truth:** owner-only `GET /funnel` (signup / portfolio_connected / trial_started / chose_free / upgraded) + the `cirvia.funnel` page-view log (referrer/UTM once backlog #2 ships). No third-party analytics — cheaper and more honest.
- **Friday, 15 minutes:** funnel deltas vs last week · top referrers · email opt-in count · **one keep/kill call** (drop the lowest-performing recurring activity or double down on the best one).
- Update the status header of this file (phase, picks-measured) at each review.

---

## 9. Do-Not-Do

- Paid ads (organic only, and per roadmap no spend until the proof surface has traction)
- Link-dropping in finance subs; any promotion in r/PersonalFinanceCanada
- Alt Reddit accounts, astroturfing, DM outreach
- Buying or scraping email lists; emailing anyone without a CASL consent lane
- Product Hunt / HN launch before ~3 months of cohort track-record history
- Testimonials and referral programs (explicitly deprioritized in ROADMAP)
- LinkedIn, YouTube long-form, TikTok, cold outreach — out of scope for 5–10 hrs/week
