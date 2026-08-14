# Cirvia — Content Drafts (Reddit + X)

**Created:** 2026-08-13 · **Phase:** pre-proof (headline the machinery, not the record)
**Companion to** [marketing.md](marketing.md) — that file holds the strategy and guardrails; this one holds the words.

> **Every `[COMPUTE: …]` marker is a number you generate with Cirvia and paste in.**
> Nothing in this file invents a statistic. In a niche where your entire positioning is
> "shows its work," a made-up correlation coefficient is an unrecoverable credibility loss.
> If you can't compute it, cut the sentence — don't estimate it.

---

## 1. Where to participate

Reddit blocks automated access, so subscriber counts and rule text below are from your
existing doc plus general 2026 self-promo guidance — **read each sidebar yourself before
your first post in that sub.** Rules change and mods enforce locally.

| Sub | Posture | First move | Hard line |
|---|---|---|---|
| **r/PersonalFinanceCanada** | Comment-only, permanently | Start today. Highest volume of answerable questions. | No links, no tool mention, ever. PFC removes self-promo on sight. |
| **r/CanadianInvestor** | Comment 2–3 weeks → then ONE post | Start commenting today; the clock for the post starts now | Mod-message before the post. No link-drops in comments meanwhile. |
| **r/Wealthsimple** | Most tolerant | Answer "how do I analyze my performance" threads | One disclosed intro post, then leave it alone for weeks |
| **r/Questrade** | Most tolerant | Same as above | Never same-day cross-post with r/Wealthsimple |
| **r/fican**, **r/dividendscanada** | Optional, comment-only | Only if you have spare capacity | Promotion of any kind |

**Deliberately excluded:** r/investing and r/stocks. Both are US-centric with aggressive
automod on anything tool-shaped, and neither matches your Canadian TFSA/RRSP wedge. Volume
without fit costs you the account.

**The 90/10 rule is the floor, not the target.** Nine genuine contributions per mention.
At your stage the correct ratio is closer to 30/1 — you are accumulating standing, not traffic.

---

## 2. Reddit comment drafts

These map to threads that recur weekly in PFC and r/CanadianInvestor. Adapt, never paste
verbatim — identical comment text across accounts and subs is the fastest way to get flagged.

**Universal rules for every comment below:** no link, no Cirvia mention, no "DM me."
If someone asks what you use, *then* you disclose. Not before.

---

### 2.1 — Thread type: "Is XEQT + [Canadian banks] diversified?"

> XEQT already holds those banks — that's the part worth checking before you add more.
> It's roughly [COMPUTE: XEQT's actual % weight in Canadian financials] financials, so
> buying RY/TD/BNS on top isn't adding a position so much as concentrating one you
> already have.
>
> The thing to look at isn't the count of tickers, it's how they move together. Canadian
> banks have historically been tightly correlated with each other — same domestic rate
> environment, same mortgage book exposure, same regulator. Five of them behaves a lot
> closer to one bet than five.
>
> If you want to check it on your own holdings rather than take my word: pull daily
> closes for each position and compute the correlation matrix. Anything consistently
> above ~0.7 pairwise is telling you those two aren't doing separate jobs in the portfolio.

*Why it works:* answers the actual question, gives a method they can run themselves,
makes zero claims about what they should buy.

---

### 2.2 — Thread type: "How much of my TFSA is too much in one stock?"

> There isn't a clean threshold, but there's a better question than the percentage:
> what's the realistic bad month, in dollars, and would you sell if it happened?
>
> One way to get at it: take the position's daily volatility over the past year, and
> look at roughly the 5th-percentile monthly move. That gives you a "1-in-20 months
> looks about this bad" figure. On a $50k TFSA with a concentrated single name, that
> number is usually a lot larger than people expect when they're thinking in percentages.
>
> The percentage doesn't scare anyone. The dollar figure does, and the dollar figure is
> the one that actually predicts whether you'll panic-sell at the bottom — which is the
> real risk to your returns, not the volatility itself.

*Why it works:* teaches the VaR concept in plain language without jargon-dropping,
and reframes toward behaviour. Pure P3 pillar.

---

### 2.3 — Thread type: "Wealthsimple/Questrade shows me my returns — what else should I track?"

> Those platforms are good at the backward-looking part: what you hold, what it did.
> The gap I keep running into is forward-looking risk — nothing tells you which of your
> positions are quietly doing the same job, or what a bad week actually costs you.
>
> Three things worth tracking that neither platform surfaces by default:
> - **Correlation between your top holdings** — are your "different" positions one bet?
> - **Sector concentration including what's inside your ETFs** — the look-through is
>   where people find out they're 40% financials.
> - **Drawdown tolerance in dollars, not percent** — see above.
>
> All three are computable from data you already have access to; none of them show up
> on a standard performance screen.

*Why it works:* names a real gap without naming your product. If someone replies
"is there a tool for this?" — that is your disclosed opening, and only then.

---

### 2.4 — Thread type: someone posts an AI stock-picking tool / "I asked ChatGPT for stock picks"

> Worth asking of any of these, including the ones I'd build myself: can you see the
> picks it got wrong?
>
> The failure mode isn't the model being dumb, it's the record being curated. If entry
> prices aren't frozen at publication and losers can quietly leave the page, the track
> record is a marketing asset rather than evidence. Same for returns quoted without
> a benchmark over the identical span — a 12% gain in a year the index did 20% is a
> loss you're being shown as a win.
>
> The questions that separate the two: are entries timestamped and frozen? Are misses
> still visible? Is every return dividend-adjusted and benchmarked same-span?

*Why it works:* this is your entire thesis stated as a consumer-protection heuristic.
It is the single highest-leverage comment you can make, and it works *before* you have
a record of your own. Note the "including the ones I'd build myself" — pre-emptive
honesty that reads as credible rather than promotional.

---

### 2.5 — Disclosure template (only when directly asked)

> Full disclosure, I'm the developer, so treat this as biased — I built a tool that does
> exactly this, which is why I have opinions about it. Happy to explain the methodology
> if that's useful, and equally happy if you'd rather just have the method so you can do
> it yourself: [restate the method in two sentences].

*Why it works:* discloses first, offers the method free, makes the tool optional.
Never leads with a link. If they want it, they'll ask again.

---

## 3. The one r/CanadianInvestor post

**Do not post this until:** 2–3 weeks of comment history, `/methodology` verified live,
and a mod modmail sent and answered.

### 3.1 Modmail (send first)

> Subject: Permission check — methodology post, self-disclosed developer
>
> Hi mods — I've been commenting here for a few weeks. I've built a Canadian
> portfolio-analysis tool and I'd like to post the methodology for criticism, not as
> promotion: how picks are generated, why entry prices are frozen at publication, and
> why losses stay on the record.
>
> I'd disclose developer status in the first line, link only the methodology page (not
> the homepage or any signup), and I'm not selling anything in the post. If that's not
> something you allow, no problem at all and I won't post it. If there's a format or
> flair you'd prefer, I'll follow it.

### 3.2 The post

**Title:** `I built a Canadian portfolio analyser and published the methodology — tear it apart`

> I'm the developer, so read this as biased. I'm posting the methodology rather than the
> product because the methodology is the part worth arguing about, and I'd rather find
> out now where it's wrong.
>
> The problem I started from: every AI stock tool shows you its wins. Almost none are
> built so they *can't* hide the losses. That's a structural property, not a promise, so
> here's how I tried to make it structural:
>
> **Entry prices freeze at publication.** The moment a pick publishes, its entry price is
> written down and never recalculated. There's no evaluation job that could revise it later.
>
> **Misses are never deleted.** A pick that goes badly stays on the public record with the
> same prominence as one that goes well. There is no delete path in the code.
>
> **Returns are computed at read time from dividend-adjusted closes,** benchmarked against
> the S&P 500 over the identical span. Not a stored number that could drift from reality.
>
> **Headline stats stay hidden until 30 picks have fully-measured outcomes.** Small-n
> performance numbers are marketing, not evidence. Right now the page shows the machinery
> and withholds the averages, because I don't think I've earned them yet.
>
> **An adversarial critic re-checks every claim against first-party data before it ships** —
> no web search, source data only. Challenged claims get demoted or flagged.
>
> Known limitations, since you'd find them anyway:
> - The benchmark is the S&P 500, which is USD and US-only, while the universe includes
>   the TSX. That's a real mismatch and a blended benchmark is the fix. It isn't built yet.
> - The record is [COMPUTE: N] days old. That is not long enough to conclude anything and
>   I'm not asking you to conclude anything from it.
> - [COMPUTE: any third limitation you actually have — a real one, not a humblebrag]
>
> Methodology is here: [/methodology link]
>
> What I'm asking for: tell me where the measurement is wrong. Specifically — is
> same-span S&P benchmarking the right comparison for a TSX-inclusive universe, or does
> that flatter the record in a way I'm not seeing?
>
> Not financial advice, informational only, past performance is not indicative of future
> results.

*Why it works:* the ask is criticism of a specific technical decision, which gives
commenters something concrete to do besides judge you. The limitations section is
the credibility engine — it pre-empts the top comment. **The closing question is real;
if someone lands a fair critique, fold it into `/methodology` and say so in-thread.
That is your single highest-trust available move.**

---

## 4. X / Twitter

Personal account, per the earlier decision. `@CirviaAI` registered as a placeholder only.

### 4.1 Bio

> Building Cirvia — an AI analyst for Canadian portfolios that publishes its misses.
> Entry prices frozen at pick time. Every return benchmarked same-span.
> Not advice. cirvia.ca/track-record

150 chars of substance, zero hype, link goes to the proof surface rather than the homepage.

### 4.2 Pinned thread

> **1/** Most AI stock tools show you their wins. I'm building one that structurally
> can't hide its losses. Here's what that means in code, not marketing.
>
> **2/** When a pick publishes, its entry price is written down and frozen. There is no
> job anywhere in the system that can revise it afterward. If the price were revisable,
> the record would be an opinion.
>
> **3/** Losing picks stay on the public page with the same prominence as winners. Not
> "archived." Not collapsed behind a tab. There is no delete path in the code, which is
> the only version of this promise that survives me having a bad month.
>
> **4/** Returns are computed at read time from dividend-adjusted closes, benchmarked
> against the same index over the identical span. A 12% return in a year the index did
> 20% is a loss. Quoting it without the benchmark would make it look like a win.
>
> **5/** My homepage hides its own performance stats until 30 picks have fully-measured
> outcomes. Below that, averages are noise dressed as evidence. The stats are gated in
> code — I can't flip them on early even if I want to.
>
> **6/** There's an adversarial critic in the pipeline whose only job is to attack the
> analysis before it ships. Verify against source data, no web search. Claims it
> challenges get demoted.
>
> **7/** None of this makes the picks good. It makes them *checkable*, which is a
> different and more boring claim. Judge it in 30 days: cirvia.ca/track-record
>
> Not financial advice. Past performance is not indicative of future results.

Note tweet 7 — refusing the stronger claim is what makes the first six credible.

### 4.3 First three weeks

**Week 1 · Monday anchor (P2):**
> I built an adversarial critic whose only job is to attack my own AI's output before
> it reaches anyone. It verifies against first-party source data with web search
> disabled — if it can't confirm a number from the fact sheet, the claim gets demoted.
> Most of what it catches is confident phrasing on thin evidence.

**Week 1 · Wednesday (P3, screenshot — demo data only):**
> "XEQT plus three Canadian banks" is the most common Canadian portfolio I see, and it
> isn't three positions plus a fund. XEQT is already [COMPUTE: %] financials, so the
> banks are concentration, not diversification. Here's the correlation matrix.
> [screenshot — sample data, no user holdings, no dollar values]

**Week 2 · Monday (P2):**
> My track record page hides its own headline stats until 30 picks are fully measured.
> That gate is in code, not policy. I built it that way specifically so that a good
> early run couldn't tempt me into publishing an average built on eleven data points.

**Week 2 · Wednesday (P4):**
> Every number in a Cirvia analysis is computed in Python from source data. The language
> model only narrates. If a valuation figure in the prose doesn't match the fact sheet,
> a deterministic pass repairs it — no model in that loop. LLMs are good writers and
> unreliable calculators; the architecture takes that literally.

**Week 3 · Monday (P2):**
> Returns on the track record aren't stored. They're recomputed at read time from
> dividend-adjusted closes every time the page loads. There's no evaluation job whose
> output I could quietly correct, because there's no stored number to correct.

**Week 3 · Wednesday (P3):**
> What a 95% one-month VaR actually means for a $50k TFSA, in plain English: roughly
> one month in twenty is expected to be at least this bad. It's not a worst case — it's
> the edge of the ordinary. People consistently underestimate it because they think in
> percentages, and percentages don't feel like money.

### 4.4 Replies — 15 min/day, 3–4 days a week

Where: threads about Wealthsimple, Questrade, XEQT, TFSA contribution room, Canadian banks.
What: add a computed observation or a method. Link only if asked.
The §2 comment drafts adapt directly — compress to 2–3 sentences.

> **Never:** quote returns without span + benchmark + past-performance line · "will
> outperform" or any projected return · engagement-bait formats · buying followers ·
> screenshots containing user data, dollar values, or identifiable holdings.

---

## 5. What I deliberately did not write

- **Any specific number.** Every statistic is a `[COMPUTE: …]` marker. See the top of this file.
- **Post-proof content** (🔓 hooks — "X of Y beat the index," "worst pick this month was ___").
  Locked until `/track-record` shows ≥30 measured picks. Check the page, don't assume.
- **Launch content** (Product Hunt / HN). Roadmap gates that on ~3 months of cohort history,
  i.e. month 4–5. Writing it now would only tempt you to fire it early.
- **Anything for LinkedIn, YouTube, or TikTok** — out of scope per marketing.md §9.

## 6. Pre-publish checklist

Run [marketing.md §7](marketing.md) against every item above before it ships. The three
that catch the most drafts: no "buy/sell/will outperform" · performance always dated +
benchmarked + misses included · screenshots are demo data only.
