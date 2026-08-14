"""Public marketing + legal site for Cirvia.

Server-rendered HTML (no framework) served from ``app.main`` at ``/``,
``/contact``, ``/privacy``, and ``/terms``. All pages share one layout and
stylesheet via ``_layout``. These pages are auth-exempt and are also what
SnapTrade / partner reviewers see.
"""

from __future__ import annotations

import json
import re
from datetime import date
from html import unescape
from urllib.parse import quote, urlparse

from app.config import get_settings

# The public support address. hello@cirvia.ca must have receiving set up
# (e.g. Cloudflare Email Routing forwarding to the owner's inbox) before a
# deploy of this constant goes live — a dead contact address on legal pages
# is worse than a personal one.
CONTACT_EMAIL = "hello@cirvia.ca"
# Cirvia is not (yet) a registered business name; it's operated as an
# unregistered Ontario sole proprietorship. No individual is named on the
# public pages; update this note if that ever changes (incorporation or an
# Ontario Business Names Act registration).
LAST_UPDATED = "July 5, 2026"

# Brand mark: a stylized dahlia — one petal path rotated into three layered
# rings in the orchid-to-plum range, with the flower's yellow-green core kept
# as the signature detail. Emitted as plain paths (no <use>/ids) so the same
# markup can repeat safely within a page and inside CSS data URIs.
_PETAL = "M0 -104C18 -88 21 -52 0 -18C-21 -52 -18 -88 0 -104Z"


def _dahlia_ring(fill: str, transform: str = "") -> str:
    tf = f" transform='{transform}'" if transform else ""
    petals = "".join(
        f"<path d='{_PETAL}' transform='rotate({a})'/>" for a in range(0, 360, 30)
    )
    return f"<g fill='{fill}'{tf}>{petals}</g>"


_DAHLIA_BODY = (
    _dahlia_ring("#DCA4EE")
    + _dahlia_ring("#C776E6", "rotate(15) scale(0.74)")
    + _dahlia_ring("#AC4BD5", "scale(0.5)")
    + "<circle r='20' fill='#6B2593'/><circle r='7' fill='#E3EA6B'/>"
)

# Standalone mark (needs xmlns: used as a CSS data URI and for PNG renders).
LOGO_MARK_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 240 240'>"
    f"<g transform='translate(120 120)'>{_DAHLIA_BODY}</g></svg>"
)

# Tab icon: the dahlia on a rounded deep-aubergine tile (reads better at 16px
# than petals on transparency). PNG fallbacks in app/static/ cover Apple
# touch + OG cards.
_FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 240 240'>"
    "<rect width='240' height='240' rx='56' fill='#2E123F'/>"
    f"<g transform='translate(120 120) scale(0.8)'>{_DAHLIA_BODY}</g></svg>"
)

# Shared by the marketing layout and the app pages (app/webapp.py).
ICON_LINKS = (
    f'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,{quote(_FAVICON_SVG)}">\n'
    '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">\n'
    '<meta name="theme-color" content="#f7f4fa">\n'
)


def _public_base_url() -> str:
    """Absolute origin for og:url / og:image (no trailing slash)."""
    return (get_settings().public_base_url or "https://cirvia.ca").rstrip("/")


# --------------------------------------------------------------------------
# SEO: structured data, sitemap, robots
# --------------------------------------------------------------------------
#
# JSON-LD is generated from the same Python data (FAQ lists, plan numbers)
# that drives the visible HTML, never typed twice, so the two can't drift.
# No Review/AggregateRating schema anywhere: there are no testimonials on
# this site, and fabricating a rating would break the same honesty posture
# the product itself is built on (see marketing.md's compliance guardrails).


def _strip_for_jsonld(fragment: str) -> str:
    """Plain text for a JSON-LD string field from a bit of inline HTML
    (an <a> tag, an HTML entity like &rsquo;): strip tags, decode entities,
    collapse whitespace."""
    return unescape(" ".join(re.sub(r"<[^>]+>", "", fragment).split()))


def _jsonld_script(data: dict) -> str:
    return f'<script type="application/ld+json">{json.dumps(data)}</script>\n'


def _site_jsonld(base: str) -> str:
    """Sitewide Organization + WebSite schema, emitted on every page."""
    return _jsonld_script(
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "Organization",
                    "name": "Cirvia",
                    "url": base,
                    "logo": f"{base}/static/apple-touch-icon.png",
                },
                {"@type": "WebSite", "name": "Cirvia", "url": base},
            ],
        }
    )


def _faq_html(items: list[tuple[str, str]]) -> str:
    """Visible <details> markup for a list of (question, answer_html) pairs."""
    return "\n".join(
        f"    <details data-reveal-item><summary>{q}</summary>\n"
        f"    <p>{a}</p></details>"
        for q, a in items
    )


def _faq_jsonld(items: list[tuple[str, str]]) -> dict:
    """FAQPage schema for the same (question, answer_html) pairs rendered by
    _faq_html, so visible copy and structured data can never disagree."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": _strip_for_jsonld(q),
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": _strip_for_jsonld(a),
                },
            }
            for q, a in items
        ],
    }


# The 9 public marketing routes. No per-ticker or dynamic pages here yet
# (that's ROADMAP Phase 2, blocked on data-licensing/ops work) — this is
# just the static site's own crawl surface.
_SITEMAP_PAGES: list[tuple[str, str, float]] = [
    ("/", "weekly", 1.0),
    ("/pricing", "weekly", 0.9),
    ("/track-record", "daily", 0.8),
    ("/screener", "daily", 0.6),
    ("/methodology", "monthly", 0.6),
    ("/sample-digest", "monthly", 0.5),
    ("/contact", "yearly", 0.3),
    ("/privacy", "yearly", 0.2),
    ("/terms", "yearly", 0.2),
]


def sitemap_xml() -> str:
    """Generated per-request (not frozen at import) so <loc> always tracks
    the live PUBLIC_BASE_URL — prod resolves a canonical www/apex host that
    a module-load-time constant could get stale against."""
    base = _public_base_url()
    today = date.today().isoformat()
    entries = "\n".join(
        f"  <url><loc>{base}{path}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>{freq}</changefreq><priority>{priority}</priority></url>"
        for path, freq, priority in _SITEMAP_PAGES
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n"
        "</urlset>"
    )


def robots_txt() -> str:
    """Generated per-request for the same live-base-url reason as sitemap_xml."""
    base = _public_base_url()
    allow = "\n".join(f"Allow: {path}" for path, _, _ in _SITEMAP_PAGES)
    return (
        "User-agent: *\n"
        f"{allow}\n"
        "Disallow: /app\n"
        "Disallow: /api\n"
        "Disallow: /webhooks\n"
        "Disallow: /funnel\n"
        "Disallow: /stocks/\n"
        "Disallow: /health\n"
        f"\nSitemap: {base}/sitemap.xml\n"
    )


_CSS = """
:root {
  color-scheme: light;
  --bg: oklch(97.5% 0.01 305);          /* warm lavender-tinted off-white canvas */
  --surface-1: oklch(99.2% 0.004 305);  /* cards: near-white, lifts off the tinted canvas */
  --surface-2: oklch(95.2% 0.012 305);  /* inputs, chips, hover fills (inset: darker than cards) */
  --surface-3: oklch(92.5% 0.018 305);  /* tooltips, tracks, user chat bubbles */
  --line: oklch(90% 0.018 305);
  --line-strong: oklch(82% 0.026 305);
  --ink: oklch(25% 0.035 300);
  --ink-2: oklch(37% 0.03 300);
  --ink-3: oklch(48% 0.03 300);         /* muted; ~5:1 on bg — going lighter fails AA */
  --accent: oklch(52% 0.16 295);        /* lavender fill; white text on it stays AA */
  --accent-hover: oklch(45% 0.16 295);  /* hovers darken on a light canvas */
  --accent-text: oklch(46% 0.15 295);
  --accent-deep: oklch(93% 0.045 295);  /* pale lavender fill, paired with --accent-text */
  --accent-wash: oklch(95% 0.035 300);  /* selected-chip / bot-bubble tint */
  --gain: oklch(50% 0.11 155);
  --loss: oklch(50% 0.15 25);
  --warn: oklch(54% 0.12 75);
  --shadow: oklch(35% 0.05 300);        /* shadow ink, always used at low alpha */
  --r-s: 8px; --r-m: 12px; --r-l: 18px;
  --maxw: 1060px;
  --ease: cubic-bezier(0.22, 1, 0.36, 1);
  --font: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --sidebar-w: 15rem;            /* 240px, expanded rail */
  --sidebar-w-collapsed: 4rem;   /* 64px, icon-only rail */
  --active-sidebar-w: var(--sidebar-w); /* tracks collapse state; see html.sidebar-collapsed below */
  --topbar-h: 3.25rem;           /* sticky top strip (mobile drawer trigger) */
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }
html, body { overflow-x: clip; }
body {
  font-family: var(--font);
  /* soft pastel aurora at the top, fading into the off-white canvas */
  background:
    radial-gradient(1200px 600px at 50% -120px, oklch(90% 0.055 295 / 0.8), transparent 70%),
    radial-gradient(800px 480px at 16% -60px, oklch(92% 0.045 265 / 0.55), transparent 70%),
    radial-gradient(900px 500px at 84% -80px, oklch(92% 0.05 335 / 0.5), transparent 70%),
    radial-gradient(1800px 950px at 50% -220px, oklch(95% 0.025 300 / 0.8), transparent 80%),
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
.logo { font-size: 1.3rem; font-weight: 800; letter-spacing: -0.03em; color: var(--ink); }
.logo span { color: var(--accent-text); }
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
  /* star specks read as dust on the light canvas — retired with the pastel theme */
  display: none;
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
    radial-gradient(ellipse 55% 48% at 50% 58%, oklch(82% 0.1 295 / 0.75), transparent 72%),
    radial-gradient(ellipse 70% 55% at 42% 62%, oklch(88% 0.07 265 / 0.55), transparent 68%),
    radial-gradient(ellipse 45% 40% at 58% 48%, oklch(86% 0.08 320 / 0.5), transparent 70%);
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
  border: 1px solid oklch(78% 0.05 295 / 0.7); border-radius: var(--r-m);
  padding: 0.95rem 1.1rem; font-size: 0.88rem; text-align: left;
  box-shadow: 0 30px 70px oklch(35% 0.05 300 / 0.16), 0 4px 16px oklch(35% 0.05 300 / 0.08);
  animation: floaty 7s ease-in-out infinite alternate;
}
.fc-digest { left: 50%; top: 17%; width: min(330px, 80vw); z-index: 3;
  transform: translate(-50%, 0); animation: floaty-center 8s ease-in-out infinite alternate; }
.fc-alert { right: 3%; top: 2%; width: 244px; animation-delay: -2.5s; }
.fc-chat { left: 3%; bottom: 26%; width: 254px; animation-delay: -4.5s; }
.fc-verify { right: 6%; bottom: 18%; width: 240px; animation-delay: -6s; }
.fc-verify .mock-alert-k { color: var(--gain); }
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
    transform: none !important; animation: none; box-shadow: 0 12px 32px oklch(35% 0.05 300 / 0.12); }
  .fc-chat { display: none; }
  .fc-verify { display: none; }
  .hero-stars { display: none; }
}
/* showcase (chat demo) */
.show-panel { background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-l); padding: 1.3rem 1.4rem 1.5rem; }
.chat-demo { position: relative; max-width: 640px; margin-top: 2.2rem; }
.bubble { padding: 0.65rem 0.95rem; border-radius: var(--r-m); margin-top: 0.7rem;
  font-size: 0.92rem; line-height: 1.55; max-width: 92%; width: fit-content; }
.bubble.user { background: var(--surface-3); color: var(--ink); margin-left: auto; }
.bubble.bot { background: var(--accent-wash); color: var(--ink-2); }
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
    radial-gradient(1000px 460px at 50% 118%, oklch(87% 0.075 295 / 0.75), transparent 72%),
    radial-gradient(620px 300px at 32% 125%, oklch(90% 0.055 265 / 0.55), transparent 70%),
    radial-gradient(620px 300px at 68% 125%, oklch(90% 0.06 330 / 0.5), transparent 70%);
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
  border-color: oklch(52% 0.16 295 / 0.5);
  background:
    radial-gradient(420px 190px at 50% -60px, oklch(52% 0.16 295 / 0.08), transparent 75%),
    var(--surface-1);
  box-shadow: 0 20px 50px oklch(35% 0.06 300 / 0.14);
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
/* proof: stat tiles filled from the live track record + verification story */
.stat-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem; margin-top: 2.2rem; }
.stat-strip[hidden] { display: none; } /* author display beats the hidden attr otherwise */
.stat { background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-m); padding: 1.1rem 1.3rem; }
.stat .k { display: block; font-size: 1.8rem; font-weight: 800; color: var(--ink);
  letter-spacing: -0.015em; font-variant-numeric: tabular-nums; }
.stat .l { color: var(--ink-3); font-size: 0.85rem; }
.pro-pill { display: inline-block; font-size: 0.68rem; font-weight: 700;
  color: var(--accent-text); background: var(--accent-deep); border-radius: 999px;
  padding: 0.12rem 0.55rem; margin-left: 0.5rem; vertical-align: 0.14em;
  letter-spacing: 0.03em; }
/* track record table */
.table-scroll { overflow-x: auto; margin-top: 2.2rem; background: var(--surface-1);
  border: 1px solid var(--line); border-radius: var(--r-l); }
.tr-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; min-width: 620px; }
.tr-table th { text-align: left; font-size: 0.76rem; font-weight: 700;
  letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-3);
  padding: 0.9rem 1.1rem; border-bottom: 1px solid var(--line-strong); }
.tr-table td { padding: 0.7rem 1.1rem; border-bottom: 1px solid var(--line);
  color: var(--ink-2); }
.tr-table tr:last-child td { border-bottom: none; }
.tr-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.tr-table .tick { font-weight: 700; color: var(--ink); }
/* valuation screener (/screener) */
.scr-controls { display: flex; gap: 0.7rem; flex-wrap: wrap; align-items: center;
  margin-top: 1.6rem; }
.scr-search { flex: 1 1 260px; background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-m); padding: 0.6rem 0.9rem; color: var(--ink); font-size: 0.92rem;
  font-family: inherit; }
.scr-search:focus { outline: none; border-color: var(--line-strong); }
.scr-count { color: var(--ink-3); font-size: 0.85rem; white-space: nowrap; }
.scr-table th[data-sort] { cursor: pointer; user-select: none; }
.scr-table th[data-sort]:hover { color: var(--ink); }
.scr-table th[data-sort]::after { content: ""; margin-left: 0.3rem; opacity: 0.5; }
.scr-table th[data-sort].asc::after { content: "\\2191"; opacity: 1; }
.scr-table th[data-sort].desc::after { content: "\\2193"; opacity: 1; }
.vd-badge { display: inline-block; font-size: 0.78rem; font-weight: 650; border-radius: 999px;
  padding: 0.16rem 0.65rem; border: 1px solid var(--line-strong); white-space: nowrap; }
.vd-under { color: var(--gain); }
.vd-over { color: var(--loss); }
.vd-fair { color: var(--ink-2); }
.vd-none { color: var(--ink-3); }
/* sample digest: the plain-text digest, presented as it reads on your phone */
.dg { padding-top: 0.9rem; font-size: 0.94rem; line-height: 1.6; color: var(--ink-2); }
.dg .dg-label { font-size: 0.76rem; font-weight: 700; letter-spacing: 0.06em;
  color: var(--ink-3); margin: 1.1rem 0 0.2rem; }
.dg .dg-line strong { color: var(--ink); }
.dg ul { list-style: none; }
.dg li { position: relative; padding-left: 1rem; margin: 0.2rem 0; }
.dg li::before { content: "–"; position: absolute; left: 0; color: var(--ink-3); }
.dg .dg-holding { margin-top: 0.55rem; }
.dg .dg-holding .h { font-variant-numeric: tabular-nums; color: var(--ink); font-weight: 600; }
.dg .dg-holding p { padding-left: 1.1rem; color: var(--ink-2); font-size: 0.9rem; }
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
/* phone tier: tighter gutters and rhythm, hero type scaled for ~375px,
   full-width primary CTA */
@media (max-width: 640px) {
  .wrap { padding: 0 1.1rem 4rem; }
  h1 { font-size: clamp(2.1rem, 9vw, 2.5rem); }
  section { padding-top: clamp(3rem, 12vw, 4.5rem); }
  .cta-row { gap: 0.8rem; }
  .cta-row .btn.lg { width: min(100%, 320px); text-align: center; }
  .plan { padding: 1.4rem 1.2rem; }
  .contact-card { padding: 1.5rem 1.2rem; }
  .foot-inner { gap: 1.75rem 2.5rem; padding: 2.25rem 1.1rem 2rem; }
  .foot-bottom { padding: 0 1.1rem 2.25rem; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""

# Dahlia mark ahead of every wordmark: one rule covers the nav, footer, auth
# pages, and the unsubscribe page (they all share .logo) with no per-site
# markup. Appended here because the data URI interpolates LOGO_MARK_SVG.
_CSS += (
    ".logo::before { content: ''; display: inline-block;"
    " width: 1.15em; height: 1.15em; margin-right: 0.4em; vertical-align: -0.18em;"
    f' background: url("data:image/svg+xml,{quote(LOGO_MARK_SVG)}")'
    " no-repeat center / contain; }\n"
)

# Sidebar shell: a persistent left rail on desktop (collapsible to an
# icon-only rail) and an off-canvas drawer with a sticky top strip on
# mobile/tablet. Shared by the marketing site (this file) and the signed-in
# app shell (app/webapp.py, which imports _CSS and rides along for free) via
# _sidebar_shell() — each caller supplies its own link list, icons, and
# footer content; only the drawer/rail mechanics live here, once.
# Breakpoint: 901px+ is rail mode, <=900px is drawer mode. Media queries
# can't read custom properties, so 900/901 are hardcoded on every rule below
# rather than derived from a --sidebar-breakpoint var.
_SIDEBAR_CSS = """
.sidebar-topbar {
  position: sticky; top: 0; z-index: 20;
  display: flex; align-items: center; gap: 0.9rem;
  height: var(--topbar-h); padding: 0 1.1rem;
  background: oklch(97.5% 0.01 305 / 0.9); backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--line);
}
.sidebar-topbar .logo { font-size: 1.1rem; }
.sidebar-topbar .topbar-extra { flex: 1; min-width: 0; }
@media (min-width: 901px) { .sidebar-topbar { display: none; } }

.sidebar-hamburger { display: inline-flex; flex-direction: column; align-items: center;
  justify-content: center; background: none; border: 0; cursor: pointer;
  padding: 0.55rem; margin: -0.55rem 0 -0.55rem -0.4rem; flex: none; }
.sidebar-hamburger span { display: block; width: 20px; height: 2px; border-radius: 2px;
  background: var(--ink); margin: 5px 0;
  transition: transform 0.2s var(--ease), opacity 0.2s var(--ease); }
body.sidebar-open .sidebar-hamburger span:first-child { transform: translateY(3.5px) rotate(45deg); }
body.sidebar-open .sidebar-hamburger span:last-child { transform: translateY(-3.5px) rotate(-45deg); }
@media (min-width: 901px) { .sidebar-hamburger { display: none; } }

.sidebar-backdrop { position: fixed; inset: 0; z-index: 79;
  background: oklch(35% 0.05 300 / 0.35); opacity: 0; pointer-events: none;
  transition: opacity 0.2s var(--ease); }
.sidebar-backdrop.open { opacity: 1; pointer-events: auto; }
@media (min-width: 901px) { .sidebar-backdrop { display: none; } }
body.sidebar-open { overflow: hidden; }

.sidebar {
  position: fixed; top: 0; left: 0; bottom: 0; z-index: 80; overflow: hidden;
  width: var(--sidebar-w); display: flex; flex-direction: column;
  background: var(--surface-1); border-right: 1px solid var(--line);
  transition: width 0.2s var(--ease);
}
html.sidebar-collapsed .sidebar { width: var(--sidebar-w-collapsed); }
html.sidebar-collapsed { --active-sidebar-w: var(--sidebar-w-collapsed); }
.sidebar-head { display: flex; align-items: center; gap: 0.3rem;
  padding: 1.1rem 0.85rem 0.75rem 1.1rem; }
.sidebar-head .sidebar-logo { flex: 1; min-width: 0; overflow: hidden; white-space: nowrap; }
html.sidebar-collapsed .sidebar-logo::before { margin-right: 0; }
.sidebar-collapse, .sidebar-close { display: inline-flex; align-items: center; justify-content: center;
  background: none; border: 0; cursor: pointer; color: var(--ink-3); flex: none;
  width: 28px; height: 28px; border-radius: var(--r-s);
  transition: background 0.15s var(--ease), color 0.15s var(--ease), transform 0.2s var(--ease); }
.sidebar-collapse svg, .sidebar-close svg { width: 16px; height: 16px; }
.sidebar-collapse:hover, .sidebar-close:hover { background: var(--surface-2); color: var(--ink); }
html.sidebar-collapsed .sidebar-collapse { transform: rotate(180deg); }
.sidebar-close { display: none; }

.sidebar-nav { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 0.4rem 0.7rem;
  display: flex; flex-direction: column; gap: 0.1rem; }
.sidebar-foot { padding: 0.7rem; border-top: 1px solid var(--line);
  display: flex; flex-direction: column; gap: 0.25rem; }

.side-link { position: relative; display: flex; align-items: center; gap: 0.85rem;
  padding: 0.62rem 0.75rem; border-radius: var(--r-s); color: var(--ink-3);
  font-family: var(--font); font-size: 0.92rem; font-weight: 600; white-space: nowrap;
  overflow: hidden; background: none; border: 0; width: 100%; text-align: left; cursor: pointer; }
.side-link:hover { background: var(--surface-2); color: var(--ink); text-decoration: none; }
.side-link.active { background: var(--accent-deep); color: var(--accent-text); }
.side-link .ico { flex: none; width: 20px; height: 20px; display: grid; place-items: center; }
.side-link .ico svg { width: 19px; height: 19px; }
.side-link .lbl { overflow: hidden; text-overflow: ellipsis; opacity: 1;
  transition: opacity 0.12s linear; }
.side-link.btn-cta { background: var(--accent); color: #fff; }
.side-link.btn-cta:hover { background: var(--accent-hover); color: #fff; }

html.sidebar-collapsed .side-link .lbl { opacity: 0; width: 0; }
html.sidebar-collapsed .side-link { justify-content: center; padding-left: 0; padding-right: 0; gap: 0; }
html.sidebar-collapsed .sidebar-head .sidebar-logo { display: none; }
html.sidebar-collapsed .sidebar-head { justify-content: center; padding: 0.9rem 0.4rem 0.75rem; }
html.sidebar-collapsed .side-link::after {
  content: attr(data-label); position: absolute; left: calc(100% + 10px); top: 50%;
  transform: translateY(-50%); background: var(--surface-1);
  border: 1px solid var(--line-strong); border-radius: var(--r-s);
  padding: 0.35rem 0.65rem; font-size: 0.82rem; font-weight: 600; color: var(--ink);
  white-space: nowrap; box-shadow: 0 12px 32px oklch(35% 0.05 300 / 0.16);
  opacity: 0; pointer-events: none; transition: opacity 0.12s var(--ease) 0.35s; z-index: 90; }
html.sidebar-collapsed .side-link:hover::after,
html.sidebar-collapsed .side-link:focus-visible::after { opacity: 1; }

@media (min-width: 901px) {
  /* footer/.app-foot have no max-width of their own (their .foot-inner /
     .foot-bottom children center themselves), so they just need to clear
     the fixed sidebar. .wrap and .app-wrap *do* cap at a max-width, so a
     plain margin-left here would leave the auto right margin absorbing all
     the leftover space instead of splitting it — the content would hug the
     sidebar instead of sitting centered in the remaining viewport. Centering
     that remaining space requires computing both margins from the sidebar's
     current width via --active-sidebar-w (kept in sync by the
     html.sidebar-collapsed override above) and each box's own max-width
     (--content-w, set per selector below). */
  /* "body X" (not bare "X") is deliberate: app/webapp.py's _APP_CSS is
     concatenated *after* this file's _CSS inside the single style element
     ({_CSS}{_APP_CSS} - never write a literal closing style tag in these
     comments, the HTML parser ends the element there and drops the rest of
     the stylesheet),
     and .app-wrap's own base rule there sets a plain "margin: 0 auto" —
     equal specificity, later in source, so it would silently win and wipe
     these values back to auto, leaving content centered in the full
     viewport with no allowance for the fixed sidebar (which then overlaps
     it). The "body " prefix outranks that regardless of source order. */
  body footer, body .app-foot { margin-left: var(--active-sidebar-w);
    transition: margin-left 0.2s var(--ease); }
  body .wrap, body .app-wrap {
    margin-left: max(var(--active-sidebar-w),
      calc((100vw + var(--active-sidebar-w) - var(--content-w)) / 2));
    margin-right: max(0px, calc((100vw - var(--active-sidebar-w) - var(--content-w)) / 2));
    transition: margin-left 0.2s var(--ease), margin-right 0.2s var(--ease);
  }
  .wrap { --content-w: var(--maxw); }
  .app-wrap { --content-w: 880px; }
}

@media (max-width: 900px) {
  .sidebar-collapse { display: none; }
  .sidebar-close { display: inline-flex; }
  .sidebar, html.sidebar-collapsed .sidebar {
    width: 16.5rem; transform: translateX(-100%);
    transition: transform 0.2s var(--ease);
    box-shadow: 0 18px 48px -12px oklch(35% 0.05 300 / 0.35); }
  .sidebar.open { transform: translateX(0); }
  html.sidebar-collapsed .side-link .lbl { opacity: 1; width: auto; }
  html.sidebar-collapsed .side-link { justify-content: flex-start;
    padding-left: 0.75rem; padding-right: 0.75rem; gap: 0.85rem; }
  html.sidebar-collapsed .side-link::after { display: none; }
  html.sidebar-collapsed .sidebar-head .sidebar-logo .word { display: inline; }
  html.sidebar-collapsed .sidebar-logo::before { margin-right: 0.4em; }
  html.sidebar-collapsed .sidebar-head { justify-content: flex-start;
    padding-left: 1.1rem; padding-right: 0.85rem; }
  html.sidebar-collapsed .sidebar-head .sidebar-logo { display: block; }
}
"""
_CSS += _SIDEBAR_CSS

_FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:'
    'ital,wght@0,400..800;1,400&display=swap" rel="stylesheet">\n'
)

MOTION_CDN = "https://cdn.jsdelivr.net/npm/motion@12/dist/motion.js"

# Hero aurora: a single-quad WebGL fragment shader (domain-warped fbm noise in
# pastel lavenders — ribbons sit darker than the light canvas, like watercolor).
# Pure progressive enhancement over the CSS .hero-orb base layer: no WebGL, no
# JS, or reduced motion all fall back to the gradient orb.
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
    '  vec3 rc=mix(vec3(.72,.62,.94),vec3(.55,.4,.92),k);',
    '  col+=rc*(k*.95+glow*.22*hill);',
    '  a+=k*.85+glow*.2*hill;',
    ' }',
    ' float base=exp(-dx*dx*1.4)*exp(-(uv.y-.16)*(uv.y-.16)*30.);',
    ' col+=vec3(.62,.5,.9)*base*.5;',
    ' a+=base*.4;',
    ' float ex=smoothstep(0.,.16,uv.x)*smoothstep(1.,.84,uv.x);',
    ' float ey=smoothstep(0.,.06,uv.y)*smoothstep(1.,.7,uv.y);',
    ' a=clamp(a,0.,1.)*ex*ey*.55;',
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

# Applies the persisted collapsed-rail state before first paint, inlined in
# <head> (same placement as _auth_redirect_js) so desktop visitors never see
# a flash of the wrong sidebar width. Runs on both the marketing site and
# the app shell regardless of whether Supabase is configured.
_SIDEBAR_PRECOLLAPSE_JS = """
(function () {
  try {
    if (localStorage.getItem('cirvia:sidebar:collapsed') === '1') {
      document.documentElement.classList.add('sidebar-collapsed');
    }
  } catch (e) { /* storage unavailable; default to expanded */ }
})();
"""

# Sidebar drawer (mobile) + collapsible rail (desktop) behavior. Dependency
# -free so it survives a failed Motion CDN load, same as the phone menu it
# replaces. Shared by the marketing site and the app shell.
_SIDEBAR_JS = """
document.addEventListener('DOMContentLoaded', function () {
  var html = document.documentElement;
  var sidebar = document.getElementById('sidebar');
  var backdrop = document.querySelector('[data-sidebar-backdrop]');
  var openBtns = document.querySelectorAll('[data-sidebar-open]');
  var closeBtn = document.querySelector('[data-sidebar-close]');
  var collapseBtn = document.querySelector('[data-sidebar-collapse]');
  var opener = null;

  function isDrawerMode() { return matchMedia('(max-width: 900px)').matches; }

  function setOpen(open) {
    if (!sidebar) return;
    sidebar.classList.toggle('open', open);
    if (backdrop) backdrop.classList.toggle('open', open);
    document.body.classList.toggle('sidebar-open', open);
    openBtns.forEach(function (b) { b.setAttribute('aria-expanded', open ? 'true' : 'false'); });
    if (open) {
      var first = sidebar.querySelector('a, button');
      if (first) first.focus();
    } else if (opener) {
      opener.focus();
      opener = null;
    }
  }

  openBtns.forEach(function (btn) {
    btn.addEventListener('click', function () { opener = btn; setOpen(true); });
  });
  if (closeBtn) closeBtn.addEventListener('click', function () { setOpen(false); });
  if (backdrop) backdrop.addEventListener('click', function () { setOpen(false); });
  if (sidebar) {
    sidebar.addEventListener('click', function (e) {
      if (isDrawerMode() && e.target.closest('a')) setOpen(false);
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && sidebar && sidebar.classList.contains('open')) setOpen(false);
  });
  document.addEventListener('click', function (e) {
    if (!sidebar || !sidebar.classList.contains('open')) return;
    if (sidebar.contains(e.target)) return;
    var onOpener = false;
    openBtns.forEach(function (b) { if (b.contains(e.target)) onOpener = true; });
    if (!onOpener) setOpen(false);
  });
  /* focus trap: Tab/Shift+Tab cycles within the drawer while it's open */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Tab' || !sidebar || !sidebar.classList.contains('open')) return;
    var items = sidebar.querySelectorAll('a, button');
    if (!items.length) return;
    var first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  /* crossing the breakpoint on resize should never leave the drawer stuck open */
  window.addEventListener('resize', function () {
    if (!isDrawerMode()) setOpen(false);
  });

  if (collapseBtn) {
    collapseBtn.addEventListener('click', function () {
      var collapsed = !html.classList.contains('sidebar-collapsed');
      html.classList.toggle('sidebar-collapsed', collapsed);
      try { localStorage.setItem('cirvia:sidebar:collapsed', collapsed ? '1' : '0'); }
      catch (e) { /* storage unavailable */ }
    });
  }
});
"""

_NAV_LINKS = (
    ("how", "/#how", "How it works"),
    ("screener", "/screener", "Screener"),
    ("track", "/track-record", "Track record"),
    ("pricing", "/pricing", "Pricing"),
    ("contact", "/contact", "Contact"),
)

# Small hand-rolled 20x20 stroke icons, same weight/style as the dahlia
# wordmark. Structural ones (chevron, close) are used by the sidebar shell
# itself; the rest label the marketing nav's own links. app/webapp.py keeps
# its own icon set for the app-shell links (dashboard/picks/risk/etc.).
_ICONS = {
    "chevron": (
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round"><path d="M12.5 4.5 6 10l6.5 5.5"/></svg>'
    ),
    "close": (
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"'
        ' stroke-linecap="round"><path d="M5 5l10 10M15 5 5 15"/></svg>'
    ),
    "how": (
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M10 2.5a5 5 0 0 0-3 9c.6.5 1 1.2 1 2v.5h4V13.5c0-.8.4-1.5 1-2a5 5 0 0 0-3-9Z"/>'
        '<path d="M8 17.5h4M8.5 15.5h3"/></svg>'
    ),
    "screener": (
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 4h14l-5.5 6.5v5L8.5 17v-6.5L3 4Z"/></svg>'
    ),
    "track": (
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 15 8 9l3.5 3L17 5"/><path d="M12.5 5H17v4.5"/></svg>'
    ),
    "pricing": (
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M10.5 3H4v6.5L11 16l6-6-6.5-7Z"/>'
        '<circle cx="7.2" cy="6.2" r="1" fill="currentColor" stroke="none"/></svg>'
    ),
    "contact": (
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="5" width="14" height="10" rx="1.5"/>'
        '<path d="m3.5 5.5 6.5 5.5 6.5-5.5"/></svg>'
    ),
    "signin": (
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M8 3.5H4.5v13H8"/><path d="M12 6.5 16 10l-4 3.5M16 10H8"/></svg>'
    ),
    "cta": (
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round"><path d="M4 10h11M11 5.5 16 10l-5 4.5"/></svg>'
    ),
}


def _sidebar_shell(
    *,
    nav_links_html: str,
    foot_html: str = "",
    topbar_extra: str = "",
    mobile_bar_class: str = "marketing-bar",
) -> str:
    """Backdrop + off-canvas/rail <aside> + sticky top strip.

    Shared by the marketing site and the signed-in app shell (imported into
    app/webapp.py) — each caller supplies its own link list, icons, and
    footer content. The drawer/rail mechanics (breakpoint, collapse, focus
    handling) live once, in _SIDEBAR_CSS/_SIDEBAR_JS."""
    return (
        '<div class="sidebar-backdrop" data-sidebar-backdrop></div>'
        f'<div class="sidebar-topbar {mobile_bar_class}">'
        '<button class="sidebar-hamburger" type="button" aria-label="Menu"'
        ' aria-expanded="false" aria-controls="sidebar" data-sidebar-open>'
        "<span></span><span></span></button>"
        '<a class="logo" href="/">Cir<span>via</span></a>'
        + (f'<div class="topbar-extra">{topbar_extra}</div>' if topbar_extra else "")
        + "</div>"
        '<aside class="sidebar" id="sidebar">'
        '<div class="sidebar-head">'
        '<a class="logo sidebar-logo" href="/"><span class="word">Cir<span>via</span></span></a>'
        '<button class="sidebar-collapse" type="button" aria-label="Collapse sidebar"'
        f' data-sidebar-collapse>{_ICONS["chevron"]}</button>'
        '<button class="sidebar-close" type="button" aria-label="Close menu"'
        f' data-sidebar-close>{_ICONS["close"]}</button>'
        "</div>"
        f'<nav class="sidebar-nav">{nav_links_html}</nav>'
        f'<div class="sidebar-foot">{foot_html}</div>'
        "</aside>"
    )


def _nav(active: str) -> str:
    links = ""
    for key, href, label in _NAV_LINKS:
        cls = " active" if key == active else ""
        icon = _ICONS.get(key, "")
        links += (
            f'<a class="side-link{cls}" href="{href}" data-label="{label}">'
            f'<span class="ico">{icon}</span><span class="lbl">{label}</span></a>'
        )
    foot = (
        '<a class="side-link" href="/app" data-auth="signin" data-label="Sign in">'
        f'<span class="ico">{_ICONS["signin"]}</span><span class="lbl">Sign in</span></a>'
        '<a class="side-link btn-cta" href="/app#signup" data-auth="cta" data-label="Get started">'
        f'<span class="ico">{_ICONS["cta"]}</span><span class="lbl">Get started</span></a>'
    )
    return _sidebar_shell(nav_links_html=links, foot_html=foot)


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
      // Straight to the dashboard — /app would flash the sign-in form
      // before redirecting. Signed-out visitors keep the /app href.
      el.setAttribute('href', '/app/dashboard');
    });
  } catch (e) { /* signed-out rendering is the safe default */ }
})();
""" % ref


def _auth_redirect_js() -> str:
    """Send already-signed-in visitors straight to the dashboard.

    Same localStorage session check as ``_auth_nav_js``, but emitted in
    ``<head>`` so the landing page never paints before the redirect. Only
    the home page gets this — signed-in users can still deliberately visit
    pricing/contact/legal pages."""
    supabase_url = get_settings().supabase_url
    if not supabase_url:
        return ""
    ref = urlparse(supabase_url).hostname.split(".")[0]
    return """
(function () {
  try {
    if (location.hash) return; /* keep /#how and /#faq reachable when signed in */
    var raw = localStorage.getItem('sb-%s-auth-token');
    if (!raw) return;
    var s = JSON.parse(raw);
    if (!s || !(s.refresh_token || (s.expires_at && s.expires_at * 1000 > Date.now()))) return;
    location.replace('/app/dashboard');
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
    '<a href="/screener">Valuation screener</a>'
    '<a href="/track-record">Track record</a>'
    '<a href="/sample-digest">Sample digest</a>'
    '<a href="/methodology">Methodology</a>'
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
    "<br><br>Cirvia operates as a sole proprietorship based in "
    "Ontario, Canada. © 2026 Cirvia · Built in Canada</p></div></footer>"
)


def _layout(
    title: str,
    description: str,
    body: str,
    active: str = "",
    path: str = "/",
    extra_jsonld: str = "",
) -> str:
    base = _public_base_url()
    og_image = f"{base}/static/og.png"
    redirect_js = _auth_redirect_js() if path == "/" else ""
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        + f"<script>{_SIDEBAR_PRECOLLAPSE_JS}</script>\n"
        + (f"<script>{redirect_js}</script>\n" if redirect_js else "")
        + f"<title>{title}</title>\n"
        f'<meta name="description" content="{description}">\n'
        + ICON_LINKS
        + f'<link rel="canonical" href="{base}{path}">\n'
        + f'<meta property="og:title" content="{title}">\n'
        + f'<meta property="og:description" content="{description}">\n'
        + '<meta property="og:type" content="website">\n'
        + '<meta property="og:site_name" content="Cirvia">\n'
        + f'<meta property="og:url" content="{base}{path}">\n'
        + f'<meta property="og:image" content="{og_image}">\n'
        + '<meta property="og:image:width" content="1200">\n'
        + '<meta property="og:image:height" content="630">\n'
        + '<meta property="og:image:type" content="image/png">\n'
        + '<meta name="twitter:card" content="summary_large_image">\n'
        + f'<meta name="twitter:image" content="{og_image}">\n'
        + _site_jsonld(base)
        + extra_jsonld
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
        + _SIDEBAR_JS
        + "</script>\n"
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

# Verbatim source for both the visible #faq <details> markup and the
# FAQPage JSON-LD emitted on LANDING_HTML — one list, so they can't drift.
_HOME_FAQ: list[tuple[str, str]] = [
    (
        "Can Cirvia trade for me?",
        "No. Access is strictly read-only. Cirvia cannot place orders or move funds "
        "under any circumstances.",
    ),
    (
        "Is this financial advice?",
        "No. Cirvia is informational only. It explains and contextualizes; it does not "
        "tell you to buy or sell.",
    ),
    (
        "Do the picks actually work?",
        "Judge for yourself. Every daily pick&rsquo;s entry price is frozen at "
        "publication and scored against the S&amp;P 500 on a "
        '<a href="/track-record">public track record</a>, misses stay on the '
        "board. Picks are research with receipts, not recommendations.",
    ),
    (
        "How do I know the AI isn&rsquo;t making things up?",
        "Every number is computed from market data in code: the AI is never "
        "allowed to assert one. Written claims are re-checked by an adversarial "
        "verifier with its own live tools, and anything challenged is demoted or "
        "flagged before you see it.",
    ),
    (
        "Which brokerages work?",
        "Wealthsimple, Questrade, and most major North American brokerages. Connections "
        "are handled by SnapTrade, a trusted service that links millions of brokerage "
        "accounts.",
    ),
    (
        "How is my data protected?",
        "Your password stays with your brokerage, your data is encrypted, and your "
        "information is completely separate from every other user&rsquo;s. See our "
        '<a href="/privacy">Privacy Policy</a>.',
    ),
]

_HOME_BODY = """
<section class="hero">
  <div class="hero-copy">
    <h1 data-hero>The AI analyst that shows its work.</h1>
    <p class="lead" data-hero>Your real holdings, briefed every morning.
    Every number computed, every claim verified, and a public track
    record to prove it.</p>
    <div class="cta-row" data-hero>
      <a class="btn lg" href="/app#signup" data-auth="cta">Get started free</a>
      <a class="quiet" href="/track-record">See the track record</a>
    </div>
  </div>
  <div class="hero-scene">
    <div class="hero-stars" aria-hidden="true"></div>
    <div class="hero-orb" aria-hidden="true"></div>
    <canvas id="aurora" aria-hidden="true"></canvas>
    <div class="float-card fc-chat" data-float aria-hidden="true">
      <p class="fc-q">&ldquo;Why is my NVDA down today?&rdquo;</p>
      <p class="fc-a">A court ruling in a big AI copyright lawsuit hit tech stocks. NVIDIA is your largest holding, so it moved your portfolio the most.</p>
    </div>
    <div class="float-card fc-digest" data-float aria-hidden="true">
      <div class="mock-top"><span class="mock-dot"></span>Morning digest
        <span class="mock-date">9:00 AM</span></div>
      <div class="mock-val"><span class="v" data-tick>$48,214</span>
        <span class="d loss">&minus;0.4% today</span></div>
      <div class="mock-row"><span class="t">VFV</span>
        <span class="n">S&amp;P 500 ETF</span>
        <span class="chg gain">+0.8%</span></div>
      <div class="mock-row"><span class="t">NVDA</span>
        <span class="n">NVIDIA</span>
        <span class="chg loss">&minus;2.1%</span></div>
      <div class="mock-row"><span class="t">ENB</span>
        <span class="n">Enbridge</span>
        <span class="chg gain">+0.6%</span></div>
    </div>
    <div class="float-card fc-alert" data-float aria-hidden="true">
      <span class="mock-alert-k">Macro alert</span>
      <p class="fc-a">Major AI copyright lawsuit ruling shakes tech stocks. NVDA and MSFT in your portfolio are affected.</p>
    </div>
    <div class="float-card fc-verify" data-float aria-hidden="true">
      <span class="mock-alert-k">Verified</span>
      <p class="fc-a">Deep dive complete: <strong>14 of 14 claims</strong> re-checked against live market data. 0 challenged.</p>
    </div>
  </div>
</section>

<section id="features">
  <h2 data-reveal>Signal, not noise.</h2>
  <div class="ledger" data-reveal-group data-stagger="0.45">
    <div class="ledger-row" data-reveal-item>
      <h3>Morning digest</h3>
      <p>Overnight moves, what changed, and what to watch, written for your tickers.
      <a href="/sample-digest">See a sample</a>.</p>
      <span class="meta">Weekdays, your time</span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Model Picks<span class="pro-pill">Pro</span></h3>
      <p>A daily board screened from ~560 S&amp;P 500 and TSX names: quantitative
      factors first, then AI analysts, then a verifier that re-checks every number.
      Scored on a <a href="/track-record">public track record</a>.</p>
      <span class="meta">Daily, pre-market</span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Deep Dives<span class="pro-pill">Pro</span></h3>
      <p>Four research agents (fundamentals, technicals, risk, news)
      investigate a holding in parallel, and an adversarial fact-checker re-tests
      every claim before you see the report.</p>
      <span class="meta">On demand</span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Macro alerts<span class="pro-pill">Pro</span></h3>
      <p>Fed decisions, energy shocks, geopolitics. Only when they touch your holdings.</p>
      <span class="meta">As it happens</span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Risk Lab<span class="pro-pill">Pro</span></h3>
      <p>Monte Carlo futures, risk contribution, and correlation: quant analytics
      on your actual book, explained in plain English.</p>
      <span class="meta">Always current</span>
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

<section id="proof">
  <div class="security-grid">
    <div data-reveal>
      <h2>Never trust a guessed number.</h2>
      <p class="sect-lead">Most AI tools assert; Cirvia proves. Every figure you see
      is computed from market data, and everything the AI writes is re-checked
      before it reaches you.</p>
    </div>
    <ul class="checklist" data-reveal>
      <li>Every number is computed from source data: the AI is never allowed to make one up</li>
      <li>An adversarial critic re-checks each claim with its own live tools</li>
      <li>Challenged picks are demoted or flagged before you see them</li>
      <li>Each pick&rsquo;s entry price is frozen at publication and scored publicly against the S&amp;P 500, misses included</li>
    </ul>
  </div>
  <div class="stat-strip" data-track-stats hidden>
    <div class="stat"><span class="k" data-stat="picks">&ndash;</span>
      <span class="l">picks measured, last 180 days</span></div>
    <div class="stat"><span class="k" data-stat="hit">&ndash;</span>
      <span class="l">beat the S&amp;P 500 over the same span</span></div>
    <div class="stat"><span class="k" data-stat="avg">&ndash;</span>
      <span class="l">average return per pick</span></div>
  </div>
  <p data-reveal style="margin-top:1.6rem;">
    <a class="btn ghost" href="/track-record">See the public track record</a>
  </p>
  <script>
  (function () {
    fetch('/stocks/picks/track-record?days=180')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        /* below ~30 measured picks the stats are noise, not signal — the
           strip stays hidden and the track-record page carries the detail */
        if (!d || !d.available || !d.summary || !(d.summary.measured >= 30)) return;
        var s = d.summary;
        function put(k, v) {
          var el = document.querySelector('[data-stat="' + k + '"]');
          if (el && v != null) el.textContent = v;
        }
        put('picks', s.measured);
        put('hit', s.hit_rate_pct != null ? s.hit_rate_pct + '%' : null);
        put('avg', s.avg_return_pct != null
          ? (s.avg_return_pct > 0 ? '+' : '') + s.avg_return_pct + '%' : null);
        document.querySelector('[data-track-stats]').hidden = false;
      })
      .catch(function () { /* stat strip simply stays hidden */ });
  })();
  </script>
</section>

<section id="showcase">
  <h2 data-reveal>Ask about your investments.</h2>
  <p class="sect-lead" data-reveal>Every answer starts from the positions you
  actually hold.</p>
  <div class="show-panel chat-demo" data-chat aria-hidden="true">
    <div class="mock-top"><span class="mock-dot"></span>Chat</div>
    <div class="bubble user">Why is my NVDA down today?</div>
    <div class="bubble bot">A court ruled against a major AI company in a copyright
    lawsuit, and tech stocks sold off. NVIDIA is your largest holding, so it pulled
    your portfolio down the most today.</div>
    <div class="bubble user">Anything to watch this week?</div>
    <div class="bubble bot">Two things: Apple reports earnings Thursday after
    close, and the Bank of Canada rate decision lands Thursday morning.</div>
  </div>
</section>

<section id="how">
  <h2 data-reveal>Connected in three minutes.</h2>
  <div class="steps" data-reveal-group>
    <div class="step" data-reveal-item><div class="num"></div><div><h3>Connect your brokerage</h3>
    <p>Pick your brokerage (Wealthsimple, Questrade, and more) and log in on a secure
    connection page, the same way you&rsquo;d link your bank to a budgeting app.
    We never see your password.</p></div></div>
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
      <li>We can only view your investments, never touch them</li>
      <li>Your brokerage password stays with your bank, we never see it</li>
      <li>Everything is encrypted and stored securely</li>
      <li>Your data is yours, no one else can ever see it</li>
    </ul>
  </div>
</section>

<section id="pricing-teaser">
  <h2 data-reveal>Start with a week of Pro, free.</h2>
  <p class="sect-lead" data-reveal>Every new account gets the full Pro experience for
  7 days, no card required. Read-only on every plan; your brokerage
  password never leaves your bank.</p>
  <div class="plans" style="margin-left:auto;margin-right:auto;" data-reveal-group>
    <div class="plan" data-reveal-item>
      <div class="plan-tag">Free</div>
      <div class="price">$0<span class="per"> /mo</span></div>
      <ul>
        <li>1 connected account</li>
        <li>Weekly digest on up to 3 holdings</li>
        <li>3 chat questions per week</li>
      </ul>
      <a class="btn ghost" href="/app#signup">Start free</a>
    </div>
    <div class="plan featured" data-reveal-item>
      <div class="plan-tag">Pro</div>
      <div class="price">$20<span class="per"> /mo CAD</span></div>
      <p class="price-note">or $160/yr CAD, 4 months free.</p>
      <ul>
        <li>Daily weekday digest across all holdings</li>
        <li>Model Picks: the daily verified board, with its
        <a href="/track-record">public track record</a></li>
        <li>Risk Lab: Monte Carlo, risk contribution, correlation</li>
        <li>Macro alerts when the world moves</li>
      </ul>
      <a class="btn ghost" href="/app#signup" data-auth="cta">Get started free</a>
      <p class="price-note" style="margin-top:0.75rem;">New here? Signing up
      starts a 7-day Pro trial, no card required.</p>
    </div>
  </div>
  <p data-reveal style="margin-top:1.4rem;"><a class="quiet" href="/pricing">Pricing</a></p>
</section>

<section id="faq">
  <h2 data-reveal>Questions</h2>
  <div class="faq" data-reveal-group>
%%HOME_FAQ%%
  </div>
</section>

<div class="cta-final" data-reveal>
  <h2>Know your portfolio by 9:00.</h2>
  <p>Every new account starts with 7 days of full Pro, no card required.
  Connected in under three minutes.</p>
  <a class="btn lg" href="/app#signup" data-auth="cta">Get started free</a>
</div>
"""
# _HOME_BODY is a plain (non-f) string because #proof embeds a <script> full
# of JS braces that an f-string would need double-escaped; a placeholder +
# .replace() sidesteps that entirely for the one spot that needs interpolation.
_HOME_BODY = _HOME_BODY.replace("%%HOME_FAQ%%", _faq_html(_HOME_FAQ))

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

_METHODOLOGY_BODY = """
<div class="prose">
  <h1>Methodology</h1>
  <p class="updated">How the numbers are made, how they're checked, and where they fall short.</p>

  <p>Cirvia's design rule is simple: <strong>every number you see is computed in
  code from market data; the AI only narrates.</strong> This page explains what
  that means for the daily Model Picks, the public track record, and the
  portfolio analytics, including the limitations we haven't fixed yet.</p>

  <h2>How the daily picks are made</h2>
  <p><strong>1. Universe.</strong> Roughly 560 names: the S&amp;P 500 plus the TSX 60.
  Membership is recorded as dated history: when a company leaves the index or
  delists, its record stays and its prices keep updating while any published pick
  references it, so failures remain visible.</p>
  <p><strong>2. Quantitative screen.</strong> A pure-math factor screen ranks the
  universe before any AI is involved: value, quality, growth, momentum (12-months
  skipping the last month), analyst upside (shrunk toward zero when coverage is
  thin), and low risk. Metrics are scored relative to each stock's industry
  peers — falling back to its sector, then the full tracked universe, when
  there aren't enough industry peers — using robust statistics (median and
  MAD, not mean and standard deviation, because financial ratios have fat
  tails). Names with stale prices or missing data are
  excluded with a recorded reason; nothing is imputed.</p>
  <p><strong>3. AI analysts, on a leash.</strong> Each top candidate gets an AI
  analyst that may only cite numbers from a fact sheet computed in step 2. Its
  output is then machine-checked: any cited figure that doesn't match the fact
  sheet is repaired to the canonical value or dropped.</p>
  <p><strong>4. Adversarial verification.</strong> A separate AI critic re-checks
  the most load-bearing claims using its own live data tools and marks each one
  verified or challenged. A pick with two or more challenged claims is demoted
  below every clean pick. Confidence scores are computed in code from screen
  rank, data coverage, and verification results; the AI is never asked how
  confident it feels.</p>

  <h2>How the track record is measured</h2>
  <ul>
    <li><strong>Entry prices freeze at publication.</strong> Each pick records the
    last market close before its pre-market publication, and that number is never
    revised.</li>
    <li><strong>Returns are total returns.</strong> Performance is computed from
    dividend- and split-adjusted closes drawn from one consistent price series,
    from the pick's publication bar to the latest close, fresh on every page load.</li>
    <li><strong>The benchmark includes dividends.</strong> Picks are compared
    against SPY's adjusted close (an S&amp;P 500 total-return proxy) over each
    pick's identical span; a price-only index would flatter us by the
    index's dividend yield.</li>
    <li><strong>Cohorts, not cherry-picks.</strong> Because a good pick can stay on
    the board for weeks, per-pick averages over-count persistent names. The honest
    headline numbers group picks into daily cohorts measured only at fully-elapsed
    horizons, plus a simulated portfolio that buys each day's top five
    equal-weighted and rebalances when the board changes.</li>
    <li><strong>Misses stay on the board.</strong> Nothing is deleted,
    including picks on companies that later fell, were removed from their index,
    or delisted.</li>
    <li><strong>Small samples stay quiet.</strong> Headline stats appear only once
    at least 30 picks have fully-measured outcomes; below that, averages are noise.</li>
    <li><strong>Inputs are archived nightly.</strong> Every evening we store a
    dated, hashed snapshot of each stock's fundamentals. From the first snapshot
    onward, any pick can be re-derived from data timestamped before the pick was
    published.</li>
  </ul>

  <h2>Portfolio analytics</h2>
  <p>The Risk Lab and chat answers use the same discipline: returns are built from
  adjusted closes aligned across markets (Canadian and US holidays differ, so only
  common trading days are compared); portfolio risk uses a shrunk covariance
  estimate (Ledoit-Wolf) rather than raw sample correlations; downside estimates
  report Value-at-Risk several ways (including a fat-tail adjustment) and say
  which is which; Monte Carlo projections use zero drift by default: the
  fan shows risk, not a forecast. All of it is unit-tested against closed-form
  results.</p>

  <h2>How the <a href="/screener">valuation screener</a> works</h2>
  <p>Every stock Cirvia tracks gets a plain verdict: <strong>Undervalued</strong>,
  <strong>Fairly Valued</strong>, or <strong>Expensive</strong>. Here is exactly what
  that measures, and what it deliberately doesn't claim yet.</p>
  <p><strong>It compares a stock to its closest peers, today.</strong> Each verdict is
  built from the same value factor the daily screen uses above: trailing/forward P/E,
  PEG, price/sales, price/book, EV/EBITDA, and price/FCF, each normalized against the
  stock's industry peers — a narrower, more like-for-like group than its broad GICS
  sector — using the same robust (median/MAD) statistics, then averaged into
  one score. A stock needs at least two of those seven metrics to be scored at all;
  fewer than that, and the verdict reads &ldquo;Not enough data&rdquo; rather than
  guessing. When a stock's industry doesn't have enough scored peers to compare
  against reliably, the comparison widens to its sector, and if even that's too
  thin, to the whole tracked universe; the evidence table always says which lens
  was used.</p>
  <p><strong>It does not yet compare a stock to its own history.</strong> A "is this
  cheap for <em>this stock</em>, historically" verdict needs years of point-in-time
  valuation snapshots. Cirvia only started archiving those nightly snapshots recently,
  so there isn't yet a decade (or even a full year) of a stock's own
  history to compare against. Rather than fabricate that comparison, today's verdict
  only measures the peer-relative lens. Once enough snapshot history accrues, a
  second "vs. its own history" lens will be added and disclosed with the exact window
  it's built from, not a fixed claim we can't back up.</p>
  <p><strong>The verdict is free; the numbers behind it are Pro.</strong> Anyone can
  browse the <a href="/screener">full grid</a> with no account. On a stock's own page,
  the per-metric evidence (this stock's ratio vs. its peer median) is part of
  Cirvia&nbsp;Pro, the same as the rest of the fact sheet it's built from.</p>

  <h2>Limitations, honestly</h2>
  <ul>
    <li><strong>Data source.</strong> Prices and fundamentals come from free/retail
    market-data services, not an institutional vendor. Fields are occasionally
    revised upstream; the nightly snapshots bound this going forward but cannot
    repair history before they began.</li>
    <li><strong>Benchmark mismatch.</strong> SPY is a US total-return proxy while
    the pick universe includes TSX names; a blended benchmark is planned.</li>
    <li><strong>Factor weights are judgment.</strong> The screen's factor weights
    come from the academic literature and our judgment; they have not yet been
    validated out-of-sample on our own data. A walk-forward validation harness is
    planned, and its results will be published here.</li>
    <li><strong>The simulated portfolio ignores costs.</strong> Spreads and
    commissions are not netted from the top-5 simulation; it is a research
    measure, not a trading result.</li>
    <li><strong>Short history.</strong> The track record is young. Judge it by its
    rules and its transparency until it has the sample size to be judged by its
    numbers.</li>
  </ul>

  <p>Cirvia is informational only: research with receipts, not
  recommendations, and never personalized advice to buy or sell a security.
  Past performance does not guarantee future results.</p>
</div>
"""


_PRIVACY_BODY = f"""
<div class="prose">
  <h1>Privacy Policy</h1>
  <p class="updated">Last updated: {LAST_UPDATED}</p>

  <p>Cirvia ("Cirvia", "we", "us", or "our") is operated as a sole
  proprietorship based in Ontario, Canada, and provides an AI portfolio analysis service for
  individual investors. This Privacy Policy explains what personal information we collect, why we
  collect it, how we use, share, and protect it, and the choices and rights you have. It is
  written to align with Canada's <em>Personal Information Protection and Electronic Documents Act</em>
  (PIPEDA). By creating an account or using Cirvia, you consent to the collection, use, and
  disclosure of your information as described here.</p>

  <h2>1. Accountability</h2>
  <p>Cirvia is responsible for personal information under its control. Questions,
  requests, and privacy complaints can be directed to our privacy contact at
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
    <li>Your brokerage username, password, or other login credentials: you authenticate directly
    with your brokerage inside SnapTrade's secure portal; those credentials never pass through or
    reach Cirvia.</li>
    <li>Payment card details, if and when paid plans are offered: these would be handled directly
    by a third-party payment processor, not stored by Cirvia.</li>
  </ul>

  <h2>4. Purposes and how we use your information</h2>
  <ul>
    <li>To provide the service: syncing your holdings, generating your daily digest and macro
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
    <li><strong>SnapTrade</strong>: secure brokerage connectivity (read-only holdings).</li>
    <li><strong>Supabase</strong>: authentication and database hosting.</li>
    <li><strong>Anthropic</strong>: the AI model that generates analysis (we send relevant
    portfolio context and public news; we do not send your brokerage credentials).</li>
    <li><strong>Finnhub and other market-data providers</strong>: public market and news data.</li>
    <li><strong>Railway</strong>: application hosting.</li>
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
  "we", "us"), operated as a sole proprietorship based in Ontario, Canada,
  governing your access to and use of the Cirvia website, application, and services (collectively,
  the "Service"). By accessing or using the Service, you agree to these Terms and to our
  <a href="/privacy">Privacy Policy</a>. If you do not agree, do not use the Service.</p>

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
  <p>Information provided by the Service, including holdings, prices, news, and AI-generated analysis,
  may be delayed, incomplete, or inaccurate, and may contain errors. Do not rely on it as the sole
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

# Verbatim source for both the visible #pricing-faq <details> markup and the
# FAQPage JSON-LD emitted on PRICING_HTML — one list, so they can't drift.
_PRICING_FAQ: list[tuple[str, str]] = [
    (
        "Can I cancel anytime?",
        "Yes. Cancel whenever you like from Settings &rarr; Manage billing; your Pro "
        "features stay active until the end of the current billing period.",
    ),
    (
        "Is there a yearly option?",
        "Yes. Pro is $20/mo CAD or $160/yr CAD, which works out to four months free "
        "versus paying monthly.",
    ),
    (
        "How does the free trial work?",
        "Every new account gets 7 days of full Pro (daily digests, macro "
        "alerts, and Pro chat limits) with no card on file. When it ends, your "
        "digests pause until you choose: upgrade to Pro, or continue on Free. Nothing "
        "is ever charged automatically.",
    ),
    (
        "What happens on the Free plan?",
        "You keep one connected account, a weekly digest on up to three holdings, and "
        "three chat questions a week. Free, indefinitely.",
    ),
    (
        "Do you offer refunds?",
        "Reach out and we'll make it right. Email us at "
        f'<a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.',
    ),
]


def _pricing_product_jsonld(base: str) -> dict:
    """Product/Offer schema for the Pro plan. Deliberately no aggregateRating
    or review: there are no testimonials on this site to source one from, and
    fabricating one would break the same honesty posture the product sells."""
    return {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Cirvia Pro",
        "description": (
            "Daily verified portfolio digest, Model Picks with a public track "
            "record, Deep Dive research, Risk Lab, and macro alerts."
        ),
        "brand": {"@type": "Brand", "name": "Cirvia"},
        "offers": [
            {
                "@type": "Offer",
                "name": "Cirvia Pro Monthly",
                "price": "20.00",
                "priceCurrency": "CAD",
                "url": f"{base}/pricing",
                "availability": "https://schema.org/InStock",
            },
            {
                "@type": "Offer",
                "name": "Cirvia Pro Annual",
                "price": "160.00",
                "priceCurrency": "CAD",
                "url": f"{base}/pricing",
                "availability": "https://schema.org/InStock",
            },
        ],
    }


_PRICING_BODY = f"""
<section class="hero" style="padding-bottom:0;">
  <div class="hero-copy">
    <h1 data-hero>Start with a week of Pro, free.</h1>
    <p class="lead" data-hero>Every new account gets the full Pro experience for
    7 days, no card required. Read-only on every plan; your brokerage
    password never leaves your bank.</p>
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
        <li>3 chat questions per week</li>
        <li>1 Deep Dive research report per month</li>
        <li>Watchlist for up to 3 tickers</li>
      </ul>
      <a class="btn ghost" href="/app#signup">Start free</a>
    </div>
    <div class="plan featured" data-reveal-item>
      <div class="plan-tag">Pro</div>
      <div class="price">$20<span class="per"> /mo CAD</span></div>
      <p class="price-note">or $160/yr CAD, 4 months free.</p>
      <ul>
        <li>Unlimited connected accounts</li>
        <li>Daily weekday digest across all holdings</li>
        <li>Model Picks: the daily verified board, with its
        <a href="/track-record">public track record</a></li>
        <li>Deep Dive research reports, 2 per week</li>
        <li>Risk Lab: Monte Carlo, risk contribution, correlation</li>
        <li>Macro alerts when the world moves</li>
        <li>Price-anomaly alerts on unusual moves</li>
        <li>10 chat questions per day</li>
        <li>Watchlist for up to 30 tickers</li>
      </ul>
      <a class="btn ghost" href="/app/settings?billing=upgrade">Go Pro</a>
      <p class="price-note" style="margin-top:0.75rem;">New here? Signing up
      starts a 7-day Pro trial, no card required.</p>
    </div>
  </div>
</section>

<section id="pricing-faq">
  <h2 data-reveal>Questions about plans</h2>
  <div class="faq" data-reveal-group>
{_faq_html(_PRICING_FAQ)}
  </div>
</section>

<div class="cta-final" data-reveal>
  <h2>Ready when you are.</h2>
  <p>Start free. Upgrade any time.</p>
  <a class="btn lg" href="/app#signup" data-auth="cta">Get started free</a>
</div>
"""


# --------------------------------------------------------------------------
# Track record (public proof page — body rendered per-request from live data)
# --------------------------------------------------------------------------

_TRACK_RECORD_INTRO = """
<section class="hero" style="padding-bottom:0;">
  <div class="hero-copy">
    <h1 data-hero>Every pick. Priced honestly.</h1>
    <p class="lead" data-hero>Each day&rsquo;s Model Picks are published with a frozen
    entry price and scored here against the S&amp;P 500 over the identical span.
    Misses stay on the board, nothing is ever deleted.</p>
  </div>
</section>
"""

_TRACK_RECORD_METHOD = """
<section>
  <h2 data-reveal>How this is measured</h2>
  <div class="steps" data-reveal-group>
    <div class="step" data-reveal-item><div class="num"></div><div><h3>Entry price is frozen</h3>
    <p>The moment a pick is published, its entry price is recorded and never revised.</p></div></div>
    <div class="step" data-reveal-item><div class="num"></div><div><h3>Scored at read time</h3>
    <p>Returns are total returns (dividend- and split-adjusted) computed fresh
    from publication to the latest stored close each time this page loads, not curated
    snapshots.</p></div></div>
    <div class="step" data-reveal-item><div class="num"></div><div><h3>Benchmarked, same span</h3>
    <p>Each pick is compared against the S&amp;P 500 with dividends reinvested, from its
    publication date to now. Beating a bull market is the bar, not just going up.</p></div></div>
  </div>
  <p class="sect-lead" style="margin-top:1.6rem;">Picks are research with receipts, not
  recommendations. Past performance does not guarantee future results.
  <a href="/methodology">Read the full methodology</a>, limitations included.</p>
</section>

<div class="cta-final" data-reveal>
  <h2>See today&rsquo;s board with your own portfolio.</h2>
  <p>Every new account starts with 7 days of full Pro, no card required.</p>
  <a class="btn lg" href="/app#signup" data-auth="cta">Get started free</a>
</div>
"""


def _signed_pct(value: float | None) -> str:
    if value is None:
        return "&ndash;"
    return f"{'+' if value > 0 else ''}{value:.2f}%"


def track_record_html(payload: dict) -> str:
    """The public /track-record page, rendered from the same payload the
    /stocks/picks/track-record JSON route returns."""
    summary = payload.get("summary") or {}
    entries = payload.get("entries") or []
    if not payload.get("available") or not entries:
        body = _TRACK_RECORD_INTRO + """
<section>
  <div class="callout" data-reveal>The track record is measured from live pick data and
  builds day by day as picks season. Check back shortly: every pick published from
  day one will appear here, wins and misses alike.</div>
</section>
""" + _TRACK_RECORD_METHOD
        return _layout(
            "Pick track record | Cirvia",
            "The public, honestly-priced track record of Cirvia's daily Model Picks, "
            "benchmarked against the S&P 500.",
            body,
            active="track",
            path="/track-record",
        )

    stats = ""
    if summary.get("measured"):
        hit = (
            f"{summary['hit_rate_pct']}%" if summary.get("hit_rate_pct") is not None
            else "&ndash;"
        )
        stats = f"""
  <div class="stat-strip" data-reveal>
    <div class="stat"><span class="k">{summary["measured"]}</span>
      <span class="l">picks measured</span></div>
    <div class="stat"><span class="k">{hit}</span>
      <span class="l">beat the S&amp;P 500 over the same span</span></div>
    <div class="stat"><span class="k">{_signed_pct(summary.get("avg_return_pct"))}</span>
      <span class="l">average return per pick</span></div>
  </div>"""

    sim_stats = (payload.get("simulated") or {}).get("stats") or None
    simulated = ""
    if sim_stats:
        simulated = f"""
  <div class="stat-strip" data-reveal style="margin-top:1rem;">
    <div class="stat"><span class="k">{_signed_pct(sim_stats.get("total_return_pct"))}</span>
      <span class="l">top-5 portfolio, bought each run</span></div>
    <div class="stat"><span class="k">{_signed_pct(sim_stats.get("benchmark_return_pct"))}</span>
      <span class="l">S&amp;P 500 over the same days</span></div>
    <div class="stat"><span class="k">{_signed_pct(sim_stats.get("max_drawdown_pct"))}</span>
      <span class="l">worst drawdown along the way</span></div>
  </div>
  <p style="color:var(--ink-3);font-size:0.85rem;margin-top:0.6rem;">The simulated
  portfolio buys each day&rsquo;s top-5 picks equal-weighted at the prior close and
  rebalances when the board changes. Before transaction costs: a research
  measure, not a trading result.</p>"""

    rows = ""
    for e in entries:
        entry_price = (
            f"${e['entry_price']:,.2f}" if e.get("entry_price") is not None else "&ndash;"
        )
        ret = e.get("return_pct")
        bench = e.get("benchmark_return_pct")
        ret_cls = "gain" if (ret or 0) > 0 else ("loss" if (ret or 0) < 0 else "")
        beat = "&ndash;"
        if ret is not None and bench is not None:
            beat = "&#10003;" if ret > bench else "&#8211;"
        rows += f"""
      <tr>
        <td class="num">{e["run_date"]}</td>
        <td class="tick">{e["ticker"]}</td>
        <td class="num">{e.get("rank") or "&ndash;"}</td>
        <td class="num">{entry_price}</td>
        <td class="num {ret_cls}">{_signed_pct(ret)}</td>
        <td class="num">{_signed_pct(bench)}</td>
        <td class="num">{beat}</td>
      </tr>"""

    body = f"""{_TRACK_RECORD_INTRO}
<section style="padding-top:2.5rem;">
  {stats}
  {simulated}
  <div class="table-scroll" data-reveal>
    <table class="tr-table">
      <thead><tr>
        <th>Published</th><th>Ticker</th><th>Rank</th><th>Entry</th>
        <th style="text-align:right;">Return</th>
        <th style="text-align:right;">S&amp;P 500, same span</th>
        <th style="text-align:right;">Beat</th>
      </tr></thead>
      <tbody>{rows}
      </tbody>
    </table>
  </div>
  <p style="color:var(--ink-3);font-size:0.85rem;margin-top:0.9rem;">Returns are total
  returns (dividends and splits included), computed from each pick&rsquo;s last close
  before publication to the latest stored close, at the moment this page loads. The
  S&amp;P 500 column is SPY total return over the identical span.</p>
</section>
{_TRACK_RECORD_METHOD}"""
    return _layout(
        "Pick track record | Cirvia",
        "The public, honestly-priced track record of Cirvia's daily Model Picks, "
        "benchmarked against the S&P 500.",
        body,
        active="track",
        path="/track-record",
    )


# --------------------------------------------------------------------------
# Valuation screener (/screener) — public "cheap or expensive" grid, the
# no-signup browse hook. Server-rendered from the same JSON
# /stocks/valuations returns; sort/search run client-side over the ~560
# already-rendered rows, no second request. See app/quant/valuation.py for
# what "verdict" actually measures (industry-relative, falling back to
# sector then the whole universe — deliberately not claiming a 10-year
# history Cirvia doesn't have yet).
# --------------------------------------------------------------------------

_SCREENER_INTRO = """
<section class="hero" style="padding-bottom:1.5rem;">
  <div class="hero-copy" style="max-width:52rem;">
    <h1 data-hero>Is this stock cheap or expensive?</h1>
    <p class="lead" data-hero>A verdict for every stock Cirvia tracks, computed against
    its closest industry peers today (falling back to sector, then the market, when
    there aren't enough industry peers), not a vague label. Every verdict comes with
    the numbers behind it: <a href="/methodology">see the methodology</a>,
    limitations included.</p>
  </div>
</section>
"""

_SCREENER_METHOD = """
<section id="screener-method" style="padding-top:0.5rem;">
  <div class="callout" data-reveal>
  <strong>What this measures today:</strong> each verdict compares a stock's valuation
  multiples (P/E, P/S, P/B, EV/EBITDA, price/FCF, PEG) to its industry peers (falling
  back to sector, then the whole tracked universe, when there aren't enough
  industry-level peers), using a robust (outlier-resistant) statistical comparison, not
  a raw average. The Sector column below is general company info, not the peer group
  used — verdicts are computed against each stock's narrower industry, so two stocks in
  the same broad sector can get different verdicts; see a stock's own page for the exact
  peer group. It does <strong>not</strong> yet compare a stock to its own history: that
  needs years of daily snapshots Cirvia only started collecting recently, and a verdict
  here will say so honestly rather than fake a decade it doesn't have.
  <a href="/methodology">Full methodology</a>.
  </div>
</section>
"""


def _fmt_cap(v: float | None) -> str:
    if v is None:
        return "&ndash;"
    a = abs(v)
    if a >= 1e12:
        return f"${v / 1e12:.2f}T"
    if a >= 1e9:
        return f"${v / 1e9:.2f}B"
    if a >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:,.0f}"


_VERDICT_CLASS = {
    "Undervalued": "vd-under",
    "Expensive": "vd-over",
    "Fairly Valued": "vd-fair",
}


def _verdict_badge(verdict: str) -> str:
    cls = _VERDICT_CLASS.get(verdict, "vd-none")
    return f'<span class="vd-badge {cls}">{verdict}</span>'


_SCREENER_JS = """
(function () {
  var input = document.getElementById('scr-search');
  var tbody = document.getElementById('scr-body');
  if (!input || !tbody) return;
  var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
  var countEl = document.getElementById('scr-count');

  function applyFilter() {
    var q = input.value.trim().toLowerCase();
    var shown = 0;
    rows.forEach(function (r) {
      var hit = !q || r.dataset.ticker.indexOf(q) !== -1 || r.dataset.name.indexOf(q) !== -1;
      r.hidden = !hit;
      if (hit) shown++;
    });
    if (countEl) countEl.textContent = shown + ' of ' + rows.length + ' shown';
  }
  input.addEventListener('input', applyFilter);
  applyFilter();

  var sortState = { key: null, dir: 1 };
  document.querySelectorAll('th[data-sort]').forEach(function (th) {
    th.addEventListener('click', function () {
      var key = th.dataset.sort;
      sortState.dir = sortState.key === key ? -sortState.dir : 1;
      sortState.key = key;
      document.querySelectorAll('th[data-sort]').forEach(function (t) {
        t.classList.remove('asc', 'desc');
      });
      th.classList.add(sortState.dir === 1 ? 'asc' : 'desc');
      var numeric = key === 'cap' || key === 'price';
      rows.sort(function (a, b) {
        var av = a.dataset[key] || '', bv = b.dataset[key] || '';
        if (numeric) {
          av = av === '' ? -Infinity : parseFloat(av);
          bv = bv === '' ? -Infinity : parseFloat(bv);
          return (av - bv) * sortState.dir;
        }
        return av.localeCompare(bv) * sortState.dir;
      });
      rows.forEach(function (r) { tbody.appendChild(r); });
    });
  });
})();
"""


def screener_html(payload: dict) -> str:
    """The public /screener page, rendered from the same JSON
    /stocks/valuations returns."""
    rows = payload.get("rows") or []
    universe = payload.get("universe") or {}
    universe_size = universe.get("size")
    coverage_note = (
        f"Covers ~{universe_size} US and Canadian large caps "
        "(S&amp;P 500 + TSX 60) today." if universe_size else ""
    )

    if not rows:
        body = _SCREENER_INTRO + f"""
<section>
  <div class="callout" data-reveal>Verdicts are computed nightly and build up as the
  screen runs. Check back shortly. {coverage_note}</div>
</section>
""" + _SCREENER_METHOD
        return _layout(
            "Stock valuation screener | Cirvia",
            "Is this stock cheap or expensive? A peer-relative verdict, with the "
            "numbers behind it, for every stock Cirvia tracks.",
            body,
            active="screener",
            path="/screener",
        )

    trs = ""
    for r in sorted(rows, key=lambda r: (r.get("market_cap") or 0), reverse=True):
        cap = r.get("market_cap")
        price = r.get("last_price")
        trs += f"""
      <tr data-ticker="{(r.get("ticker") or "").lower()}"
          data-name="{(r.get("name") or "").lower()}"
          data-sector="{(r.get("sector") or "").lower()}"
          data-cap="{cap if cap is not None else ""}"
          data-price="{price if price is not None else ""}"
          data-verdict="{r.get("verdict") or ""}">
        <td class="tick"><a href="/app/stock/{r.get("ticker")}">{r.get("ticker")}</a></td>
        <td>{r.get("name") or "&ndash;"}</td>
        <td>{r.get("sector") or "&ndash;"}</td>
        <td class="num">{_fmt_cap(cap)}</td>
        <td class="num">{f"${price:,.2f}" if price is not None else "&ndash;"}</td>
        <td>{_verdict_badge(r.get("verdict") or "Not enough data")}</td>
      </tr>"""

    body = f"""{_SCREENER_INTRO}
<section style="padding-top:0.5rem;">
  <div class="scr-controls" data-reveal>
    <input class="scr-search" id="scr-search" type="text"
           placeholder="Search by ticker or company name&hellip;">
    <span class="scr-count" id="scr-count"></span>
  </div>
  <p style="color:var(--ink-3);font-size:0.85rem;margin-top:0.6rem;">{coverage_note}
  As of {payload.get("as_of") or "&ndash;"}.</p>
  <div class="table-scroll" data-reveal>
    <table class="tr-table scr-table">
      <thead><tr>
        <th data-sort="ticker">Ticker</th>
        <th data-sort="name">Company</th>
        <th data-sort="sector">Sector</th>
        <th data-sort="cap" style="text-align:right;">Market cap</th>
        <th data-sort="price" style="text-align:right;">Price</th>
        <th data-sort="verdict">Verdict</th>
      </tr></thead>
      <tbody id="scr-body">{trs}
      </tbody>
    </table>
  </div>
</section>
{_SCREENER_METHOD}
<script>{_SCREENER_JS}</script>"""
    return _layout(
        "Stock valuation screener | Cirvia",
        "Is this stock cheap or expensive? A peer-relative verdict, with the "
        "numbers behind it, for every stock Cirvia tracks.",
        body,
        active="screener",
        path="/screener",
    )


# --------------------------------------------------------------------------
# Sample digest (public proof page — static, mirrors the real digest format)
# --------------------------------------------------------------------------

_SAMPLE_DIGEST_BODY = """
<section class="hero" style="padding-bottom:0;">
  <div class="hero-copy">
    <h1 data-hero>A morning digest, up close.</h1>
    <p class="lead" data-hero>This is what lands on your phone at 9:00, written
    fresh each morning from your actual holdings. The sample below covers an
    illustrative portfolio.</p>
  </div>
</section>

<div class="show-panel" data-hero style="max-width:640px;margin:2.5rem auto 0;">
  <div class="mock-top"><span class="mock-dot"></span>Morning digest, sample
    <span class="mock-date">9:00 AM</span></div>
  <div class="dg">
    <p class="dg-line"><strong>PORTFOLIO:</strong> &minus;0.6% today (&minus;$318)</p>
    <p class="dg-label">TOP RISK</p>
    <p>Rate-sensitive names are 38% of the book ahead of Thursday&rsquo;s Bank of
    Canada decision; ENB and TD would feel a hawkish surprise most.</p>
    <p class="dg-label">NOTABLE</p>
    <ul>
      <li>NVDA &minus;2.1%, extending yesterday&rsquo;s slide after the AI copyright
      ruling; still the largest single-name exposure at 18%.</li>
      <li>VFV +0.8% with the S&amp;P 500&rsquo;s rebound: the index sleeve did
      the lifting today.</li>
      <li>TD upgraded at a major bank on credit normalization.</li>
    </ul>
    <p class="dg-label">WATCH TODAY</p>
    <p>Bank of Canada rate decision, 9:45 AM ET, direct read-through to ENB,
    TD, and the REIT sleeve.</p>
    <p class="dg-label">HOLDINGS <span class="pro-pill">Pro</span></p>
    <div class="dg-holding"><span class="h">NVDA &middot; $9,120 &middot; 18.2% of book &middot; &minus;2.1% today</span>
      <p>Extends yesterday&rsquo;s slide on the copyright ruling; no new company-specific news this morning.</p></div>
    <div class="dg-holding"><span class="h">VFV &middot; $14,480 &middot; 28.9% of book &middot; +0.8% today</span>
      <p>Tracking the S&amp;P 500&rsquo;s rebound; nothing name-specific.</p></div>
    <div class="dg-holding"><span class="h">TD &middot; $6,240 &middot; 12.4% of book &middot; +1.2% today</span>
      <p>Upgraded this morning on credit normalization; watch the BoC decision Thursday.</p></div>
    <div class="dg-holding"><span class="h">QUIET: 5 others little changed; largest ENB &minus;0.3%.</span></div>
  </div>
</div>

<section>
  <h2 data-reveal>What you&rsquo;re looking at</h2>
  <div class="ledger" data-reveal-group>
    <div class="ledger-row" data-reveal-item>
      <h3>Written for your book</h3>
      <p>The digest is generated each morning from your synced holdings, not a
      generic market newsletter with your name on it.</p>
      <span class="meta"></span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>One risk, called out</h3>
      <p>TOP RISK is the single most important thing in your portfolio today. On a quiet
      day it names your biggest exposure; it never invents drama.</p>
      <span class="meta"></span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Numbers you can trust</h3>
      <p>Every figure is computed from market data before the AI writes a word. It
      explains the numbers; it is never allowed to make them up.</p>
      <span class="meta"></span>
    </div>
    <div class="ledger-row" data-reveal-item>
      <h3>Tuned to you</h3>
      <p>Your investor profile (horizon, goals, experience) sets the lookback
      window and what counts as worth mentioning.</p>
      <span class="meta"></span>
    </div>
  </div>
</section>

<div class="cta-final" data-reveal>
  <h2>Tomorrow morning, this could be your portfolio.</h2>
  <p>Every new account starts with 7 days of full Pro, no card required.</p>
  <a class="btn lg" href="/app#signup" data-auth="cta">Get started free</a>
</div>
"""

SAMPLE_DIGEST_HTML = _layout(
    "Sample morning digest | Cirvia",
    "See exactly what Cirvia's morning digest looks like: portfolio move, top risk, "
    "notable items, and what to watch, written from your real holdings.",
    _SAMPLE_DIGEST_BODY,
    path="/sample-digest",
)


LANDING_HTML = _layout(
    "Cirvia | AI portfolio analyst for Canadian investors",
    "The AI analyst that shows its work: a daily brief on your real holdings, verified "
    "stock research with a public track record, and on-demand answers. Read-only. "
    "No trade execution.",
    _HOME_BODY,
    active="home",
    path="/",
    extra_jsonld=_jsonld_script(_faq_jsonld(_HOME_FAQ)),
)

PRICING_HTML = _layout(
    "Pricing | Cirvia",
    "Cirvia pricing: start free with a weekly digest and chat questions, or go Pro at "
    "$20/mo CAD ($160/yr) for daily digests, verified Model Picks with a public track "
    "record, Deep Dive reports, Risk Lab, and macro alerts.",
    _PRICING_BODY,
    active="pricing",
    path="/pricing",
    extra_jsonld=(
        _jsonld_script(_faq_jsonld(_PRICING_FAQ))
        + _jsonld_script(_pricing_product_jsonld(_public_base_url()))
    ),
)

CONTACT_HTML = _layout(
    "Contact | Cirvia",
    "Get in touch with Cirvia for early access, support, privacy requests, or partnerships.",
    _CONTACT_BODY,
    active="contact",
    path="/contact",
)

METHODOLOGY_HTML = _layout(
    "Methodology | Cirvia",
    "How Cirvia's daily picks are made and verified, how the public track record "
    "is measured, and the limitations we haven't fixed yet.",
    _METHODOLOGY_BODY,
    path="/methodology",
)

PRIVACY_HTML = _layout(
    "Privacy Policy | Cirvia",
    "How Cirvia collects, uses, and protects your personal and brokerage information.",
    _PRIVACY_BODY,
    path="/privacy",
)

TERMS_HTML = _layout(
    "Terms of Service | Cirvia",
    "The terms governing your use of Cirvia's read-only, informational portfolio analysis service.",
    _TERMS_BODY,
    path="/terms",
)
