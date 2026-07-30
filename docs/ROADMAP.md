# Cirvia → World-Class AI Quant Analyst: Strategic Roadmap

*Adopted 2026-07-30. Supersedes nothing; sits alongside `MULTI_TENANT_ROADMAP.md` (which remains future/unstarted).*

## Context

**The ask:** turn Cirvia into an AI quant analyst worthy of a top quant shop — and the best product for everyday investors: compelling enough that people try it, sign up, and genuinely benefit.

**Scope decisions:** all three fronts — quant analytics, growth & conversion, trust & accuracy — phased. Data budget free/cheap only (~$0–30/mo); no institutional vendors. Each phase is planned and implemented separately; this document is the map, not the specs.

**Ordering principle (governs every phase):** anything that blocks revenue or loses unrecoverable data comes before anything that improves analysis; activation comes before traffic; amplification comes last, after the proof surface exists. The most intellectually satisfying work (factor models, regime detection) is deliberately gated behind user milestones — it is the most dangerous work for a solo founder precisely because it is the most fun.

## Where the product stands (baseline as of Jul 30, 2026)

The analytical core is already unusually rigorous for a retail product — Ledoit-Wolf shrinkage covariance, Euler risk decomposition, Cornish-Fisher/historical VaR + CVaR, zero-drift Monte Carlo, mean-variance frontier (pure numpy, unit-tested vs closed-form identities in `app/quant/`), plus a Best Stocks pipeline (`app/agent/picks/`) with a pure-math factor screen, fact-sheet-grounded LLM analysts, deterministic evidence repair, an adversarial critic, and Python-computed confidence. Anti-hallucination is architectural ("every number computed in Python; the LLM only narrates") with an eval harness in `evals/`.

**Shipped Jul 30 (in `main` — do not re-plan):**
- Public (unauthenticated) `/track-record` page and `/stocks/picks/track-record` JSON — per-entry version: frozen entry price, return, S&P 500 same-span, misses shown. Payload TTL-cached 15 min (the homepage stat strip hits it on every load), cleared after picks runs.
- **Both track-record honesty bugs fixed** (were Phase 0 item 2): benchmark is now SPY adjusted close (total return) over each pick's exact span, synced nightly; returns are same-series adjusted-close ratios (last close before publication → latest bar), so yfinance re-adjustments can't fake a loss — entry_price is display-only. Split-scenario regression test in `tests/test_picks_api.py`.
- Benchmark **span-asymmetry fix**: the S&P comparison starts from the same prior-day close the entry price is frozen at (was first close ≥ run_date).
- Public `/sample-digest` page (faithful, clearly-labeled sample).
- Landing rewrite around "the AI analyst that shows its work": verification story, full feature ledger (Top Picks / Deep Dives / Risk Lab with Pro tags), track record in nav/footer, trial mention in CTAs; pricing page lists the full Pro feature set.
- Homepage live stat strip, gated on **≥30 measured picks** (small samples read as noise — keep this gate in every future version).
- Contact is `hello@cirvia.ca` (was a personal live.ca address). **Deploy blocker: set up receiving for that address (e.g. Cloudflare Email Routing) before this ships** — a dead contact link on legal pages is worse than a personal one.
- Request-path perf layer (`app/perf/`): verified-JWT + user-id caches, per-user dashboard snapshot store with SWR, `/dashboard/bootstrap` aggregated read, SnapTrade calls off-loop, quote-warm/positions-refresh jobs.

**The real gaps:**
1. **Data & validation** — yfinance fundamentals overwritten daily (no point-in-time history); static survivorship-biased ~560-name universe; factor weights hand-set, never validated out-of-sample; track record is raw price return vs `^GSPC` with no risk adjustment, per-entry (double-counts persistent picks), and carries two remaining honesty bugs (Phase 0).
2. **Activation** — the aha moment arrives with tomorrow's digest, ~18 hours after signup; brokerage link is required for any value; trial lapse silently pauses digests forever.
3. **Revenue** — Stripe may still be env-gated "coming soon" in prod (`app/billing.py:32`); USD pricing to an explicitly Canadian audience; personal `live.ca` contact email on the marketing site.
4. **Distribution** — zero SEO surface; no lifecycle email; no shareable artifacts.

**Strategic thesis:** Cirvia's rarest asset is a daily picks pipeline with adversarial verification, frozen entry prices, and demotion of challenged claims — now partially public. Finish making the honesty machine public, make the first three minutes prove the quant engine on the visitor's own portfolio, and let the track record be the marketing department. Because trust compounds with calendar time, data-provenance work ("start the clock") is urgent: every day without point-in-time snapshots is unimpeachable history permanently lost.

**Effort scale:** S ≈ 1–3 days · M ≈ 1–2 weeks · L ≈ 3+ weeks. (Honest total: this is a ~6-month roadmap. The phase labels are sequence, not calendar promises.)

---

## Phase 0 — This week: revenue on, honesty bugs off (all S)

1. **Ship billing live** — set the Stripe env vars in Railway prod, remove "coming soon" (`app/billing.py:32`). Until this is done, everything else on this roadmap is decoration: a trial funnel into a wall trains users that Pro isn't real. **This is item #1 in the entire plan.**
2. ~~Fix the two remaining track-record honesty bugs~~ **Done Jul 30** (see baseline above). *Interim caveat that survives the fix:* SPY is USD/US-only while the pick universe includes the TSX — the Phase 2 blended benchmark replaces it; note the mismatch on the methodology page until then.
3. **Fix trust contradictions** — ~~contact email~~ done (`hello@cirvia.ca`; receiving setup is a deploy blocker, see baseline); still open: a legal-entity footer once the entity name is settled.
4. ~~Trial mechanics~~ **Done Jul 30**: the trial arms at the first successful portfolio sync (`Repo.maybe_start_trial`, migration 024's `trial_started_at` prevents re-arming; existing accounts backfilled as consumed); the lapsed pause is bounded (`TRIAL_DECISION_GRACE_DAYS = 7` in `app/plans.py`) after which the account resumes as plain Free with no DB write; the daily `trial_notices` job (`app/trial_notices.py`, `TRIAL_NOTICES_CRON`) sends T-2 / day-of / +3 notices, deduped by payload kind, nothing to long-lapsed accounts.
5. ~~Reprice in CAD~~ **Done Jul 30**: $20/mo CAD, $160/yr CAD (annual keeps the exact "4 months free" math). No live subs existed, so no grandfathering — **create the Stripe prices in CAD** when doing item #1.
6. ~~SnapTrade return-flow polling~~ **Done** (shipped with the dashboard-shell work): the portal open starts a 5s `/portfolio/status` poll that auto-runs the first sync; the manual button remains as an immediate-check fallback.
7. ~~Funnel instrumentation~~ **Done Jul 30**: `funnel_events` table (migration 025, once-per-account PK) recording signup / portfolio_connected / trial_started / chose_free / upgraded / dashboard_viewed, plus owner-only `GET /funnel` counts. Anonymous page views stay in the `cirvia.funnel` log.

## Phase 1 — Weeks 1–4: start the clock, finish the proof surface, fix activation

**Data provenance (urgent because it compounds):**

1. ~~Point-in-time fundamentals by construction~~ **Done Jul 30** — `fundamentals_snapshots` (migration 026), appended nightly by `run_universe_sync` with payload hashes; error rows never snapshotted; `get_fundamentals_snapshots(as_of=D)` is the "as it would have run" read. **Clock starts on the first prod deploy.**
2. ~~Universe membership history + delisting handling~~ **Done Jul 30** — `universe_membership` (migration 027) diffed nightly from the deployed constituent lists (intervals close, never delete); prices keep syncing for tickers referenced by pick entries in the last 365d after they leave the universe.
3. ~~Cohort-based track record~~ **Done Jul 30** — `app/quant/trackrecord.py` (pure numpy, closed-form-tested): dated cohorts at fully-elapsed 7/30/91/182d horizons vs SPY total return over identical spans, plus the simulated top-5 portfolio (equal-weight per rebalance, buy-and-hold between runs) with Sharpe/max-drawdown/tracking-error reused from `performance.py`/`tailrisk.py`. Wired into the public payload (`cohorts`/`simulated`) and the /track-record page. Still open from the original item: per-run integrity line + git-hash tamper evidence (see #6), factor attribution (needs Phase 2 factor model).

**Activation (pulled forward — traffic is worthless if visitors bounce at the connect step):**

4. **Instant first analysis** (M) — on completing onboarding, immediately render a "your first briefing" (mini-digest + risk snapshot via `digest_pipeline.py` preview mode). Today the aha moment arrives with tomorrow's digest — ~18 hours too late. Biggest activation fix available.
5. **Manual portfolio entry fallback** (M) — "no brokerage link? type your holdings" (ticker + shares/weight) at the SnapTrade step. Linking a brokerage to an unknown site is the #1 drop-off; convert those users now, upsell the sync later.

**Proof surface (upgrades to what shipped Jul 30, not new pages):**

6. **Upgrade `/track-record` to the cohort version** (M) — cohort NAV chart vs benchmark, every pick ever made with dated frozen entry price, per-run integrity line (data as-of, methodology version, verification summary — already persisted). Publish full pick details (theses) with a **1-day delay**; today's board stays Pro. Tamper-evidence: at run time, **commit the picks payload's hash to a public git repo** (GitHub's commit timestamp makes it externally verifiable — unlike a hash on our own site); publish the full payload the next day and anyone can check it against yesterday's hash. Committing the payload itself at run time would leak the Pro board a day early; committing it a day later would leave a 24-hour editable window.
7. ~~Public methodology page~~ **Done Jul 30** — `/methodology` (auth-exempt, footer + track-record links): full pick pipeline, track-record measurement rules, quant-engine explainers, and an explicit limitations section including the interim-benchmark caveat and the not-yet-validated factor weights.
8. **One real public sample Deep Dive** (S) — a dated, real-ticker report linked from the hero, regenerated monthly. Sophisticated visitors smell mocked demo content instantly.
9. ~~Free-tier repackaging~~ **Done Jul 30** — `DEEP_DIVE_FREE_MONTHLY_LIMIT` (default 1 per rolling 30 days; 0 restores Pro-only) plus pricing-page copy. Track record already public. No mid-tier.

## Phase 2 — Months 2–3: widen the funnel; quant depth behind a user gate

**Funnel first:**

1. **Demo portfolio mode** (M) — one-click sample Canadian book (XEQT, RY, TD, ENB, SHOP, CNR…) pre-signup on the landing page and as an onboarding escape hatch, watermarked "sample data."
2. **Lifecycle email track** (M) — new lifecycle message type through the existing Resend adapter/dispatcher: day-0 welcome, day-2 "how to read your risk numbers," day-5 trial-ending, event-triggered "your brokerage connection broke" (silent sync failures are silent churn). CASL-compliant like the digest.
3. **Weekly Portfolio Report Card** (M) — Sunday, all plans: grade + week-over-week risk delta + best/worst holding + "N events flagged." The digest is news-shaped; the report card is progress-shaped — the artifact people screenshot. For Free users it's the primary upgrade surface.
4. **Public per-ticker pages** (M) — unauthenticated `/stock/{ticker}` across S&P 500 + TSX (~1,700 server-rendered pages with sitemap); TSX coverage is the wedge (near-zero quality competition for "SHOP.TO risk analysis"-class queries). **⚠ Licensing constraint (unresolved):** public republication of yfinance-scraped data violates Yahoo's ToS, and Finnhub's free tier restricts redistribution. These pages must lead with *Cirvia's own computed outputs* (factor-screen scores, risk stats, drawdown/beta computed from stored series, own commentary) with minimal raw quote display — or wait for a redistribution-licensed source. Do not discover this at scale; resolve the data-source question before building. **⚠ Ops constraint (also unresolved):** the app is a single-worker monolith with in-process APScheduler — 1,700 public pages plus crawler traffic would share one process with the digest crons and yfinance TTL caches. These pages need aggressive Cache-Control / pre-rendered static output / CDN in front before they ship, or a crawl spike delays everyone's morning digest.

**Quant engine (gate: start after ~50 paying subscribers, except item 5 which is cheap and wrong today):**

5. **Canadian benchmarks + real risk-free** (S — do early, no gate) — benchmark set (SPY, XIC.TO/XIU.TO, VBAL.TO blend, geography-inferred blended benchmark) replacing single `^GSPC`/interim SPY; Bank of Canada Valet API (free, no key) 3-month T-bill replacing the flat 4% `DEFAULT_RISK_FREE_ANNUAL`. A Canadian holding XIU deserves their market as the yardstick; also retires the Phase 0 interim-benchmark caveat.
6. **Statistical factor risk model** (M) — new `app/quant/factormodel.py`: regress holdings on free ETF factor proxies (SPY, XIU.TO, USDCAD, IWM−SPY size, IWD−IWF value, TLT rates) + PCA on residuals. Output "62% of your risk is one bet: US large-cap growth" alongside the existing Euler decomposition. The single most "professional analyst" insight retail tools lack; also feeds track-record attribution (skill vs beta rally).
7. **Regime detection** (M) — new `app/quant/regime.py`: defensible 2–3 state classifier (realized-vol quantile + trend sign), validated via the `calibrate_detectors.py` pattern. Conditions Risk Lab framing, digest tone, picks annotation. Names the regime without pretending to time markets.
8. **Walk-forward factor validation harness** (M/L) — new `scripts/validate_factors.py` + `app/quant/backtest.py` (pure-numpy rebalance simulator, shared with cohort NAV): monthly-rebalance reconstruction of the screen, per-factor information coefficients, quintile spreads, weight sensitivity. Honest caveat built in: only price factors are validatable day one; fundamentals factors become validatable ~12 months after PIT snapshots ship. Publish a dated "factor report card" on the methodology page; weight changes bump `METHODOLOGY_VERSION`.
9. **Transaction-cost-aware framing** (S) — spread/commission estimates netted from the simulated pick-portfolio NAV, shown wherever action is implied ("acting on daily rank changes would cost ~X%/yr — these are research signals, not trade signals").

## Phase 3 — Months 3–4+: features investors feel + amplification

**Product (all $0 data):**

1. **Portfolio health score** (M) — new `app/quant/health.py`: one 0–100 score with named sub-scores from existing machinery (effective bets, concentration HHI, CVaR percentile, currency balance, factor concentration post-factor-model). Deterministic, versioned, delta-tracked in the digest ("72 → 68: NVDA is now 31% of your risk"). The feature users screenshot.
2. **What-if scenario tool** (M) — "what if I trim NVDA to 10% / add $5k XIC?" — re-run the pure-numpy stack on hypothetical weights, show deltas. UI panel + agent tool so chat answers "should I trim?" with computed before/after numbers instead of vibes.
3. **Dividend safety score** (S/M) — payout ratio vs earnings and FCF, dividend growth streak, balance-sheet strain; robust-z composite in the screener's house style + detector alert ("payout crossed 90%"). "Is my dividend safe?" is a top-3 Canadian retail anxiety.
4. **Canadian tax-aware framing** (M) — new `app/quant/taxlocation.py`: TFSA/RRSP/taxable types already flow from SnapTrade. Deterministic asset-location analysis (US withholding drag in TFSA vs RRSP, eligible-dividend treatment) with concrete "$140/yr unrecoverable withholding" lines. Educational framing, never filing advice. Invisible to US-built competitors.
5. **Retirement projection upgrade** (M) — monthly contributions + inflation-adjusted terms (BoC CPI, free) + block-bootstrap alongside GBM (preserves fat tails), with the GBM-vs-bootstrap spread shown as model uncertainty.

**Amplification (only after the legal consultation below, and only once the cohort track record has ≥3 months of history):**

6. **Track record as content engine** (S/M) — auto-generated weekly recap permalink (`/track-record/2026-w31`) + email: picks vs index, wins and misses. A compounding content archive from a cron that already runs.
7. **Shareable risk card** (M) — post-analysis "share my risk card": tokenized public page/OG image with letter grade + percentiles — percentages only, never dollar values, opt-in.
8. **Remotion organic clips** (S) — repurpose `ad/` compositions into 15-second "yesterday's pick, verified, dated entry price" shorts, auto-templated from the picks payload. Organic only; no paid spend until the proof surface has traction.
9. **Cornerstone Canadian content + community** — 4–6 SEO articles (TFSA portfolio risk, the banks+XEQT concentration problem, methodology explainers); genuine-usefulness-only presence in r/CanadianInvestor (r/PersonalFinanceCanada bans promotion — the public ticker pages do the linking).
10. **Win-back + value counter** (S) — monthly "here's what you missed" with one concrete number about their last-synced portfolio; digest footer "since joining, Cirvia analyzed X digests, flagged Y anomalies."
11. **One launch moment** (S) — a "Show"-style launch (Product Hunt / HN / r/CanadianInvestor post) once the cohort track record has ≥3 months of history. The compounding channels above build slowly; one spike event with the "we show our misses" hook is cheap and times itself: the launch artifact *is* the track-record page.

## Phase 4 — Continuous from ~month 3: LLM layer + guardrails

1. **Quant-fluent chat** (M) — wire the new tools (what-if, health score, factor exposures, regime, tax location) into the agent registry; upgrade prompting so the agent plans multi-tool counterfactual answers; selective extended thinking on complex-analysis intents. The gap isn't model quality — it's that the agent can't yet run the counterfactual, which is what an analyst does.
2. **Proactive insight cards** (M) — weekly deterministic scanner (Python decides what's noteworthy: health deltas, factor drift, regime change, dividend downgrades, tax drag, cohort milestones), Haiku narrates — the proven `app/agent/anomaly/` pattern; dedupe via memory embeddings. An analyst who only answers when asked isn't an analyst. This is the retention engine.
3. **Eval expansion** (M, continuous) — golden cases per new tool with a numeric-consistency checker (every number in the answer must appear in a tool result within rounding); picks-narrative eval with adversarial fixtures (contradictory metrics → model must declare gaps); "correct answer is 'it depends'" cases judged for calibrated hedging. The trust story dies on one screenshot of the agent misquoting its own VaR.

## Regulatory posture (before Phase 3 amplification)

- **Adviser registration (Canada):** the picks pipeline is impersonal — lean into "informational publisher of dated model outputs" (the newsletter/publisher-consistent posture). Keep all personal-portfolio output rigorously descriptive (what your risk *is*), never prescriptive (what to buy/sell) — audit `app/agent/prompts.py` for prescriptive verbs.
- **Marketing language:** never "buy," "will outperform," or projected returns in ads/clips. Past performance shown must be complete (true by design), dated, benchmarked, with "past performance is not indicative" language. Rename "Best Stocks" in public marketing ("Model Picks" / "Daily Ranked Analysis") — it's the most recommendation-flavored phrase in the product.
- **CASL/PIPEDA:** lifecycle + win-back emails need the same consent/unsubscribe treatment as digests; share cards are percentages-only and opt-in.
- **Data licensing:** public per-ticker pages (Phase 2 #4) must not republish yfinance/Finnhub raw data — see the constraint noted there. User-authenticated analysis of their own portfolio is a different posture from public redistribution.
- **Action:** one consultation with a Canadian securities lawyer before putting money or virality behind picks marketing (Phase 3) — not needed to ship the public track record with disclaimers (already live).

## Explicitly deprioritized

Intraday anything (free data can't support it honestly) · full historical fundamentals backtesting (PIT-by-construction instead; the one candidate paid API — FMP/EODHD ~$25/mo for statement history — waits until the $0 walk-forward harness exists and 6+ months of snapshots have accumulated) · options/derivatives analytics (wrong audience) · ML return prediction (destroys the "every number is verifiable" position) · testimonials (until real ones exist) · referral programs/streaks/mid-tier pricing (loops that don't exist at this user count).

## Critical files

- `app/main.py` (`_track_record_payload`) — remaining honesty bugs (a)/(b), cohort migration
- `app/agent/picks/pipeline.py` — entry persistence (bar date), methodology versioning, cohorts, public git publication
- `app/tools/universe.py` + `scripts/refresh_universe.py` — PIT snapshots, membership history
- `app/quant/` — new: `trackrecord.py`, `factormodel.py`, `regime.py`, `health.py`, `taxlocation.py`, `backtest.py`; extend: `simulate.py`, `performance.py`
- `app/tools/portfolio_risk.py` — benchmark set, risk-free, health, what-if, factor model
- `app/plans.py` / `app/billing.py` — trial semantics, CAD pricing, Free packaging
- `app/landing.py` — methodology page, sample Deep Dive, contact fix, cohort track-record upgrade
- `app/webapp.py` — onboarding (manual entry, demo mode, instant first analysis)
- `app/delivery/` — lifecycle/win-back message types
- `evals/` — quant-surface golden cases, numeric-consistency checker

## Verification / success measures

- **Per-phase:** each initiative lands with tests in the existing style (quant modules vs closed-form identities; eval golden cases for LLM surfaces; `/verify` skill run for end-to-end flows).
- **Trust:** by month 3, the public track record is re-derivable from immutable snapshots, cohort-based, risk-adjusted, benchmark-honest — survivable under hostile scrutiny.
- **Growth instrumentation:** track signup → connect → first-briefing-viewed → trial decision funnel; organic search impressions on ticker pages; track-record page visits → signups.
- **North-star sequence:** billing live (Phase 0) → proof + activation (Phase 1) → funnel widened (Phase 2) → amplification (Phase 3). Don't amplify before the proof surface exists; don't build quant depth before ~50 paying users (exception: Canadian benchmarks/risk-free, which fix numbers that are wrong today).
