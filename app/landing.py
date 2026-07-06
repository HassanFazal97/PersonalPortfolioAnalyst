"""Public marketing + legal site for Cirvia.

Server-rendered HTML (no framework) served from ``app.main`` at ``/``,
``/contact``, ``/privacy``, and ``/terms``. All pages share one layout and
stylesheet via ``_layout``. These pages are auth-exempt and are also what
SnapTrade / partner reviewers see.
"""

from __future__ import annotations

CONTACT_EMAIL = "fazalhassan@live.ca"
LAST_UPDATED = "July 5, 2026"

_CSS = """
:root {
  --bg: oklch(13% 0.014 300);
  --surface-1: oklch(17% 0.016 300);
  --surface-2: oklch(20% 0.018 300);
  --surface-3: oklch(24% 0.02 300);
  --line: oklch(27% 0.018 300);
  --line-strong: oklch(35% 0.022 300);
  --ink: oklch(94% 0.008 300);
  --ink-2: oklch(79% 0.02 300);
  --ink-3: oklch(66% 0.024 300);
  --accent: oklch(48% 0.18 295);
  --accent-hover: oklch(55% 0.18 295);
  --accent-text: oklch(76% 0.12 295);
  --accent-deep: oklch(30% 0.1 295);
  --gain: oklch(76% 0.13 155);
  --loss: oklch(72% 0.14 25);
  --warn: oklch(80% 0.11 85);
  --r-s: 8px; --r-m: 12px; --r-l: 18px;
  --maxw: 1060px;
  --ease: cubic-bezier(0.22, 1, 0.36, 1);
  --font: "Schibsted Grotesk", ui-sans-serif, system-ui, -apple-system, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  font-family: var(--font);
  /* atmospheric violet aurora at the top, fading into the near-black canvas */
  background:
    radial-gradient(1200px 600px at 50% -120px, oklch(44% 0.15 295 / 0.55), transparent 70%),
    radial-gradient(800px 480px at 16% -60px, oklch(38% 0.12 265 / 0.35), transparent 70%),
    radial-gradient(900px 500px at 84% -80px, oklch(36% 0.13 315 / 0.3), transparent 70%),
    radial-gradient(1800px 950px at 50% -220px, oklch(27% 0.08 300 / 0.75), transparent 80%),
    var(--bg);
  background-repeat: no-repeat;
  color: var(--ink-2);
  line-height: 1.65; min-height: 100vh; -webkit-font-smoothing: antialiased;
}
h1, h2, h3 { color: var(--ink); text-wrap: balance; }
a { color: var(--accent-text); text-decoration: none; }
a:hover { text-decoration: underline; }
a:focus-visible, button:focus-visible, summary:focus-visible {
  outline: 2px solid var(--accent-text); outline-offset: 2px; border-radius: 4px;
}
.wrap { max-width: var(--maxw); margin: 0 auto; padding: 0 1.5rem 5.5rem; }
/* nav */
nav {
  position: sticky; top: 0; z-index: 10;
  background: oklch(13% 0.014 300 / 0.82); backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--line);
}
.nav-inner {
  max-width: var(--maxw); margin: 0 auto; padding: 0.85rem 1.5rem;
  display: flex; align-items: center; justify-content: space-between; gap: 1rem;
}
.logo { font-size: 1.3rem; font-weight: 800; letter-spacing: -0.03em; color: var(--ink); }
.logo span { color: var(--accent-text); }
.nav-links { display: flex; align-items: center; gap: 1.4rem; font-size: 0.92rem; font-weight: 500; }
.nav-links a { color: var(--ink-3); }
.nav-links a:hover, .nav-links a.active { color: var(--ink); text-decoration: none; }
@media (max-width: 660px) { .nav-links a:not(.btn):not(.keep) { display: none; } }
/* buttons */
.btn {
  display: inline-block; font-family: var(--font); font-weight: 600; font-size: 0.92rem;
  padding: 0.62rem 1.3rem; border-radius: 999px; border: 1px solid transparent;
  background: var(--accent); color: #fff; cursor: pointer;
  transition: background 0.12s var(--ease), transform 0.12s var(--ease);
}
.btn:hover { background: var(--accent-hover); text-decoration: none; transform: translateY(-1px); }
.btn.ghost { background: transparent; border-color: var(--line-strong); color: var(--ink); }
.btn.ghost:hover { background: var(--surface-2); }
/* hero */
.hero { padding: clamp(4rem, 9vw, 6.5rem) 0 1rem; text-align: center; }
.badge {
  display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; font-weight: 600;
  padding: 0.32rem 0.9rem; border-radius: 999px; margin-bottom: 1.5rem;
  background: var(--surface-1); border: 1px solid var(--line); color: var(--ink-3);
}
.badge-dot { width: 7px; height: 7px; border-radius: 999px; background: var(--accent-text); }
h1 {
  font-size: clamp(2.4rem, 6vw, 4rem); font-weight: 800; letter-spacing: -0.03em;
  line-height: 1.06; max-width: 15em; margin: 0 auto;
}
.lead {
  font-size: clamp(1.05rem, 2vw, 1.2rem); color: var(--ink-2);
  max-width: 36em; margin: 1.4rem auto 0;
}
.cta-row { display: flex; flex-wrap: wrap; justify-content: center; gap: 0.8rem; margin-top: 2rem; }
/* hero product stage: central digest panel + floating satellite cards */
.stage {
  position: relative; max-width: 920px; margin: clamp(3rem, 6vw, 4.5rem) auto 0;
  padding: 1.5rem 0 2.5rem; text-align: left;
}
.mock-glow {
  position: absolute; inset: -10% -12%; pointer-events: none;
  background: radial-gradient(closest-side, oklch(48% 0.18 295 / 0.16), transparent 72%);
}
.mock-panel {
  position: relative; max-width: 560px; margin: 0 auto;
  background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-l); padding: 1.25rem 1.4rem 1.4rem;
}
.float-card {
  position: absolute; z-index: 2; background: var(--surface-2);
  border: 1px solid var(--line-strong); border-radius: var(--r-m);
  padding: 0.85rem 1.05rem; font-size: 0.88rem;
  box-shadow: 0 18px 44px oklch(0% 0 0 / 0.38);
  animation: floaty 7s ease-in-out infinite alternate;
}
.fc-total { left: 1%; top: 10%; width: 190px; }
.fc-alert { right: 0.5%; top: 26%; width: 280px; animation-delay: -2.5s; }
.fc-chat { left: 4%; bottom: -3%; width: 290px; animation-delay: -4.5s; }
@keyframes floaty { from { transform: translateY(-5px); } to { transform: translateY(7px); } }
.fc-k { display: block; font-size: 0.74rem; font-weight: 600; color: var(--ink-3); }
.fc-v { display: block; font-size: 1.35rem; font-weight: 800; color: var(--ink);
  letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }
.fc-d { font-size: 0.82rem; font-weight: 600; }
.fc-q { font-weight: 600; color: var(--ink); margin-bottom: 0.3rem; }
.fc-a { color: var(--ink-2); }
@media (max-width: 920px) {
  .stage { padding: 0; }
  .float-card { position: static; width: min(100%, 430px); margin: 0.8rem auto 0;
    animation: none; box-shadow: none; }
  .fc-total { display: none; }
}
.mock-top {
  display: flex; align-items: center; gap: 0.55rem; font-size: 0.82rem; font-weight: 600;
  color: var(--ink-3); padding-bottom: 0.85rem; border-bottom: 1px solid var(--line);
}
.mock-dot { width: 8px; height: 8px; border-radius: 999px; background: var(--accent-text); }
.mock-date { margin-left: auto; font-weight: 500; font-variant-numeric: tabular-nums; }
.mock-row {
  display: grid; grid-template-columns: 4.2rem 1fr auto; gap: 0.8rem; align-items: baseline;
  padding: 0.62rem 0; border-bottom: 1px solid var(--line); font-size: 0.92rem;
}
.mock-row .t { font-weight: 700; color: var(--ink); }
.mock-row .n { color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mock-row .chg { font-weight: 600; font-variant-numeric: tabular-nums; }
.gain { color: var(--gain); } .loss { color: var(--loss); }
.mock-sum { font-size: 0.92rem; color: var(--ink-2); padding-top: 0.9rem; }
.mock-alert-k { display: block; font-size: 0.74rem; font-weight: 700; color: var(--warn); margin-bottom: 0.2rem; }
/* showcase (chat + alert demo) */
.show-grid { display: grid; grid-template-columns: 1.25fr 1fr; gap: 1.25rem;
  margin-top: 2.4rem; align-items: start; }
@media (max-width: 780px) { .show-grid { grid-template-columns: 1fr; } }
.show-panel { background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-l); padding: 1.3rem 1.4rem 1.5rem; }
.bubble { padding: 0.65rem 0.95rem; border-radius: var(--r-m); margin-top: 0.7rem;
  font-size: 0.92rem; line-height: 1.55; max-width: 92%; width: fit-content; }
.bubble.user { background: var(--surface-3); color: var(--ink); margin-left: auto; }
.bubble.bot { background: oklch(30% 0.1 295 / 0.4); color: var(--ink-2); }
.alert-demo .head-line { color: var(--ink); font-weight: 650; margin-top: 0.2rem; }
.alert-demo p { color: var(--ink-2); font-size: 0.92rem; margin-top: 0.4rem; }
.show-note { color: var(--ink-3); font-size: 0.92rem; margin-top: 1rem; max-width: 34em; }
/* sections */
section { padding-top: clamp(4rem, 9vw, 6.5rem); }
h2 { font-size: clamp(1.6rem, 3.4vw, 2.2rem); font-weight: 700; letter-spacing: -0.022em; }
h3 { font-size: 1.05rem; font-weight: 650; margin-bottom: 0.3rem; }
.sect-lead { color: var(--ink-3); margin-top: 0.7rem; max-width: 40em; }
/* ledger (feature rows) */
.ledger { margin-top: 2.4rem; border-top: 1px solid var(--line); }
.ledger-row {
  display: grid; grid-template-columns: minmax(11rem, 1fr) 2.2fr auto; gap: 1.5rem;
  align-items: baseline; padding: 1.5rem 0; border-bottom: 1px solid var(--line);
}
.ledger-row p { color: var(--ink-2); font-size: 0.97rem; max-width: 48em; }
.ledger-row .meta { color: var(--ink-3); font-size: 0.84rem; white-space: nowrap; font-variant-numeric: tabular-nums; }
@media (max-width: 680px) {
  .ledger-row { grid-template-columns: 1fr; gap: 0.3rem; }
  .ledger-row .meta { order: -1; }
}
/* steps */
.steps { counter-reset: step; margin-top: 2.2rem; max-width: 640px; }
.step { display: flex; gap: 1.2rem; padding: 1.3rem 0; border-bottom: 1px solid var(--line); }
.step:last-child { border-bottom: none; }
.step .num {
  counter-increment: step; flex: 0 0 auto; width: 2.1rem; height: 2.1rem; border-radius: 999px;
  background: var(--surface-2); border: 1px solid var(--line-strong); color: var(--ink);
  display: grid; place-items: center; font-weight: 700; font-size: 0.9rem;
  font-variant-numeric: tabular-nums;
}
.step .num::before { content: counter(step); }
.step p { color: var(--ink-2); font-size: 0.95rem; }
/* security */
.security-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 3rem; align-items: start; margin-top: 0; }
@media (max-width: 760px) { .security-grid { grid-template-columns: 1fr; gap: 1.5rem; } }
.checklist { list-style: none; background: var(--surface-1); border: 1px solid var(--line); border-radius: var(--r-l); padding: 1.4rem 1.6rem; }
.checklist li { position: relative; padding: 0.5rem 0 0.5rem 1.7rem; color: var(--ink-2); }
.checklist li::before { content: "✓"; position: absolute; left: 0; color: var(--accent-text); font-weight: 700; }
/* faq */
.faq { margin-top: 2rem; border-top: 1px solid var(--line); max-width: 760px; }
.faq details { border-bottom: 1px solid var(--line); }
.faq summary {
  cursor: pointer; list-style: none; display: flex; justify-content: space-between;
  align-items: center; gap: 1rem; padding: 1.15rem 0; font-weight: 600; color: var(--ink);
}
.faq summary::-webkit-details-marker { display: none; }
.faq summary::after { content: "+"; color: var(--ink-3); font-size: 1.25rem; flex: 0 0 auto; transition: transform 0.2s var(--ease); }
.faq details[open] summary::after { transform: rotate(45deg); }
.faq details p { color: var(--ink-2); padding: 0 0 1.25rem; max-width: 60ch; text-wrap: pretty; }
/* cta band */
.cta-band {
  margin-top: clamp(4rem, 9vw, 6.5rem);
  background:
    radial-gradient(640px 320px at 50% -80px, oklch(38% 0.13 295 / 0.45), transparent 75%),
    var(--surface-1);
  border: 1px solid var(--line-strong); border-radius: var(--r-l);
  padding: clamp(2.25rem, 5vw, 3.5rem); text-align: center;
}
.cta-band h2 { margin-bottom: 0.5rem; }
.cta-band p { color: var(--ink-3); margin-bottom: 1.5rem; }
/* plans (pricing) */
.plans { display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 1.25rem; margin-top: 2.4rem; max-width: 780px; }
.plan {
  background: var(--surface-1); border: 1px solid var(--line); border-radius: var(--r-l);
  padding: 1.9rem 1.8rem; display: flex; flex-direction: column;
}
.plan.featured { border-color: var(--accent-hover); }
.plan-tag { font-size: 0.8rem; font-weight: 700; color: var(--ink-3); }
.plan.featured .plan-tag { color: var(--accent-text); }
.price { font-size: 2.4rem; font-weight: 800; letter-spacing: -0.02em; color: var(--ink); margin: 0.3rem 0 0.1rem; font-variant-numeric: tabular-nums; }
.price .per { font-size: 1rem; font-weight: 500; color: var(--ink-3); letter-spacing: 0; }
.price-note { color: var(--ink-3); font-size: 0.9rem; margin-bottom: 1.1rem; }
.plan ul { list-style: none; margin-bottom: 1.4rem; }
.plan li { position: relative; padding: 0.35rem 0 0.35rem 1.6rem; color: var(--ink-2); font-size: 0.95rem; }
.plan li::before { content: "✓"; position: absolute; left: 0; color: var(--accent-text); font-weight: 700; }
.plan .btn { margin-top: auto; text-align: center; }
/* legal / prose */
.prose { max-width: 68ch; padding-top: 3rem; }
.prose h1 { font-size: clamp(1.9rem, 4.5vw, 2.4rem); font-weight: 800; letter-spacing: -0.025em; margin-bottom: 0.4rem; }
.prose .updated { color: var(--ink-3); font-size: 0.9rem; margin-bottom: 2.25rem; }
.prose h2 { font-size: 1.25rem; font-weight: 650; margin: 2.1rem 0 0.6rem; }
.prose p, .prose li { color: var(--ink-2); font-size: 0.97rem; text-wrap: pretty; }
.prose ul { margin: 0.5rem 0 0.5rem 1.25rem; }
.prose li { margin: 0.3rem 0; }
.callout {
  background: var(--surface-1); border: 1px solid var(--line); border-radius: var(--r-m);
  padding: 1rem 1.25rem; margin: 1.75rem 0; color: var(--ink-2); font-size: 0.95rem;
}
/* contact */
.contact-card {
  background: var(--surface-1); border: 1px solid var(--line); border-radius: var(--r-l);
  padding: 2.25rem; text-align: center; margin: 2.5rem auto 0; max-width: 560px;
}
.contact-card .email { font-size: 1.3rem; font-weight: 650; margin: 0.4rem 0 1.4rem; }
/* footer */
footer { border-top: 1px solid var(--line); margin-top: 2rem; }
.foot-inner {
  max-width: var(--maxw); margin: 0 auto; padding: 3rem 1.5rem 2.5rem;
  display: flex; flex-wrap: wrap; gap: 2.5rem; justify-content: space-between;
}
.foot-col h4 { font-size: 0.8rem; font-weight: 700; color: var(--ink-3); margin-bottom: 0.75rem; }
.foot-col a { display: block; color: var(--ink-2); font-size: 0.92rem; padding: 0.2rem 0; }
.foot-col a:hover { color: var(--ink); text-decoration: none; }
.foot-bottom { max-width: var(--maxw); margin: 0 auto; padding: 0 1.5rem 2.5rem; color: var(--ink-3); font-size: 0.85rem; }
.foot-bottom .disc { border-top: 1px solid var(--line); padding-top: 1.25rem; max-width: 75ch; }
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""

_FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:'
    'ital,wght@0,400..900;1,400..900&display=swap" rel="stylesheet">\n'
)

MOTION_CDN = "https://cdn.jsdelivr.net/npm/motion@12/dist/motion.js"

# Reveal choreography: content is fully visible without JS; the script hides
# elements immediately before animating them in, so no-JS/headless renders and
# reduced-motion users always get the complete page.
_REVEAL_JS = """
document.addEventListener('DOMContentLoaded', function () {
  if (!window.Motion || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var animate = Motion.animate, inView = Motion.inView, stagger = Motion.stagger;
  var EASE = [0.22, 1, 0.36, 1];
  var hero = document.querySelectorAll('[data-hero]');
  if (hero.length) {
    hero.forEach(function (el) { el.style.opacity = '0'; el.style.transform = 'translateY(16px)'; });
    animate(hero, { opacity: 1, transform: 'translateY(0px)' }, { duration: 0.7, delay: stagger(0.09), ease: EASE });
  }
  document.querySelectorAll('[data-reveal]').forEach(function (el) {
    el.style.opacity = '0'; el.style.transform = 'translateY(18px)';
    inView(el, function () {
      animate(el, { opacity: 1, transform: 'translateY(0px)' }, { duration: 0.6, ease: EASE });
    }, { amount: 0.3 });
  });
  document.querySelectorAll('[data-reveal-group]').forEach(function (group) {
    var items = group.querySelectorAll('[data-reveal-item]');
    if (!items.length) return;
    items.forEach(function (el) { el.style.opacity = '0'; el.style.transform = 'translateY(14px)'; });
    inView(group, function () {
      animate(items, { opacity: 1, transform: 'translateY(0px)' }, { duration: 0.55, delay: stagger(0.08), ease: EASE });
    }, { amount: 0.15 });
  });
});
"""

_NAV_LINKS = (
    ("how", "/#how", "How it works"),
    ("pricing", "/pricing", "Pricing"),
    ("contact", "/contact", "Contact"),
)


def _nav(active: str) -> str:
    links = ""
    for key, href, label in _NAV_LINKS:
        cls = ' class="active"' if key == active else ""
        links += f'<a href="{href}"{cls}>{label}</a>'
    return (
        '<nav><div class="nav-inner">'
        '<a class="logo" href="/">Cir<span>via</span></a>'
        f'<div class="nav-links">{links}'
        '<a class="keep" href="/app">Sign in</a>'
        '<a class="btn" href="/app">Get started</a>'
        "</div></div></nav>"
    )


_FOOTER = (
    '<footer><div class="foot-inner">'
    '<div class="foot-col"><div class="logo">Cir<span>via</span></div>'
    '<p style="color:var(--ink-3);font-size:0.9rem;margin-top:0.5rem;max-width:16em;">'
    "AI portfolio analyst for Canadian investors. Read-only. No trade execution.</p></div>"
    '<div class="foot-col"><h4>Product</h4>'
    '<a href="/">Home</a><a href="/#how">How it works</a>'
    '<a href="/pricing">Pricing</a><a href="/#faq">FAQ</a></div>'
    '<div class="foot-col"><h4>Legal</h4>'
    '<a href="/privacy">Privacy</a><a href="/terms">Terms</a></div>'
    '<div class="foot-col"><h4>Contact</h4>'
    f'<a href="/contact">Contact us</a><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></div>'
    "</div>"
    '<div class="foot-bottom"><p class="disc"><strong>Not financial advice.</strong> '
    "Cirvia is for informational purposes only and does not provide personalized "
    "investment advice or recommendations to buy or sell. Investing involves risk, "
    "including loss of principal; past performance does not guarantee future results. "
    f"<br><br>© 2026 Cirvia · Built in Canada</p></div></footer>"
)


def _layout(title: str, description: str, body: str, active: str = "") -> str:
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f'<meta name="description" content="{description}">\n'
        + _FONT_LINKS
        + "<style>"
        + _CSS
        + "</style>\n</head>\n<body>\n"
        + _nav(active)
        + '<main class="wrap">\n'
        + body
        + "\n</main>\n"
        + _FOOTER
        + f'\n<script defer src="{MOTION_CDN}"></script>\n'
        + "<script>"
        + _REVEAL_JS
        + "</script>\n"
        + "</body>\n</html>"
    )


# --------------------------------------------------------------------------
# Home
# --------------------------------------------------------------------------

_HOME_BODY = """
<section class="hero">
  <span class="badge" data-hero><span class="badge-dot"></span>Early access · Built in Canada</span>
  <h1 data-hero>Know what matters to your portfolio before the market opens.</h1>
  <p class="lead" data-hero>Cirvia is an AI analyst that knows your actual holdings.
  Connect your brokerage and get a weekday morning digest, macro alerts when
  the world moves, and clear answers about your positions whenever you ask.</p>
  <div class="cta-row" data-hero>
    <a class="btn" href="/app">Get started free</a>
    <a class="btn ghost" href="#how">See how it works</a>
  </div>
  <div class="stage" data-hero aria-hidden="true">
    <div class="mock-glow"></div>
    <div class="mock-panel">
      <div class="mock-top"><span class="mock-dot"></span>Morning digest
        <span class="mock-date">Tue, Jul 7 · 7:45</span></div>
      <div class="mock-row"><span class="t">VFV</span>
        <span class="n">Vanguard S&amp;P 500 Index ETF</span>
        <span class="chg gain">+0.8%</span></div>
      <div class="mock-row"><span class="t">NVDA</span>
        <span class="n">NVIDIA Corporation</span>
        <span class="chg gain">+2.1%</span></div>
      <div class="mock-row"><span class="t">ENB</span>
        <span class="n">Enbridge Inc.</span>
        <span class="chg loss">&minus;1.2%</span></div>
      <p class="mock-sum">Futures point higher after the Fed held rates steady.
      Energy trades soft ahead of OPEC output talks, which touches your ENB
      position. Nothing in your book reports earnings today.</p>
    </div>
    <div class="float-card fc-total">
      <span class="fc-k">Portfolio value</span>
      <span class="fc-v">$48,214</span>
      <span class="fc-d gain">+1.2% today</span>
    </div>
    <div class="float-card fc-alert">
      <span class="mock-alert-k">Macro alert</span>
      <p class="fc-a">OPEC+ signals a supply increase for August. Crude is down 3%
      pre-market; relevant to ENB and SU in your portfolio.</p>
    </div>
    <div class="float-card fc-chat">
      <p class="fc-q">&ldquo;Why is ENB down today?&rdquo;</p>
      <p class="fc-a">Crude fell 3% after OPEC+ signalled higher output. ENB is your
      third-largest holding&hellip;</p>
    </div>
  </div>
</section>

<section id="features">
  <h2 data-reveal>Signal, not noise, mapped to what you own.</h2>
  <div class="ledger" data-reveal-group>
    <div class="ledger-row" data-reveal-item>
      <h3>Morning digest</h3>
      <p>A weekday brief tailored to your tickers: overnight moves, what changed,
      and what to watch, written in plain language.</p>
      <span class="meta">Weekdays, your time</span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Macro alerts</h3>
      <p>Fed decisions, energy shocks, geopolitics, and regulation, surfaced only
      when they plausibly touch your holdings.</p>
      <span class="meta">As it happens</span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>On-demand answers</h3>
      <p>Ask anything about your book: news, performance, drawdowns, context.
      Every answer is grounded in your actual positions.</p>
      <span class="meta">Any time</span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Automatic sync</h3>
      <p>Your TFSA, RRSP, and taxable accounts stay current through a secure,
      read-only brokerage connection.</p>
      <span class="meta">Continuous</span>
    </div>
  </div>
</section>

<section id="showcase">
  <h2 data-reveal>Ask about your book. Get grounded answers.</h2>
  <p class="sect-lead" data-reveal>Not generic market takes. Every answer starts
  from the positions you actually hold.</p>
  <div class="show-grid" data-reveal-group>
    <div class="show-panel" data-reveal-item aria-hidden="true">
      <div class="mock-top"><span class="mock-dot"></span>Chat</div>
      <div class="bubble user">Why is ENB down today?</div>
      <div class="bubble bot">Crude fell 3% after OPEC+ signalled higher August
      output. ENB is your third-largest holding; pipelines are less exposed to
      crude prices than producers, but sentiment is dragging the whole sector.</div>
      <div class="bubble user">Anything to watch in my book this week?</div>
      <div class="bubble bot">Two things: NVDA reports earnings Wednesday after
      close, and the Bank of Canada rate decision lands Thursday morning, which
      touches your rate-sensitive holdings.</div>
    </div>
    <div data-reveal-item>
      <div class="show-panel alert-demo" aria-hidden="true">
        <span class="mock-alert-k">Macro alert · High</span>
        <p class="head-line">Fed holds rates, signals one cut this year.</p>
        <p>Rate-sensitive names in your book: T.TO, BCE.TO. Bond-proxy sectors
        typically firm on this news.</p>
      </div>
      <p class="show-note">Alerts arrive only when an event plausibly touches your
      holdings. No noise, no spam, no generic headlines.</p>
    </div>
  </div>
</section>

<section id="how">
  <h2 data-reveal>Three steps. Your brokerage password never leaves your bank.</h2>
  <div class="steps" data-reveal-group>
    <div class="step" data-reveal-item><div class="num"></div><div><h3>Connect Wealthsimple</h3>
    <p>Link your account through SnapTrade's secure Connection Portal. Cirvia never sees
    or stores your brokerage login.</p></div></div>
    <div class="step" data-reveal-item><div class="num"></div><div><h3>We read your holdings</h3>
    <p>Read-only access syncs your positions and balances. Cirvia can never place a trade
    or move money.</p></div></div>
    <div class="step" data-reveal-item><div class="num"></div><div><h3>Get informed, daily</h3>
    <p>Receive your morning digest and macro alerts, and ask questions whenever you like.</p></div></div>
  </div>
</section>

<section id="security">
  <div class="security-grid">
    <div data-reveal>
      <h2>Built read-only. Private by design.</h2>
      <p class="sect-lead">Cirvia informs. It never trades, never advises buy or sell,
      and never handles your money.</p>
    </div>
    <ul class="checklist" data-reveal>
      <li>Read-only brokerage access, always</li>
      <li>Your credentials stay with your bank, never with us</li>
      <li>Connection secrets encrypted at rest</li>
      <li>Every account isolated at the database level</li>
    </ul>
  </div>
</section>

<section id="faq">
  <h2 data-reveal>Questions</h2>
  <div class="faq" data-reveal-group>
    <details data-reveal-item><summary>Can Cirvia trade for me?</summary>
    <p>No. Access is strictly read-only. Cirvia cannot place orders or move funds
    under any circumstances.</p></details>
    <details data-reveal-item><summary>Is this financial advice?</summary>
    <p>No. Cirvia is informational only. It explains and contextualizes; it does not
    tell you to buy or sell.</p></details>
    <details data-reveal-item><summary>Which brokerages work?</summary>
    <p>Wealthsimple today, via SnapTrade. More brokerages that SnapTrade supports
    may be added over time.</p></details>
    <details data-reveal-item><summary>How is my data protected?</summary>
    <p>Brokerage credentials stay with your bank, connection secrets are encrypted,
    and every account is isolated by row-level security. See our
    <a href="/privacy">Privacy Policy</a>.</p></details>
  </div>
</section>

<section>
  <div class="cta-band" data-reveal>
    <h2>Know your portfolio by 7:45.</h2>
    <p>Start free. Connect Wealthsimple in under three minutes.</p>
    <a class="btn" href="/app">Get started free</a>
  </div>
</section>
"""

# --------------------------------------------------------------------------
# Contact
# --------------------------------------------------------------------------

_CONTACT_BODY = f"""
<section class="hero" style="padding-bottom:0;">
  <h1 data-hero>Get in touch</h1>
  <p class="lead" data-hero>Questions, support, privacy inquiries, or partnerships.
  We read everything.</p>
</section>

<div class="contact-card" data-hero>
  <div class="email"><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></div>
  <a class="btn" href="mailto:{CONTACT_EMAIL}">Send an email</a>
</div>

<section>
  <h2 data-reveal>What we can help with</h2>
  <div class="ledger" data-reveal-group>
    <div class="ledger-row" data-reveal-item>
      <h3>Getting started</h3>
      <p>Questions before you sign up, or help creating your account.</p>
      <span class="meta"></span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Support</h3>
      <p>Trouble connecting your brokerage or a question about your digest.</p>
      <span class="meta"></span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Privacy &amp; data</h3>
      <p>Request access to, correction of, or deletion of your data. See our
      <a href="/privacy">Privacy Policy</a>.</p>
      <span class="meta"></span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Partnerships &amp; press</h3>
      <p>Working on something related? Reach out.</p>
      <span class="meta"></span>
    </div>
  </div>
  <p style="color:var(--ink-3);margin-top:1.5rem;font-size:0.95rem;">We aim to respond
  within two business days.</p>
</section>
"""

# --------------------------------------------------------------------------
# Privacy Policy
# --------------------------------------------------------------------------

_PRIVACY_BODY = f"""
<div class="prose">
  <h1>Privacy Policy</h1>
  <p class="updated">Last updated: {LAST_UPDATED}</p>

  <p>Cirvia ("Cirvia", "we", "us", or "our") provides an AI portfolio analysis service for
  individual investors. This Privacy Policy explains what personal information we collect, why we
  collect it, how we use, share, and protect it, and the choices and rights you have. It is
  written to align with Canada's <em>Personal Information Protection and Electronic Documents Act</em>
  (PIPEDA). By creating an account or using Cirvia, you consent to the collection, use, and
  disclosure of your information as described here.</p>

  <h2>1. Accountability</h2>
  <p>Cirvia is responsible for personal information under its control. Questions, requests, and
  privacy complaints can be directed to our privacy contact at
  <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p>

  <h2>2. Information we collect</h2>
  <ul>
    <li><strong>Account information.</strong> When you sign in, our authentication provider stores
    your email address and a unique account identifier.</li>
    <li><strong>Brokerage holdings data.</strong> With your authorization, we retrieve
    <em>read-only</em> account, position, transaction, and balance information from your connected
    brokerage through SnapTrade.</li>
    <li><strong>Usage and technical data.</strong> We log your interactions with the service (such
    as questions you ask and digests generated), along with limited technical data (such as
    timestamps and request metadata) needed to operate and secure it.</li>
    <li><strong>Communications.</strong> If you contact us, we keep your messages and contact
    details to respond.</li>
  </ul>

  <h2>3. Information we do NOT collect</h2>
  <ul>
    <li>Your brokerage username, password, or other login credentials — you authenticate directly
    with your brokerage inside SnapTrade's secure portal; those credentials never pass through or
    reach Cirvia.</li>
    <li>Payment card details, if and when paid plans are offered — these would be handled directly
    by a third-party payment processor, not stored by Cirvia.</li>
  </ul>

  <h2>4. Purposes and how we use your information</h2>
  <ul>
    <li>To provide the service — syncing your holdings, generating your daily digest and macro
    alerts, and answering your questions.</li>
    <li>To secure, maintain, debug, and improve the service.</li>
    <li>To communicate with you about your account, support requests, and service updates.</li>
    <li>To comply with legal obligations.</li>
  </ul>
  <p>We use your information only for the purposes identified here or for which you provide
  consent. We do <strong>not</strong> sell your personal information, and we do not use your
  holdings data for advertising.</p>

  <h2>5. Consent</h2>
  <p>We collect, use, and disclose your personal information with your consent. You provide consent
  by creating an account and by connecting your brokerage. You may withdraw consent at any time by
  disconnecting your brokerage and/or closing your account (see Section 9); withdrawing consent may
  limit or end your ability to use the service.</p>

  <h2>6. Automated processing and AI</h2>
  <p>Cirvia uses artificial intelligence to generate analysis, summaries, and alerts from your
  holdings and public market data. This output is informational only and does not constitute
  automated decision-making that produces legal or similarly significant effects about you. AI
  output may be inaccurate or incomplete and should not be solely relied upon.</p>

  <h2>7. Service providers and disclosure</h2>
  <p>We share the minimum information necessary with service providers that process data on our
  behalf to operate Cirvia, each bound by their own terms and privacy and security commitments:</p>
  <ul>
    <li><strong>SnapTrade</strong> — secure brokerage connectivity (read-only holdings).</li>
    <li><strong>Supabase</strong> — authentication and database hosting.</li>
    <li><strong>Anthropic</strong> — the AI model that generates analysis (we send relevant
    portfolio context and public news; we do not send your brokerage credentials).</li>
    <li><strong>Finnhub and other market-data providers</strong> — public market and news data.</li>
    <li><strong>Railway</strong> — application hosting.</li>
  </ul>
  <p>We may also disclose information if required by law, to enforce our Terms, or to protect the
  rights, property, or safety of Cirvia, our users, or others. If Cirvia is involved in a merger,
  acquisition, or asset sale, information may be transferred subject to this policy.</p>

  <h2>8. International storage and transfer</h2>
  <p>Cirvia and its service providers may store and process your information on servers located in
  the United States and other countries. As a result, your information may be subject to the laws
  of those jurisdictions, including lawful access requests by courts or authorities. By using
  Cirvia, you consent to this transfer, storage, and processing outside your province or country of
  residence.</p>

  <h2>9. Retention and deletion</h2>
  <p>We retain your information for as long as your account is active or as needed to provide the
  service and meet legal, accounting, or reporting requirements. You may request deletion of your
  account and associated data at any time by emailing
  <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>; we will delete or de-identify it within a
  reasonable period, except where retention is required by law. Disconnecting your brokerage stops
  further data retrieval immediately.</p>

  <h2>10. Safeguards</h2>
  <ul>
    <li>Brokerage credentials are never seen or stored by Cirvia.</li>
    <li>Brokerage connection secrets are encrypted at rest.</li>
    <li>Each account's data is isolated at the database level using row-level security, so one user
    cannot access another user's information.</li>
    <li>Data is transmitted over encrypted (TLS) connections.</li>
  </ul>
  <p>No method of transmission or storage is completely secure. In the event of a data breach that
  poses a real risk of significant harm, we will notify affected individuals and the appropriate
  authorities as required by applicable law.</p>

  <h2>11. Cookies and tracking</h2>
  <p>Our marketing pages do not use advertising or cross-site tracking cookies. The application
  uses only the cookies and tokens strictly necessary to keep you signed in and to operate the
  service securely.</p>

  <h2>12. Your rights</h2>
  <p>Subject to applicable law (including PIPEDA), you may request to access, correct, or delete
  your personal information, and to withdraw consent. To exercise these rights, contact
  <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>. If you are not satisfied with our response,
  you may contact the <a href="https://www.priv.gc.ca/" rel="noopener">Office of the Privacy
  Commissioner of Canada</a>.</p>

  <h2>13. Children</h2>
  <p>Cirvia is intended for adults (18+) and is not directed to children. We do not knowingly
  collect personal information from anyone under 18.</p>

  <h2>14. Third-party links</h2>
  <p>Our site and service may link to third-party websites or services (such as SnapTrade). Their
  privacy practices are governed by their own policies, not this one.</p>

  <h2>15. Changes to this policy</h2>
  <p>We may update this policy from time to time. Material changes will be reflected by the "Last
  updated" date above and, where appropriate, communicated to you. Your continued use after changes
  take effect constitutes acceptance.</p>

  <h2>16. Contact</h2>
  <p>Questions about this policy or your data? Email
  <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p>

  <div class="callout"><strong>Not financial advice.</strong> Cirvia is informational only and does
  not provide personalized investment advice.</div>
</div>
"""

# --------------------------------------------------------------------------
# Terms of Service
# --------------------------------------------------------------------------

_TERMS_BODY = f"""
<div class="prose">
  <h1>Terms of Service</h1>
  <p class="updated">Last updated: {LAST_UPDATED}</p>

  <p>These Terms of Service ("Terms") form a binding agreement between you and Cirvia ("Cirvia",
  "we", "us") governing your access to and use of the Cirvia website, application, and services
  (collectively, the "Service"). By accessing or using the Service, you agree to these Terms and to
  our <a href="/privacy">Privacy Policy</a>. If you do not agree, do not use the Service.</p>

  <h2>1. The Service</h2>
  <p>Cirvia is an informational tool that connects to your brokerage account on a
  <strong>read-only</strong> basis to sync your holdings, and uses artificial intelligence to
  generate a daily digest, macro alerts, and on-demand answers about your portfolio. Cirvia cannot
  place trades, transfer funds, or take any action on your brokerage account. We may modify,
  suspend, or discontinue any part of the Service at any time.</p>

  <h2>2. Not financial, investment, tax, or legal advice</h2>
  <p>Cirvia provides information and context for educational and informational purposes only. It is
  not a registered investment adviser, portfolio manager, dealer, or financial planner, and nothing
  it produces is personalized investment advice, a solicitation, or a recommendation to buy, sell, or
  hold any security. No fiduciary or advisory relationship is created by your use of the Service. You
  are solely responsible for your own investment decisions. Past performance does not guarantee future
  results, and investing involves risk, including the possible loss of principal. Consider consulting a
  qualified professional before making financial decisions.</p>

  <h2>3. Eligibility and accounts</h2>
  <p>You must be at least 18 years old and able to form a binding contract. You agree to provide
  accurate information, to keep your login credentials confidential, and to be responsible for all
  activity under your account. Notify us promptly at
  <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> of any unauthorized use.</p>

  <h2>4. Brokerage connection and third-party services</h2>
  <p>Connecting a brokerage account is performed through SnapTrade and your brokerage, subject to
  their respective terms and privacy policies. You authorize Cirvia to retrieve your read-only
  account data through that connection, and you represent that you are entitled to do so. We rely on
  third-party services (including SnapTrade, market-data providers, hosting, and AI providers) and are
  not responsible for their acts, omissions, availability, or accuracy.</p>

  <h2>5. Fees and subscriptions</h2>
  <p>The Service is currently offered in early access, and some features may be provided free of
  charge. We may introduce paid plans or subscriptions in the future. If you purchase a paid plan, the
  applicable prices, billing period, and features will be presented to you at the time of purchase and
  are incorporated into these Terms. Payments would be processed by a third-party payment processor;
  you authorize us and the processor to charge your selected payment method. Unless required by law or
  stated otherwise, fees are non-refundable, and you are responsible for applicable taxes. You may
  cancel a subscription at any time, effective at the end of the current billing period. We may change
  fees on prospective notice.</p>

  <h2>6. Data accuracy</h2>
  <p>Information provided by the Service — including holdings, prices, news, and AI-generated analysis
  — may be delayed, incomplete, or inaccurate, and may contain errors. Do not rely on it as the sole
  basis for any financial decision. Verify important information with your brokerage and other primary
  sources.</p>

  <h2>7. Acceptable use</h2>
  <p>You agree not to: (a) attempt to access accounts or data that are not yours; (b) disrupt,
  overload, or interfere with the Service; (c) reverse-engineer, scrape, or copy the Service except as
  permitted by law; (d) use the Service to violate any law or third-party right; or (e) use the Service
  to provide investment advice or services to third parties.</p>

  <h2>8. Intellectual property and license</h2>
  <p>The Service, including its software, content, and branding, is owned by Cirvia and protected by
  applicable laws. We grant you a limited, non-exclusive, non-transferable, revocable license to use
  the Service for your personal, non-commercial use, subject to these Terms.</p>

  <h2>9. Privacy</h2>
  <p>Your use of the Service is subject to our <a href="/privacy">Privacy Policy</a>, which describes
  how we collect, use, and protect your information.</p>

  <h2>10. Disclaimers</h2>
  <p>THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT. We do not
  warrant that the Service will be uninterrupted, timely, secure, error-free, or that any information
  will be accurate or complete.</p>

  <h2>11. Limitation of liability</h2>
  <p>TO THE MAXIMUM EXTENT PERMITTED BY LAW, CIRVIA AND ITS OPERATORS WILL NOT BE LIABLE FOR ANY
  INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, PUNITIVE, OR EXEMPLARY DAMAGES, OR FOR ANY INVESTMENT
  OR TRADING LOSSES, ARISING FROM OR RELATED TO YOUR USE OF THE SERVICE. OUR TOTAL AGGREGATE LIABILITY
  FOR ANY CLAIM RELATING TO THE SERVICE WILL NOT EXCEED THE GREATER OF THE AMOUNT YOU PAID US IN THE
  12 MONTHS BEFORE THE CLAIM OR CAD $100. Some jurisdictions do not allow certain limitations, so some
  of the above may not apply to you.</p>

  <h2>12. Indemnification</h2>
  <p>You agree to indemnify and hold Cirvia and its operators harmless from any claims, losses, and
  expenses (including reasonable legal fees) arising out of your use of the Service or your violation
  of these Terms or applicable law.</p>

  <h2>13. Termination</h2>
  <p>You may stop using the Service and disconnect your brokerage at any time. We may suspend or
  terminate your access at any time if you violate these Terms or to protect the Service or other
  users. Sections that by their nature should survive termination (including Sections 2, 6, 10–12, 14,
  and 16) will survive.</p>

  <h2>14. Governing law and dispute resolution</h2>
  <p>These Terms are governed by the laws of the Province of Ontario and the federal laws of Canada
  applicable therein, without regard to conflict-of-laws principles. Before filing a claim, you agree
  to first contact us at <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> to seek an informal
  resolution. The courts located in Ontario will have exclusive jurisdiction over any dispute not
  resolved informally, and you consent to that jurisdiction and venue.</p>

  <h2>15. Electronic communications</h2>
  <p>You consent to receive communications from us electronically (by email or through the Service),
  and you agree that electronic communications satisfy any legal requirement that such communications
  be in writing.</p>

  <h2>16. Changes to these Terms</h2>
  <p>We may update these Terms from time to time. Material changes will be reflected by the "Last
  updated" date above and, where appropriate, communicated to you. Your continued use after changes
  take effect constitutes acceptance of the updated Terms.</p>

  <h2>17. General</h2>
  <p>These Terms and the Privacy Policy are the entire agreement between you and Cirvia regarding the
  Service. If any provision is found unenforceable, the remaining provisions remain in effect. Our
  failure to enforce a provision is not a waiver. You may not assign these Terms without our consent;
  we may assign them in connection with a merger, acquisition, or sale of assets. We are not liable
  for delays or failures caused by events beyond our reasonable control. Section headings are for
  convenience only.</p>

  <h2>18. Contact</h2>
  <p>Questions about these Terms? Email <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p>
</div>
"""


# --------------------------------------------------------------------------
# Pricing
# --------------------------------------------------------------------------

_PRICING_BODY = f"""
<section class="hero" style="padding-bottom:0;">
  <h1 data-hero>Start free. Go Pro when you're ready.</h1>
  <p class="lead" data-hero>Read-only, informational, and built for individual investors.
  Your brokerage password never leaves your bank, on any plan.</p>
</section>

<section style="padding-top:0;">
  <div class="plans" style="margin-left:auto;margin-right:auto;" data-reveal-group>
    <div class="plan" data-reveal-item>
      <div class="plan-tag">Free</div>
      <div class="price">$0<span class="per"> /mo</span></div>
      <p class="price-note">For getting started and kicking the tires.</p>
      <ul>
        <li>1 connected account</li>
        <li>Weekly digest on up to 3 holdings</li>
        <li>5 chat questions per day</li>
      </ul>
      <a class="btn ghost" href="/app">Start free</a>
    </div>
    <div class="plan featured" data-reveal-item>
      <div class="plan-tag">Pro</div>
      <div class="price">$12<span class="per"> /mo</span></div>
      <p class="price-note">or $120/yr, two months free.</p>
      <ul>
        <li>Unlimited connected accounts</li>
        <li>Daily weekday digest across all holdings</li>
        <li>Macro alerts when the world moves</li>
        <li>Unlimited chat</li>
      </ul>
      <a class="btn" href="/app">Go Pro</a>
    </div>
  </div>
</section>

<section id="pricing-faq">
  <h2 data-reveal>Questions about plans</h2>
  <div class="faq" data-reveal-group>
    <details data-reveal-item><summary>Can I cancel anytime?</summary>
    <p>Yes. Cancel whenever you like; your Pro features stay active until the end of
    the current billing period.</p></details>
    <details data-reveal-item><summary>Is there a yearly option?</summary>
    <p>Yes. Pro is $12/mo or $120/yr, which works out to two months free versus
    paying monthly.</p></details>
    <details data-reveal-item><summary>What happens on the Free plan?</summary>
    <p>You keep one connected account, a weekly digest on up to three holdings, and
    five chat questions a day. Free, indefinitely.</p></details>
    <details data-reveal-item><summary>Do you offer refunds?</summary>
    <p>Reach out and we'll make it right. Email us at
    <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p></details>
  </div>
</section>

<section>
  <div class="cta-band" data-reveal>
    <h2>Ready when you are.</h2>
    <p>Connect Wealthsimple in under three minutes. Start free, upgrade any time.</p>
    <a class="btn" href="/app">Get started free</a>
  </div>
</section>
"""


LANDING_HTML = _layout(
    "Cirvia — AI portfolio analyst for Canadian investors",
    "Connect Wealthsimple, get a daily digest, macro alerts, and on-demand answers about your "
    "real holdings. Read-only. No trade execution.",
    _HOME_BODY,
    active="home",
)

PRICING_HTML = _layout(
    "Pricing — Cirvia",
    "Cirvia pricing: start free with a weekly digest and daily chat, or go Pro at $12/mo "
    "($120/yr) for unlimited accounts, daily digests, macro alerts, and unlimited chat.",
    _PRICING_BODY,
    active="pricing",
)

CONTACT_HTML = _layout(
    "Contact — Cirvia",
    "Get in touch with Cirvia for early access, support, privacy requests, or partnerships.",
    _CONTACT_BODY,
    active="contact",
)

PRIVACY_HTML = _layout(
    "Privacy Policy — Cirvia",
    "How Cirvia collects, uses, and protects your personal and brokerage information.",
    _PRIVACY_BODY,
)

TERMS_HTML = _layout(
    "Terms of Service — Cirvia",
    "The terms governing your use of Cirvia's read-only, informational portfolio analysis service.",
    _TERMS_BODY,
)
