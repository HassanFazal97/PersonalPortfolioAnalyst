# Cirvia — DESIGN.md

Visual system for all surfaces. Tokens live as CSS custom properties in
`app/landing.py` (`_CSS`, shared) with app-register overrides in
`app/webapp.py` (`_APP_CSS`). Colors are OKLCH.

## Color

### Canvas & surface ladder

| Token | Value | Use |
|---|---|---|
| `--bg` | `oklch(13% 0.014 300)` | page canvas (near-black, violet cast; never pure #000) |
| `--surface-1` | `oklch(17% 0.016 300)` | cards, panels |
| `--surface-2` | `oklch(20% 0.018 300)` | inputs, hovered tiles, nested panels |
| `--surface-3` | `oklch(24% 0.02 300)` | active/lifted elements, dropdowns |

Hierarchy comes from surface lift + hairlines, not drop shadows.

### Hairlines

| Token | Value |
|---|---|
| `--line` | `oklch(27% 0.018 300)` |
| `--line-strong` | `oklch(35% 0.022 300)` |

### Text

| Token | Value | Use |
|---|---|---|
| `--ink` | `oklch(94% 0.008 300)` | headings, primary text |
| `--ink-2` | `oklch(79% 0.02 300)` | body copy |
| `--ink-3` | `oklch(66% 0.024 300)` | metadata, captions (≥4.5:1 on `--bg`) |

### Accent (midnight purple)

One chromatic accent. Reserved for primary CTAs, focus rings, links, the logo
mark, and selected states. Never decoration, never gradients, never text fills.

| Token | Value | Use |
|---|---|---|
| `--accent` | `oklch(48% 0.18 295)` | primary button fill (white text ≈ 4.8:1) |
| `--accent-hover` | `oklch(55% 0.18 295)` | button hover |
| `--accent-text` | `oklch(76% 0.12 295)` | links, accent text on dark |
| `--accent-deep` | `oklch(30% 0.10 295)` | tinted fills at low emphasis |

### Semantic (data only)

| Token | Value |
|---|---|
| `--gain` | `oklch(76% 0.13 155)` |
| `--loss` | `oklch(72% 0.14 25)` |
| `--warn` | `oklch(80% 0.11 85)` |

## Typography

**One family: Schibsted Grotesk** (Google Fonts, 400–900 + italics). A
newspaper-lineage grotesque; fits the "morning brief" brand without the
saturated defaults (Inter / Space Grotesk / etc.). Weight contrast carries
hierarchy. Numbers in data displays use `font-variant-numeric: tabular-nums`.

- Marketing scale (fluid): h1 `clamp(2.4rem, 6vw, 4rem)` w800 ls-0.03em;
  h2 `clamp(1.6rem, 3.4vw, 2.2rem)` w700 ls-0.02em; lead 1.2rem; body 1rem.
- App scale (fixed rem, ratio ≈1.2): h1 1.5rem w700; h2 1.25rem w650;
  h3 1.05rem w600; body 0.95rem; caption 0.8rem.
- `text-wrap: balance` on h1–h3. Line-height 1.65 body (light-on-dark bump).

## Spacing / radius / z

- Spacing: 4px base. Section padding `clamp(4rem, 9vw, 7rem)` on marketing;
  1.5rem panel padding in app.
- Radius: `--r-s: 8px`, `--r-m: 12px`, `--r-l: 18px`, pill `999px`.
- Z scale: nav 10, dropdown 20, modal-backdrop 30, modal 40, toast 50.

## Motion

Engine: `motion` (framer-motion's vanilla build) from jsDelivr, global
`Motion`. Ease: `[0.22, 1, 0.36, 1]` (ease-out-quint family). No bounce.
All motion behind a `prefers-reduced-motion` check; content is visible by
default and JS hides-then-reveals, so no-JS renders complete.

- **Brand:** one hero entrance (staggered rise, 0.7s), `inView` scroll reveals
  (0.6s rise) on section content, stagger (80ms) inside row/card groups,
  120ms transform on CTA hover (CSS).
- **Product:** 150–250ms state transitions only. Skeleton shimmer for loading,
  onboarding panel crossfade/slide 220ms, holdings row stagger 40ms on first
  load. No page-load choreography.

## Components

- **Button primary:** accent fill, white text, pill radius, 600 weight,
  1px transparent border; hover lifts fill (`--accent-hover`), 120ms.
- **Button ghost:** transparent, `--line-strong` border, ink text; hover
  `--surface-2`.
- **Panel:** `--surface-1`, 1px `--line`, `--r-l`.
- **Input:** `--surface-2`, 1px `--line`, `--r-s`; focus ring 2px accent.
- **Ledger row** (marketing feature list): grid title/desc/meta, hairline
  separators, no cards.
- **Table (app):** hairline row separators, `--ink-3` uppercase 0.72rem
  headers, tabular numerals, gain/loss colors on deltas only.
- **Skeleton:** `--surface-2` block with slow opacity pulse.

## Bans (project-specific, absolute)

Gradient text; purple→pink gradients; glassmorphism; uppercase tracked eyebrow
labels above sections; identical icon-card grids; hero-metric template; side
accent stripes (`border-left` > 1px); shadows as primary hierarchy.
