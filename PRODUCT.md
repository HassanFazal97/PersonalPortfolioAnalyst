# Cirvia — PRODUCT.md

## Register

Split-register project with one default per surface:

- **Brand** (design IS the product): `/`, `/pricing`, `/contact`, `/privacy`, `/terms` — rendered from `app/landing.py`.
- **Product** (design SERVES the product): `/app`, `/app/onboarding`, `/app/dashboard` — rendered from `app/webapp.py`.

## What it is

Cirvia is an AI portfolio analyst for Canadian retail investors. It connects to
Wealthsimple read-only via SnapTrade, then delivers a weekday morning digest,
macro alerts when world events touch the user's holdings, and on-demand chat
about their actual positions. It informs; it never advises buy/sell and never
trades.

## Users

Individual Canadian investors (TFSA / RRSP / taxable) who check their portfolio
on their phone in the morning and don't have time to read financial news all
day. They are not day traders. Context of use: mobile-first mornings, desktop
evenings.

## Desired outcome

Marketing pages convert a visitor into a free signup (`/app`). The app gets a
new user through brokerage connection to their first synced portfolio in under
three minutes.

## Brand personality

Three words: **measured, precise, nocturnal**.

The physical scene: a reader opening a well-typeset market brief before sunrise,
screen dimmed, coffee next to the phone. Dark is not a style choice here; it is
the ambient light of the product's core moment (pre-market mornings, evening
review).

## Voice

Plain language, specific nouns, no hype. "Read-only" and "not financial advice"
are stated confidently, not buried. No marketing buzzwords (seamless, empower,
supercharge). No em dashes in copy.

## Color strategy

**Committed.** Near-black violet-cast canvas carries the whole surface; one
midnight-purple accent for primary actions, focus, and the logo mark. No second
chromatic color except semantic market colors (gain green / loss red) inside
data displays.

## Anti-references (never look like)

- Purple-to-pink gradient AI startup pages; gradient text; glassmorphism cards.
- The 2023 SaaS scaffold: tiny uppercase eyebrow above every section, identical
  icon-card grids, hero-metric templates.
- Robinhood-style gamified trading energy. Cirvia is calm, not thrilling.
- Bank-beige corporate finance. Cirvia is personal software, not an institution.

## References (aesthetic lane)

Linear (surface ladder discipline, hairlines over shadows, one accent used
scarcely), Mercury (premium calm, product visuals native to the design system),
Vercel (typographic restraint). Lane: **software-craft dark minimalism**, with
Cirvia's own violet cast and editorial "morning brief" content shapes.

## Accessibility

Body text ≥ 4.5:1 contrast on all surfaces. Every animation has a
`prefers-reduced-motion` fallback. Marketing pages must render complete without
JavaScript (reveals only enhance already-visible content).
