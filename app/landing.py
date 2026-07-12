"""Public marketing + legal site for Cirvia.

Server-rendered HTML (no framework) served from ``app.main`` at ``/``,
``/contact``, ``/privacy``, and ``/terms``. All pages share one layout and
stylesheet via ``_layout``. These pages are auth-exempt and are also what
SnapTrade / partner reviewers see.
"""

from __future__ import annotations

from urllib.parse import quote, urlparse

from app.config import get_settings

CONTACT_EMAIL = "fazalhassan@live.ca"
LAST_UPDATED = "July 5, 2026"

# Brand mark: rounded violet tile with a bold geometric "C" (flat terminals,
# echoing Schibsted Grotesk). Inlined as a data URI so the tab icon needs no
# static file; the PNG fallbacks in app/static/ cover Apple touch + OG cards.
_FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<rect width='64' height='64' rx='14' fill='#683eb6'/>"
    "<path d='M44.3 42.3A16 16 0 1 1 44.3 21.7' fill='none' stroke='#fff' stroke-width='10'/>"
    "</svg>"
)

# Shared by the marketing layout and the app pages (app/webapp.py).
ICON_LINKS = (
    f'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,{quote(_FAVICON_SVG)}">\n'
    '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">\n'
    '<meta name="theme-color" content="#08060c">\n'
)


def _public_base_url() -> str:
    """Absolute origin for og:url / og:image (no trailing slash)."""
    return (get_settings().public_base_url or "https://cirvia.ca").rstrip("/")

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
html, body { overflow-x: clip; }
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
/* nav: transparent over the hero, gains surface + hairline once scrolled */
nav {
  position: sticky; top: 0; z-index: 10;
  background: transparent; border-bottom: 1px solid transparent;
  transition: background 0.3s var(--ease), border-color 0.3s var(--ease);
}
nav.scrolled {
  background: oklch(13% 0.014 300 / 0.82); backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom-color: var(--line);
}
.nav-inner {
  max-width: var(--maxw); margin: 0 auto; padding: 0.8rem 1.5rem;
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
.btn.lg { font-size: 1rem; padding: 0.8rem 1.7rem; }
.quiet {
  color: var(--ink-2); font-weight: 600; font-size: 0.95rem;
  padding: 0.8rem 0.4rem; transition: color 0.12s var(--ease);
}
.quiet:hover { color: var(--ink); text-decoration: none; }
/* hero — minimal copy + aurora scene */
.hero { padding: clamp(3.5rem, 8vw, 6rem) 0 0; text-align: center; }
.hero-copy { max-width: 52rem; margin: 0 auto; }
h1 {
  font-size: clamp(2.5rem, 6vw, 4.4rem); font-weight: 800; letter-spacing: -0.035em;
  line-height: 1.06; max-width: 25ch; margin: 0 auto;
}
.hl { display: block; overflow: hidden; }
.hl-in { display: block; }
.lead {
  font-size: clamp(1.02rem, 1.8vw, 1.18rem); color: var(--ink-3);
  max-width: 30em; margin: 1.2rem auto 0;
}
.cta-row {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: center;
  gap: 1.1rem; margin-top: 1.9rem;
}
/* hero scene: WebGL aurora silk over a CSS-gradient base, satellite cards on top */
.hero-scene {
  position: relative; max-width: 1100px; margin: clamp(1rem, 2.6vw, 1.75rem) auto 0;
  min-height: clamp(420px, 46vw, 560px); overflow: visible;
}
.hero-stars {
  position: absolute; inset: 0; pointer-events: none; opacity: 0.45;
  background-image:
    radial-gradient(1px 1px at 12% 22%, oklch(88% 0.02 300 / 0.5), transparent),
    radial-gradient(1px 1px at 78% 14%, oklch(88% 0.02 300 / 0.35), transparent),
    radial-gradient(1.5px 1.5px at 44% 8%, oklch(90% 0.02 300 / 0.4), transparent),
    radial-gradient(1px 1px at 91% 38%, oklch(88% 0.02 300 / 0.3), transparent),
    radial-gradient(1px 1px at 6% 58%, oklch(88% 0.02 300 / 0.35), transparent),
    radial-gradient(1px 1px at 62% 72%, oklch(88% 0.02 300 / 0.25), transparent);
}
.hero-orb {
  position: absolute; left: 50%; bottom: -10%; width: min(880px, 96vw);
  height: min(480px, 52vh); transform: translateX(-50%); pointer-events: none;
  background:
    radial-gradient(ellipse 55% 48% at 50% 58%, oklch(52% 0.2 295 / 0.8), transparent 72%),
    radial-gradient(ellipse 70% 55% at 42% 62%, oklch(38% 0.14 275 / 0.5), transparent 68%),
    radial-gradient(ellipse 45% 40% at 58% 48%, oklch(45% 0.16 310 / 0.4), transparent 70%);
  filter: blur(30px);
  animation: orb-breathe 9s ease-in-out infinite alternate;
}
@keyframes orb-breathe {
  from { transform: translateX(-50%) scale(1) translateY(0); }
  to { transform: translateX(-50%) scale(1.05) translateY(-14px); }
}
#aurora {
  position: absolute; left: 50%; bottom: -14%; transform: translateX(-50%);
  width: min(1240px, 100vw); height: 118%; pointer-events: none; z-index: 1;
  opacity: 0; transition: opacity 1.4s var(--ease);
}
#aurora.on { opacity: 1; }
.float-card {
  position: absolute; z-index: 2;
  background: var(--surface-1);
  border: 1px solid oklch(42% 0.05 295 / 0.5); border-radius: var(--r-m);
  padding: 0.95rem 1.1rem; font-size: 0.88rem; text-align: left;
  box-shadow: 0 30px 70px oklch(0% 0 0 / 0.5), 0 4px 16px oklch(0% 0 0 / 0.3);
  animation: floaty 7s ease-in-out infinite alternate;
}
.fc-digest { left: 50%; top: 17%; width: min(330px, 80vw); z-index: 3;
  transform: translate(-50%, 0); animation: floaty-center 8s ease-in-out infinite alternate; }
.fc-alert { right: 3%; top: 2%; width: 244px; animation-delay: -2.5s; }
.fc-chat { left: 3%; bottom: 26%; width: 254px; animation-delay: -4.5s; }
@keyframes floaty { from { transform: translateY(-6px); } to { transform: translateY(8px); } }
@keyframes floaty-center {
  from { transform: translate(-50%, -6px); } to { transform: translate(-50%, 8px); }
}
.fc-q { font-weight: 600; color: var(--ink); margin-bottom: 0.3rem; font-size: 0.86rem; }
.fc-a { color: var(--ink-2); font-size: 0.84rem; line-height: 1.5; }
.mock-top {
  display: flex; align-items: center; gap: 0.55rem; font-size: 0.78rem; font-weight: 600;
  color: var(--ink-3); padding-bottom: 0.7rem; border-bottom: 1px solid var(--line);
}
.mock-dot { width: 7px; height: 7px; border-radius: 999px; background: var(--accent-text); }
.mock-date { margin-left: auto; font-weight: 500; font-variant-numeric: tabular-nums; }
.mock-val { display: flex; align-items: baseline; gap: 0.6rem; padding: 0.7rem 0 0.35rem; }
.mock-val .v { font-size: 1.35rem; font-weight: 800; color: var(--ink);
  letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }
.mock-val .d { font-size: 0.82rem; font-weight: 600; }
.mock-row {
  display: grid; grid-template-columns: 3.5rem 1fr auto; gap: 0.6rem; align-items: baseline;
  padding: 0.5rem 0; border-bottom: 1px solid var(--line); font-size: 0.86rem;
}
.mock-row:last-of-type { border-bottom: none; }
.mock-row .t { font-weight: 700; color: var(--ink); }
.mock-row .n { color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mock-row .chg { font-weight: 600; font-variant-numeric: tabular-nums; font-size: 0.84rem; }
.gain { color: var(--gain); } .loss { color: var(--loss); }
.mock-alert-k { display: block; font-size: 0.72rem; font-weight: 700; color: var(--warn); margin-bottom: 0.25rem; }
@media (max-width: 900px) {
  .hero-scene { min-height: auto; padding: clamp(11rem, 52vw, 15rem) 0 1rem; }
  .hero-orb { bottom: auto; top: -2%; height: 340px; opacity: 0.85; }
  #aurora { bottom: auto; top: -6%; height: clamp(300px, 60vw, 420px); }
  .float-card { position: relative; width: min(100%, 420px); margin: 0.85rem auto 0;
    left: auto !important; right: auto !important; top: auto !important; bottom: auto !important;
    transform: none !important; animation: none; box-shadow: 0 12px 32px oklch(0% 0 0 / 0.3); }
  .fc-chat { display: none; }
  .hero-stars { display: none; }
}
/* showcase (chat demo) */
.show-panel { background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-l); padding: 1.3rem 1.4rem 1.5rem; }
.chat-demo { position: relative; max-width: 640px; margin-top: 2.2rem; }
.bubble { padding: 0.65rem 0.95rem; border-radius: var(--r-m); margin-top: 0.7rem;
  font-size: 0.92rem; line-height: 1.55; max-width: 92%; width: fit-content; }
.bubble.user { background: var(--surface-3); color: var(--ink); margin-left: auto; }
.bubble.bot { background: oklch(30% 0.1 295 / 0.4); color: var(--ink-2); }
.bubble.typing { position: absolute; display: inline-flex; gap: 5px; align-items: center;
  padding: 0.85rem 0.95rem; margin: 0; }
.bubble.typing i { width: 6px; height: 6px; border-radius: 50%; background: var(--ink-3);
  animation: tdot 0.9s ease-in-out infinite; }
.bubble.typing i:nth-child(2) { animation-delay: 0.15s; }
.bubble.typing i:nth-child(3) { animation-delay: 0.3s; }
@keyframes tdot { 0%, 100% { opacity: 0.35; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(-3px); } }
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
/* cta finale: full-bleed aurora band above the footer */
.cta-final {
  margin: clamp(4.5rem, 10vw, 7.5rem) calc(50% - 50vw) -5.5rem;
  padding: clamp(4rem, 9vw, 6.5rem) 1.5rem clamp(4.5rem, 10vw, 7rem);
  text-align: center; border-top: 1px solid var(--line);
  background:
    radial-gradient(1000px 460px at 50% 118%, oklch(46% 0.17 295 / 0.55), transparent 72%),
    radial-gradient(620px 300px at 32% 125%, oklch(38% 0.13 270 / 0.4), transparent 70%),
    radial-gradient(620px 300px at 68% 125%, oklch(40% 0.14 315 / 0.35), transparent 70%);
}
.cta-final h2 { font-size: clamp(1.9rem, 4.2vw, 2.7rem); letter-spacing: -0.025em; }
.cta-final p { color: var(--ink-3); margin: 0.65rem 0 1.8rem; }
/* plans (pricing) */
.plans { display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 1.25rem; margin-top: 2.4rem; max-width: 780px; }
.plan {
  background: var(--surface-1); border: 1px solid var(--line); border-radius: var(--r-l);
  padding: 1.9rem 1.8rem; display: flex; flex-direction: column;
}
.plan.featured {
  border-color: oklch(48% 0.18 295 / 0.65);
  background:
    radial-gradient(420px 190px at 50% -60px, oklch(48% 0.18 295 / 0.14), transparent 75%),
    var(--surface-1);
  box-shadow: 0 20px 50px oklch(0% 0 0 / 0.35);
}
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

# Hero aurora: a single-quad WebGL fragment shader (domain-warped fbm noise in
# the brand violets). Pure progressive enhancement over the CSS .hero-orb base
# layer: no WebGL, no JS, or reduced motion all fall back to the gradient orb.
_SCENE_JS = """
(function () {
  var c = document.getElementById('aurora');
  if (!c || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var gl = c.getContext('webgl', { alpha: true, antialias: false, premultipliedAlpha: true });
  if (!gl) return;
  var VS = 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}';
  var FS = [
    'precision highp float;',
    'uniform vec2 u_res; uniform float u_time;',
    'float hs(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}',
    'float n2(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);',
    ' float a=hs(i),b=hs(i+vec2(1.,0.)),c2=hs(i+vec2(0.,1.)),d=hs(i+vec2(1.,1.));',
    ' return mix(mix(a,b,f.x),mix(c2,d,f.x),f.y);}',
    'float fbm(vec2 p){float v=0.,a=.5;',
    ' for(int i=0;i<4;i++){v+=a*n2(p);p=p*2.03+vec2(11.3,7.7);a*=.5;}return v;}',
    'void main(){',
    ' vec2 uv=gl_FragCoord.xy/u_res;',
    ' float ar=u_res.x/u_res.y;',
    ' float x=uv.x*ar;',
    ' float dx=x-.5*ar;',
    ' float t=u_time*.06;',
    ' float hill=exp(-dx*dx*1.15);',
    ' vec3 col=vec3(0.);',
    ' float a=0.;',
    ' for(int i=0;i<4;i++){',
    '  float fi=float(i);',
    '  float ph=fbm(vec2(x*1.1+fi*7.3+t*.4,fi*3.1+t*.15));',
    '  float y=.1+hill*(.16+fi*.1)+(ph-.5)*.12*hill+.02*sin(x*2.+fi*2.3+t);',
    '  float d=uv.y-y;',
    '  float w=(.014+.011*fi)*(.4+hill);',
    '  float core=exp(-d*d/(w*w));',
    '  float glow=exp(-d*d/(w*w*18.));',
    '  float sh=.5+.5*sin(x*(2.6-fi*.3)+fi*1.9-t*1.2+ph*4.);',
    '  float k=core*(.55+.45*sh)*(.25+.75*hill);',
    '  vec3 rc=mix(vec3(.28,.17,.55),vec3(.66,.52,1.),k);',
    '  col+=rc*(k*.95+glow*.22*hill);',
    '  a+=k*.85+glow*.2*hill;',
    ' }',
    ' float base=exp(-dx*dx*1.4)*exp(-(uv.y-.16)*(uv.y-.16)*30.);',
    ' col+=vec3(.34,.2,.62)*base*.5;',
    ' a+=base*.4;',
    ' float ex=smoothstep(0.,.16,uv.x)*smoothstep(1.,.84,uv.x);',
    ' float ey=smoothstep(0.,.06,uv.y)*smoothstep(1.,.7,uv.y);',
    ' a=clamp(a,0.,1.)*ex*ey*.92;',
    ' col=min(col,vec3(1.));',
    ' gl_FragColor=vec4(col*a,a);',
    '}'].join('\\n');
  function sh(t, s) {
    var o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o);
    return gl.getShaderParameter(o, gl.COMPILE_STATUS) ? o : null;
  }
  var v = sh(gl.VERTEX_SHADER, VS), f = sh(gl.FRAGMENT_SHADER, FS);
  if (!v || !f) return;
  var p = gl.createProgram();
  gl.attachShader(p, v); gl.attachShader(p, f); gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) return;
  gl.useProgram(p);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  var loc = gl.getAttribLocation(p, 'a');
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  var uR = gl.getUniformLocation(p, 'u_res'), uT = gl.getUniformLocation(p, 'u_time');
  function resize() {
    /* soft render scale: the silk is blurry by design, so render at ~60% and
       let the browser upscale; caps fill-rate cost on hidpi screens */
    var s = Math.min(1.5, window.devicePixelRatio || 1) * 0.6;
    var W = Math.max(1, Math.round(c.clientWidth * s));
    var H = Math.max(1, Math.round(c.clientHeight * s));
    if (c.width !== W || c.height !== H) { c.width = W; c.height = H; gl.viewport(0, 0, W, H); }
  }
  var running = false, seen = true, t0 = performance.now();
  function frame(now) {
    if (!running) return;
    resize();
    gl.uniform2f(uR, c.width, c.height);
    gl.uniform1f(uT, (now - t0) / 1000);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    requestAnimationFrame(frame);
  }
  function play() {
    var want = seen && !document.hidden;
    if (want && !running) { running = true; requestAnimationFrame(frame); }
    else if (!want) running = false;
  }
  new IntersectionObserver(function (en) { seen = en[0].isIntersecting; play(); }).observe(c);
  document.addEventListener('visibilitychange', play);
  window.addEventListener('resize', resize);
  c.classList.add('on');
  play();
})();
"""

# Motion choreography. Content is fully visible without JS; the script hides
# elements immediately before animating them in. Gates: reduced motion and
# headless/automated browsers (navigator.webdriver) get the complete static
# page, and beforeprint force-reveals everything, so nothing can ship blank.
_REVEAL_JS = """
document.addEventListener('DOMContentLoaded', function () {
  var nav = document.querySelector('nav');
  function onScroll() { if (nav) nav.classList.toggle('scrolled', window.scrollY > 24); }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  if (!window.Motion || navigator.webdriver
      || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var animate = Motion.animate, inView = Motion.inView, stagger = Motion.stagger;
  var EASE = [0.22, 1, 0.36, 1];
  var concealed = [];
  function conceal(el, y) {
    el.style.opacity = '0';
    if (y) el.style.transform = 'translateY(' + y + 'px)';
    concealed.push(el);
  }
  function revealAll() {
    concealed.forEach(function (el) { el.style.opacity = ''; el.style.transform = ''; });
    concealed.length = 0;
  }
  window.addEventListener('beforeprint', revealAll);
  window.addEventListener('pagehide', revealAll);
  setTimeout(revealAll, 3000);

  /* hero headline: split into lines, rise line by line, then restore markup.
     Waits for the webfont (600ms cap) so line measurement is correct. */
  var h1 = document.querySelector('.hero h1[data-hero]');
  if (h1) {
    conceal(h1);
    var fontsReady = (document.fonts && document.fonts.ready)
      ? Promise.race([document.fonts.ready,
          new Promise(function (res) { setTimeout(res, 600); })])
      : Promise.resolve();
    fontsReady.then(function () {
      var orig = h1.innerHTML;
      var words = h1.textContent.trim().split(/\\s+/);
      h1.innerHTML = words.map(function (w) { return '<span class="w">' + w + '</span>'; }).join(' ');
      var lines = [], lastTop = null;
      h1.querySelectorAll('.w').forEach(function (w) {
        if (w.offsetTop !== lastTop) { lines.push([]); lastTop = w.offsetTop; }
        lines[lines.length - 1].push(w.textContent);
      });
      h1.innerHTML = lines.map(function (ws) {
        return '<span class="hl"><span class="hl-in">' + ws.join(' ') + '</span></span>';
      }).join('');
      var parts = h1.querySelectorAll('.hl-in');
      parts.forEach(function (el) { el.style.transform = 'translateY(108%)'; });
      h1.style.opacity = '';
      animate(parts, { transform: 'translateY(0%)' },
        { duration: 0.85, delay: stagger(0.1), ease: EASE });
      setTimeout(function () { h1.innerHTML = orig; }, 1600);
    });
  }
  var heroRest = document.querySelectorAll('[data-hero]:not(h1)');
  if (heroRest.length) {
    heroRest.forEach(function (el) { conceal(el, 14); });
    animate(heroRest, { opacity: 1, transform: 'translateY(0px)' },
      { duration: 0.7, delay: stagger(0.09, { startDelay: 0.4 }), ease: EASE });
  }

  /* satellite cards fade in after the copy */
  var floats = document.querySelectorAll('[data-float]');
  if (floats.length) {
    floats.forEach(function (el) { conceal(el); });
    animate(floats, { opacity: 1 },
      { duration: 0.9, delay: stagger(0.12, { startDelay: 0.65 }), ease: EASE });
  }

  /* digest value ticks up once */
  var tick = document.querySelector('[data-tick]');
  if (tick) {
    var target = parseFloat(tick.textContent.replace(/[^0-9.]/g, ''));
    if (target > 0) {
      animate(target * 0.985, target, {
        duration: 1.2, delay: 1, ease: EASE,
        onUpdate: function (v) { tick.textContent = '$' + Math.round(v).toLocaleString('en-CA'); }
      });
    }
  }

  /* scroll reveals: below-fold only, so nothing above the fold ever hides */
  document.querySelectorAll('[data-reveal]').forEach(function (el) {
    if (el.getBoundingClientRect().top > window.innerHeight * 0.9) conceal(el, 18);
    inView(el, function () {
      animate(el, { opacity: 1, transform: 'translateY(0px)' }, { duration: 0.6, ease: EASE });
    }, { amount: 0.3 });
  });
  document.querySelectorAll('[data-reveal-group]').forEach(function (group) {
    var items = group.querySelectorAll('[data-reveal-item]');
    if (!items.length) return;
    /* data-stagger opts a group into a slower, one-by-one sequence */
    var gap = parseFloat(group.getAttribute('data-stagger') || '0.08');
    if (group.getBoundingClientRect().top > window.innerHeight * 0.9) {
      items.forEach(function (el) { conceal(el, 14); });
    }
    inView(group, function () {
      animate(items, { opacity: 1, transform: 'translateY(0px)' },
        { duration: gap > 0.2 ? 0.65 : 0.55, delay: stagger(gap), ease: EASE });
    }, { amount: gap > 0.2 ? 0.35 : 0.15 });
  });

  /* chat demo: conversation plays out on first view */
  var chat = document.querySelector('[data-chat]');
  if (chat) {
    var bubbles = chat.querySelectorAll('.bubble');
    bubbles.forEach(function (b) { conceal(b, 10); });
    var played = false;
    inView(chat, function () {
      if (played) return; played = true;
      var i = 0;
      function next() {
        if (i >= bubbles.length) return;
        var b = bubbles[i++];
        function show() {
          animate(b, { opacity: 1, transform: 'translateY(0px)' }, { duration: 0.45, ease: EASE });
          setTimeout(next, b.classList.contains('bot') ? 650 : 450);
        }
        if (b.classList.contains('bot')) {
          var t = document.createElement('div');
          t.className = 'bubble bot typing';
          t.innerHTML = '<i></i><i></i><i></i>';
          t.style.left = b.offsetLeft + 'px';
          t.style.top = b.offsetTop + 'px';
          chat.appendChild(t);
          setTimeout(function () { t.remove(); show(); }, 750);
        } else show();
      }
      next();
    }, { amount: 0.45 });
  }

  /* card parallax: pointer only, composes with the float keyframes via
     the separate `translate` property */
  if (matchMedia('(pointer: fine)').matches) {
    var scene = document.querySelector('.hero-scene');
    if (scene) {
      var cards = scene.querySelectorAll('.float-card');
      var tx = 0, ty = 0, cx = 0, cy = 0, raf = 0;
      function step() {
        raf = 0;
        cx += (tx - cx) * 0.08; cy += (ty - cy) * 0.08;
        cards.forEach(function (el, i) {
          var d = 7 + i * 4;
          el.style.translate = (-cx * d) + 'px ' + (-cy * d) + 'px';
        });
        if (Math.abs(tx - cx) > 0.002 || Math.abs(ty - cy) > 0.002) {
          raf = requestAnimationFrame(step);
        }
      }
      scene.addEventListener('pointermove', function (e) {
        var r = scene.getBoundingClientRect();
        tx = (e.clientX - r.left) / r.width - 0.5;
        ty = (e.clientY - r.top) / r.height - 0.5;
        if (!raf) raf = requestAnimationFrame(step);
      });
    }
  }
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
        '<a class="keep" href="/app" data-auth="signin">Sign in</a>'
        '<a class="btn" href="/app" data-auth="cta">Get started</a>'
        "</div></div></nav>"
    )


def _auth_nav_js() -> str:
    """Swap the static nav to a signed-in state when a Supabase session exists.

    The marketing pages don't load supabase-js, so this reads the SDK's
    localStorage entry (``sb-<project-ref>-auth-token``) directly. A session
    with a refresh token counts as signed in even if the access token has
    expired — the app pages refresh it on arrival. Any parse problem falls
    back to the signed-out rendering, which is always safe."""
    supabase_url = get_settings().supabase_url
    if not supabase_url:
        return ""
    ref = urlparse(supabase_url).hostname.split(".")[0]
    return """
(function () {
  try {
    var raw = localStorage.getItem('sb-%s-auth-token');
    if (!raw) return;
    var s = JSON.parse(raw);
    if (!s || !(s.refresh_token || (s.expires_at && s.expires_at * 1000 > Date.now()))) return;
    document.querySelectorAll('[data-auth="signin"]').forEach(function (el) {
      el.remove();
    });
    document.querySelectorAll('[data-auth="cta"]').forEach(function (el) {
      el.textContent = 'Open dashboard';
    });
  } catch (e) { /* signed-out rendering is the safe default */ }
})();
""" % ref


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


def _layout(title: str, description: str, body: str, active: str = "", path: str = "/") -> str:
    base = _public_base_url()
    og_image = f"{base}/static/og.png"
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f'<meta name="description" content="{description}">\n'
        + ICON_LINKS
        + f'<meta property="og:title" content="{title}">\n'
        + f'<meta property="og:description" content="{description}">\n'
        + '<meta property="og:type" content="website">\n'
        + '<meta property="og:site_name" content="Cirvia">\n'
        + f'<meta property="og:url" content="{base}{path}">\n'
        + f'<meta property="og:image" content="{og_image}">\n'
        + '<meta name="twitter:card" content="summary_large_image">\n'
        + f'<meta name="twitter:image" content="{og_image}">\n'
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
        + "<script>"
        + _SCENE_JS
        + "</script>\n"
        + f"<script>{_auth_nav_js()}</script>\n"
        + "</body>\n</html>"
    )


# --------------------------------------------------------------------------
# Home
# --------------------------------------------------------------------------

_HOME_BODY = """
<section class="hero">
  <div class="hero-copy">
    <h1 data-hero>Know what matters before the market opens.</h1>
    <p class="lead" data-hero>Your holdings. Your brief. Every morning.</p>
    <div class="cta-row" data-hero>
      <a class="btn lg" href="/app" data-auth="cta">Get started free</a>
      <a class="quiet" href="#how">See how it works</a>
    </div>
  </div>
  <div class="hero-scene">
    <div class="hero-stars" aria-hidden="true"></div>
    <div class="hero-orb" aria-hidden="true"></div>
    <canvas id="aurora" aria-hidden="true"></canvas>
    <div class="float-card fc-chat" data-float aria-hidden="true">
      <p class="fc-q">&ldquo;Why is ENB down today?&rdquo;</p>
      <p class="fc-a">Crude fell after OPEC+ output news. ENB is your third-largest holding.</p>
    </div>
    <div class="float-card fc-digest" data-float aria-hidden="true">
      <div class="mock-top"><span class="mock-dot"></span>Morning digest
        <span class="mock-date">7:45 AM</span></div>
      <div class="mock-val"><span class="v" data-tick>$48,214</span>
        <span class="d gain">+1.2% today</span></div>
      <div class="mock-row"><span class="t">VFV</span>
        <span class="n">S&amp;P 500 ETF</span>
        <span class="chg gain">+0.8%</span></div>
      <div class="mock-row"><span class="t">NVDA</span>
        <span class="n">NVIDIA</span>
        <span class="chg gain">+2.1%</span></div>
      <div class="mock-row"><span class="t">ENB</span>
        <span class="n">Enbridge</span>
        <span class="chg loss">&minus;1.2%</span></div>
    </div>
    <div class="float-card fc-alert" data-float aria-hidden="true">
      <span class="mock-alert-k">Macro alert</span>
      <p class="fc-a">OPEC+ signals higher output. Crude down 3%; touches ENB and SU.</p>
    </div>
  </div>
</section>

<section id="features">
  <h2 data-reveal>Signal, not noise.</h2>
  <div class="ledger" data-reveal-group data-stagger="0.45">
    <div class="ledger-row" data-reveal-item>
      <h3>Morning digest</h3>
      <p>Overnight moves, what changed, and what to watch, written for your tickers.</p>
      <span class="meta">Weekdays, your time</span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Macro alerts</h3>
      <p>Fed decisions, energy shocks, geopolitics. Only when they touch your holdings.</p>
      <span class="meta">As it happens</span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>On-demand answers</h3>
      <p>News, performance, drawdowns. Every answer grounded in your actual positions.</p>
      <span class="meta">Any time</span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Automatic sync</h3>
      <p>TFSA, RRSP, and taxable accounts stay current over a read-only connection.</p>
      <span class="meta">Continuous</span>
    </div>
  </div>
</section>

<section id="showcase">
  <h2 data-reveal>Ask about your book.</h2>
  <p class="sect-lead" data-reveal>Every answer starts from the positions you
  actually hold.</p>
  <div class="show-panel chat-demo" data-chat aria-hidden="true">
    <div class="mock-top"><span class="mock-dot"></span>Chat</div>
    <div class="bubble user">Why is ENB down today?</div>
    <div class="bubble bot">Crude fell 3% after OPEC+ signalled higher August
    output. ENB is your third-largest holding; pipelines are less exposed than
    producers, but sentiment is dragging the sector.</div>
    <div class="bubble user">Anything to watch this week?</div>
    <div class="bubble bot">Two things: NVDA reports earnings Wednesday after
    close, and the Bank of Canada rate decision lands Thursday morning.</div>
  </div>
</section>

<section id="how">
  <h2 data-reveal>Connected in three minutes.</h2>
  <div class="steps" data-reveal-group>
    <div class="step" data-reveal-item><div class="num"></div><div><h3>Connect your brokerage</h3>
    <p>Link through SnapTrade's secure portal. Cirvia never sees or stores your
    brokerage login.</p></div></div>
    <div class="step" data-reveal-item><div class="num"></div><div><h3>We read your holdings</h3>
    <p>Read-only access syncs positions and balances. Cirvia can never place a trade
    or move money.</p></div></div>
    <div class="step" data-reveal-item><div class="num"></div><div><h3>Get informed, daily</h3>
    <p>Your digest each weekday morning, alerts when the world moves, answers when
    you ask.</p></div></div>
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

<div class="cta-final" data-reveal>
  <h2>Know your portfolio by 7:45.</h2>
  <p>Start free. Connected in under three minutes.</p>
  <a class="btn lg" href="/app" data-auth="cta">Get started free</a>
</div>
"""

# --------------------------------------------------------------------------
# Contact
# --------------------------------------------------------------------------

_CONTACT_BODY = f"""
<section class="hero" style="padding-bottom:0;">
  <div class="hero-copy">
    <h1 data-hero>Get in touch</h1>
    <p class="lead" data-hero>Questions, support, privacy inquiries, or partnerships.
    We read everything.</p>
  </div>
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
  <div class="hero-copy">
    <h1 data-hero>Start free. Go Pro when you're ready.</h1>
    <p class="lead" data-hero>Read-only on every plan. Your brokerage password
    never leaves your bank.</p>
  </div>
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
      <a class="btn ghost" href="/app">Start free, upgrade later</a>
      <p class="price-note" style="margin-top:0.75rem;">Pro billing is coming soon.
      Every new account starts on the Free plan.</p>
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

<div class="cta-final" data-reveal>
  <h2>Ready when you are.</h2>
  <p>Start free. Upgrade any time.</p>
  <a class="btn lg" href="/app" data-auth="cta">Get started free</a>
</div>
"""


LANDING_HTML = _layout(
    "Cirvia — AI portfolio analyst for Canadian investors",
    "Connect Wealthsimple, get a daily digest, macro alerts, and on-demand answers about your "
    "real holdings. Read-only. No trade execution.",
    _HOME_BODY,
    active="home",
    path="/",
)

PRICING_HTML = _layout(
    "Pricing — Cirvia",
    "Cirvia pricing: start free with a weekly digest and daily chat, or go Pro at $12/mo "
    "($120/yr) for unlimited accounts, daily digests, macro alerts, and unlimited chat.",
    _PRICING_BODY,
    active="pricing",
    path="/pricing",
)

CONTACT_HTML = _layout(
    "Contact — Cirvia",
    "Get in touch with Cirvia for early access, support, privacy requests, or partnerships.",
    _CONTACT_BODY,
    active="contact",
    path="/contact",
)

PRIVACY_HTML = _layout(
    "Privacy Policy — Cirvia",
    "How Cirvia collects, uses, and protects your personal and brokerage information.",
    _PRIVACY_BODY,
    path="/privacy",
)

TERMS_HTML = _layout(
    "Terms of Service — Cirvia",
    "The terms governing your use of Cirvia's read-only, informational portfolio analysis service.",
    _TERMS_BODY,
    path="/terms",
)
