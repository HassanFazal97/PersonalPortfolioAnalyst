/**
 * The web design system, ported 1:1.
 *
 * Source of truth is the `:root` block in `app/landing.py`. Those values are
 * authored in oklch, which React Native's colour parser does not understand,
 * so each one is converted to sRGB here and the original is kept in the
 * comment beside it. When a token changes on the web, change it here and
 * re-run the conversion — never eyeball a replacement, the hue drift shows.
 */

export const color = {
  bg: '#f8f5fc', // oklch(97.5% 0.01 305)   warm lavender-tinted canvas
  surface1: '#fdfcff', // oklch(99.2% 0.004 305)  cards
  surface2: '#f1edf6', // oklch(95.2% 0.012 305)  inputs, chips, hover fills
  surface3: '#e9e3f0', // oklch(92.5% 0.018 305)  tracks, user chat bubbles
  line: '#e1dbe8', // oklch(90% 0.018 305)
  lineStrong: '#c8c0d2', // oklch(82% 0.026 305)

  ink: '#241e30', // oklch(25% 0.035 300)
  ink2: '#423c4e', // oklch(37% 0.03 300)
  ink3: '#605a6c', // oklch(48% 0.03 300)   muted; ~5:1 on bg, going lighter fails AA

  accent: '#7250ba', // oklch(52% 0.16 295)   white text on it stays AA
  accentPressed: '#5e3ba3', // oklch(45% 0.16 295)
  accentText: '#6040a1', // oklch(46% 0.15 295)
  accentDeep: '#e9e3ff', // oklch(93% 0.045 295)  pale fill, paired with accentText
  accentWash: '#f2eaff', // oklch(95% 0.035 300)
  accentBorder: '#d9d2f6', // oklch(88% 0.05 295)

  gain: '#1e7546', // oklch(50% 0.11 155)
  loss: '#a83634', // oklch(50% 0.15 25)
  warn: '#976200', // oklch(54% 0.12 75)
  warnBg: '#ffefd5', // oklch(96% 0.04 75)
  warnBorder: '#eccb9e', // oklch(86% 0.07 75)
  warnInk: '#55310f', // oklch(35% 0.07 60)

  shadow: '#3e3451', // oklch(35% 0.05 300)   always used at low alpha
  white: '#ffffff',
} as const;

/**
 * Allocation donut palette — `PIE_COLORS` / `PIE_OTHER` in `app/webapp.py`.
 * Order matters: slice i takes entry i, so a holding keeps its colour between
 * the web and the app.
 */
export const pieColors = [
  '#855bdc', // oklch(58% 0.19 295)
  '#de6f00', // oklch(66% 0.17 55)
  '#cc4da9', // oklch(62% 0.19 340)
  '#20a04e', // oklch(62% 0.16 150)
  '#0085c5', // oklch(58% 0.15 235)
  '#b77900', // oklch(62% 0.18 85)
  '#009993', // oklch(60% 0.14 190)
  '#c8393a', // oklch(56% 0.18 25)
] as const;

export const pieOther = '#7b7882'; // oklch(58% 0.015 300)

/**
 * 4pt grid. Screen padding is `space.s4`; card padding is `space.s3`.
 *
 * The steps carry an `s` prefix because a bare numeric key can only be reached
 * with bracket notation — `space.s3` is a syntax error, and `space[3]` reads
 * badly at every call site.
 */
export const space = {
  s0: 0,
  s1: 4,
  s2: 8,
  s3: 12,
  s4: 16,
  s5: 20,
  s6: 24,
  s7: 32,
  s8: 40,
  s9: 56,
} as const;

/** `--r-s` / `--r-m` / `--r-l`, plus the two the web only uses inline. */
export const radius = {
  s: 8,
  m: 12,
  l: 18,
  xl: 24,
  pill: 999,
} as const;

/**
 * Type scale. The web sets sizes in rem against a 16px root; these are the
 * same steps in pt, with line heights that hold the 1.45–1.65 body rhythm.
 */
export const type = {
  display: { fontSize: 30, lineHeight: 34, fontWeight: '800', letterSpacing: -0.8 },
  title: { fontSize: 22, lineHeight: 27, fontWeight: '800', letterSpacing: -0.5 },
  heading: { fontSize: 17, lineHeight: 22, fontWeight: '700', letterSpacing: -0.2 },
  cardTitle: { fontSize: 13, lineHeight: 17, fontWeight: '700' },
  body: { fontSize: 15, lineHeight: 22, fontWeight: '400' },
  bodySm: { fontSize: 13, lineHeight: 19, fontWeight: '400' },
  caption: { fontSize: 12, lineHeight: 17, fontWeight: '400' },
  label: { fontSize: 10, lineHeight: 13, fontWeight: '700', letterSpacing: 0.7 },
  metric: { fontSize: 20, lineHeight: 24, fontWeight: '700', letterSpacing: -0.4 },
} as const;

/**
 * The web's `--shadow` at the two elevations that survive the port: cards sit
 * flat (a border does the work) and only sheets and the tab bar lift.
 */
export const elevation = {
  sheet: {
    shadowColor: color.shadow,
    shadowOpacity: 0.2,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: -8 },
    elevation: 12,
  },
  raised: {
    shadowColor: color.shadow,
    shadowOpacity: 0.12,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
} as const;

/** Minimum tappable box. Anything interactive gets at least this. */
export const HIT_SLOP = { top: 8, bottom: 8, left: 8, right: 8 } as const;
export const MIN_TAP = 44;
