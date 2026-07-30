"""The signed-in web app: /app (sign in), /app/onboarding, /app/dashboard.

Server-rendered HTML shells (auth-exempt) with client-side supabase-js auth.
The browser signs in with the publishable key, then calls the existing API
with the Supabase JWT — the API remains the security boundary. Config
(SUPABASE_URL + anon key) is injected server-side at render time.
"""

from __future__ import annotations

import json

from app.landing import _CSS, _FONT_LINKS, CONTACT_EMAIL, ICON_LINKS, MOTION_CDN

_APP_CSS = """
/* app footer: hairline, quiet, single row (wraps on narrow screens) */
.app-foot { border-top: 1px solid var(--line); margin-top: 2rem;
  padding: 1rem 1.5rem 1.25rem; display: flex; flex-wrap: wrap;
  justify-content: center; gap: 0.4rem 1.4rem;
  font-size: 0.8rem; color: var(--ink-3); }
.app-foot a { color: var(--ink-3); text-decoration: none; }
.app-foot a:hover { color: var(--ink); }
/* app register: fixed rem type scale, quieter headings, denser rhythm */
/* app nav is always opaque (the marketing nav is transparent until scroll) */
nav {
  background: oklch(97.5% 0.01 305 / 0.88); backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px); border-bottom: 1px solid var(--line);
}
.app-wrap { max-width: 880px; margin: 0 auto; padding: 2.25rem 1.5rem 4rem; }
.app-wrap h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.015em;
  line-height: 1.25; max-width: none; margin: 0; }
.app-wrap h2 { font-size: 1.25rem; font-weight: 650; letter-spacing: -0.01em; }
.app-wrap h3 { font-size: 1rem; font-weight: 600; margin-bottom: 0; }
/* auth: full-viewport split — sign in puts the form left and the brand panel
   right; .mode-signup flips them (JS slides the columns with a FLIP swap) */
.auth-split { display: grid; grid-template-columns: 1fr minmax(400px, 44%);
  min-height: 100dvh; }
.auth-split.mode-signup { grid-template-columns: minmax(400px, 44%) 1fr; }
.auth-split.mode-signup .auth-brand { order: 0; margin: 1rem 0 1rem 1rem; }
.auth-brand { order: 2; display: flex; flex-direction: column; justify-content: space-between;
  gap: 2.5rem; margin: 1rem 1rem 1rem 0; padding: 2.25rem 2.25rem 2rem;
  border: 1px solid var(--line); border-radius: var(--r-l); overflow: hidden;
  background:
    radial-gradient(120% 85% at 50% -25%, oklch(88% 0.07 295 / 0.8), transparent 72%),
    radial-gradient(70% 55% at 8% 30%, oklch(91% 0.05 265 / 0.6), transparent 70%),
    var(--surface-1); }
.auth-brand h2 { font-size: 1.7rem; font-weight: 750; letter-spacing: -0.02em;
  line-height: 1.25; color: var(--ink); max-width: 22ch; text-wrap: balance; }
.auth-brand .brand-sub { color: var(--ink-2); font-size: 0.95rem; margin-top: 0.6rem;
  max-width: 40ch; }
.auth-steps { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 1.75rem;
  max-width: 320px; }
.auth-step { display: flex; align-items: center; gap: 0.7rem; padding: 0.72rem 0.95rem;
  border-radius: var(--r-m); font-size: 0.9rem; font-weight: 600;
  background: oklch(100% 0 0 / 0.55); color: var(--ink-3); }
.auth-step .n { width: 22px; height: 22px; border-radius: 50%; flex: none;
  display: grid; place-items: center; font-size: 0.72rem; font-weight: 700;
  background: oklch(90% 0.03 300); color: var(--ink-2); }
.auth-step.active { background: var(--ink); color: oklch(97% 0.01 300); }
.auth-step.active .n { background: oklch(38% 0.03 300); color: #fff; }
.brand-note { color: var(--ink-3); font-size: 0.85rem; max-width: 36ch; }
.auth-form-col { display: flex; align-items: center; justify-content: center;
  padding: 3rem 1.5rem; }
.auth-form { width: 100%; max-width: 380px; }
.auth-form .form-logo { display: none; margin-bottom: 2rem; }
.auth-form h1 { font-size: 1.6rem; font-weight: 750; letter-spacing: -0.02em;
  line-height: 1.25; max-width: none; margin: 0 0 0.35rem; }
.auth-form .sub { color: var(--ink-3); font-size: 0.95rem; margin-bottom: 1.4rem; }
.field-hint { color: var(--ink-3); font-size: 0.8rem; margin-top: 0.35rem; display: none; }
.forgot-row { text-align: right; margin-top: 0.45rem; }
.forgot-row .link-btn { font-size: 0.84rem; }
@media (max-width: 880px) {
  .auth-split, .auth-split.mode-signup { grid-template-columns: 1fr; }
  .auth-brand { display: none; }
  .auth-form .form-logo { display: inline-block; }
  .auth-form-col { padding: 3.5rem 1.5rem; align-items: flex-start; }
}
label { display: block; font-size: 0.84rem; font-weight: 600; color: var(--ink-3);
  margin: 0.9rem 0 0.3rem; }
input[type=email], input[type=password], input[type=time], input[type=tel],
input[type=url], input[type=text], select {
  width: 100%; padding: 0.65rem 0.8rem; border-radius: var(--r-s);
  border: 1px solid var(--line); background: var(--surface-2); color: var(--ink);
  font-family: var(--font); font-size: 0.95rem; outline: none;
  transition: border-color 0.15s var(--ease); }
input:focus, select:focus { border-color: var(--accent-hover); }
.btn.full { width: 100%; text-align: center; margin-top: 1.25rem; font-size: 0.95rem; }
.btn[disabled] { opacity: 0.55; cursor: default; transform: none; }
.switch-mode { text-align: center; margin-top: 1rem; font-size: 0.9rem; color: var(--ink-3); }
.error-box { background: oklch(50% 0.15 25 / 0.07); border: 1px solid oklch(50% 0.15 25 / 0.35);
  color: var(--loss); border-radius: var(--r-s); padding: 0.7rem 0.9rem; font-size: 0.9rem;
  margin-top: 1rem; display: none; }
.notice-box { background: oklch(52% 0.16 295 / 0.08); border: 1px solid var(--accent);
  color: var(--ink); border-radius: var(--r-s); padding: 0.7rem 0.9rem; font-size: 0.9rem;
  margin-top: 1rem; display: none; }
/* onboarding: step rail left, active panel right */
.ob-wrap { max-width: 1000px; }
.ob-layout { display: grid; grid-template-columns: 300px 1fr; gap: 2.5rem;
  align-items: start; margin-top: 1.75rem; }
.ob-rail { display: flex; flex-direction: column; gap: 0.25rem; }
.ob-step { display: grid; grid-template-columns: 30px 1fr; column-gap: 0.85rem;
  padding: 0.85rem 0.9rem; border-radius: var(--r-m); border: 1px solid transparent;
  transition: background 0.2s var(--ease), border-color 0.2s var(--ease); }
.ob-step .n { width: 30px; height: 30px; border-radius: 50%; display: grid;
  place-items: center; font-size: 0.8rem; font-weight: 700; grid-row: 1 / 3;
  background: var(--surface-2); color: var(--ink-3);
  border: 1px solid var(--line-strong);
  transition: background 0.2s var(--ease), color 0.2s var(--ease); }
.ob-step .t { font-size: 0.93rem; font-weight: 650; color: var(--ink-3); align-self: center; }
.ob-step .d { font-size: 0.83rem; color: var(--ink-3); margin-top: 0.15rem;
  display: none; }
.ob-step.active { background: var(--surface-1); border-color: var(--line); }
.ob-step.active .n { background: var(--accent); border-color: transparent; color: #fff; }
.ob-step.active .t { color: var(--ink); }
.ob-step.active .d { display: block; }
.ob-step.done .n { background: var(--accent-deep); border-color: transparent;
  color: var(--accent-text); }
.ob-step.done .t { color: var(--ink-2); }
.step-panel { background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-l); padding: 2rem; }
@media (max-width: 800px) {
  .ob-layout { grid-template-columns: 1fr; gap: 1.25rem; }
  .ob-rail { flex-direction: row; gap: 0.4rem; }
  .ob-step { grid-template-columns: 26px auto; padding: 0.5rem 0.7rem; flex: none; }
  .ob-step .n { width: 26px; height: 26px; }
  .ob-step .d { display: none !important; }
  .ob-step:not(.active) .t { display: none; }
}
.step-panel h2 { margin-bottom: 0.4rem; }
.step-panel p { color: var(--ink-2); font-size: 0.95rem; }
/* investor-profile questions: one question per screen (onboarding step 1) */
.q-head { display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 0.7rem; }
.q-back { background: none; border: 0; padding: 0.3rem 0.45rem;
  margin: -0.3rem -0.45rem; color: var(--ink-3); font: inherit;
  font-size: 0.88rem; cursor: pointer; border-radius: 6px;
  transition: color 0.15s var(--ease); }
.q-back:hover { color: var(--ink); }
.q-count { color: var(--ink-3); font-size: 0.82rem;
  font-variant-numeric: tabular-nums; }
.q-track { height: 2px; border-radius: 999px; background: var(--line);
  overflow: hidden; margin-bottom: 2rem; }
.q-track-fill { height: 100%; border-radius: 999px;
  background: var(--accent-text); }
/* q-screens are <section>s; zero out the marketing-section padding they'd
   otherwise inherit from the shared landing CSS. */
.q-screen { padding: 0; }
.q-title { text-wrap: balance; margin-bottom: 0.4rem; }
.q-sub { color: var(--ink-3); font-size: 0.92rem; margin-bottom: 1.5rem;
  max-width: 48ch; }
.q-stage { min-height: 300px; }
.q-opts { display: flex; flex-direction: column; gap: 0.55rem;
  max-width: 560px; }
.q-opt { display: flex; align-items: center; gap: 0.85rem;
  padding: 0.78rem 0.95rem; border-radius: var(--r-s);
  border: 1px solid var(--line); background: var(--surface-2); cursor: pointer;
  font-size: 0.95rem; font-weight: 600; user-select: none;
  transition: border-color 0.15s var(--ease), background 0.15s var(--ease); }
.q-opt:hover { background: var(--surface-3); }
.q-opt:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.q-opt .k { width: 22px; height: 22px; border-radius: 6px; flex: none;
  display: grid; place-items: center; font-size: 0.72rem; font-weight: 700;
  color: var(--ink-3); border: 1px solid var(--line-strong);
  font-variant-numeric: tabular-nums; }
.q-opt .ck { margin-left: auto; color: var(--accent-text); opacity: 0;
  transform: scale(0.6);
  transition: opacity 0.15s var(--ease), transform 0.15s var(--ease); }
.q-opt.selected { border-color: var(--accent);
  background: var(--accent-wash); color: var(--ink); }
.q-opt.selected .k { color: var(--accent-text); border-color: var(--accent); }
.q-opt.selected .ck { opacity: 1; transform: scale(1); }
.q-foot { display: flex; align-items: center; gap: 1.25rem; margin-top: 1.6rem; }
.q-skip { color: var(--ink-3); font-size: 0.88rem; }
.q-skip:hover { color: var(--ink); }
/* re-personalization (?personalize=1): no rail, no card chrome — the active
   question owns the viewport, vertically centered under a quiet topline. */
.ob-wrap.personalize { max-width: 780px; display: flex; flex-direction: column;
  min-height: calc(100dvh - 210px); }
.personalize #ob-title { font-size: 0.92rem; font-weight: 650;
  color: var(--ink-3); margin-bottom: 0; }
.personalize .ob-layout { display: flex; flex-direction: column; flex: 1;
  align-items: stretch; }
.personalize .ob-content { flex: 1; display: flex; flex-direction: column;
  justify-content: center; }
.personalize .step-panel { background: transparent; border: 0;
  padding: 2.5rem 0; }
.personalize .q-track { margin-bottom: 2.6rem; }
.personalize .q-title { font-size: 1.9rem; font-weight: 700;
  letter-spacing: -0.02em; }
.personalize .q-sub { font-size: 1rem; }
.personalize .q-stage { min-height: 0; }
.personalize .q-opts { max-width: none; }
.personalize .q-opt { padding: 0.95rem 1.1rem; font-size: 1rem; }
.personalize #panel-risk-picker h2 { font-size: 1.7rem;
  letter-spacing: -0.02em; }
.personalize .btn.full { width: auto; padding-left: 2.2rem;
  padding-right: 2.2rem; }
@media (max-width: 640px) {
  .personalize .q-title { font-size: 1.5rem; }
  .personalize .step-panel { padding: 1.25rem 0; }
  .personalize .q-stage { min-height: 0; }
  .ob-wrap.personalize { min-height: 0; }
}
/* risk-comfort posture cards (onboarding step 4) */
.posture-cards { display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem; margin: 1rem 0; }
@media (max-width: 800px) { .posture-cards { grid-template-columns: 1fr; } }
.posture-card { display: flex; flex-direction: column; gap: 0.3rem;
  padding: 0.9rem; border-radius: var(--r-s); border: 1px solid var(--line);
  background: var(--surface-2); cursor: pointer;
  transition: border-color 0.15s var(--ease), background 0.15s var(--ease); }
.posture-card.selected { border-color: var(--accent);
  background: var(--accent-wash); }
.posture-card .pc-title { font-weight: 700; font-size: 0.95rem; }
/* min-height keeps the three fans on one baseline when subtitles wrap to
   different line counts */
.posture-card .pc-sub { color: var(--ink-3); font-size: 0.78rem;
  min-height: 2.6em; }
.posture-card .pc-fan { margin: 0.4rem 0 0.2rem; }
/* per-card stat grid: labels muted, values carry the hierarchy */
.posture-card .pc-nums { display: grid; grid-template-columns: auto 1fr;
  gap: 0.12rem 0.6rem; align-items: baseline; }
.pc-nums .pn-l { color: var(--ink-3); font-size: 0.76rem; }
.pc-nums .pn-v { text-align: right; font-size: 0.84rem; font-weight: 600;
  color: var(--ink); font-variant-numeric: tabular-nums; white-space: nowrap; }
.pc-nums .pn-v.pos { color: var(--gain); }
.pc-nums .pn-v.neg { color: var(--loss); }
.mf-outer { fill: oklch(52% 0.17 295); opacity: 0.14; }
.mf-inner { fill: oklch(52% 0.17 295); opacity: 0.30; }
.mf-median { stroke: var(--accent-text); stroke-width: 2; fill: none;
  stroke-linejoin: round; stroke-linecap: round; }
.mf-zero { stroke: var(--line-strong); stroke-width: 1; }
.mf-endlbl { font-size: 10px; font-weight: 600; fill: var(--ink-2);
  font-variant-numeric: tabular-nums; }
.mf-endlbl.pos { fill: var(--gain); }
.mf-endlbl.neg { fill: var(--loss); }
#posture-btn { margin-top: 0.4rem; }
.status-line { display: flex; align-items: center; gap: 0.6rem; margin: 1rem 0;
  color: var(--ink-3); font-size: 0.95rem; }
.spinner { width: 16px; height: 16px; border: 2px solid var(--line);
  border-top-color: var(--accent-text); border-radius: 50%;
  animation: spin 0.8s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }
/* skeleton loading */
.skl { height: 0.85rem; border-radius: 6px; background: var(--surface-2);
  margin: 0.65rem 0; animation: skl-pulse 1.4s ease-in-out infinite; }
.skl.short { width: 55%; }
@keyframes skl-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.45; } }
@media (prefers-reduced-motion: reduce) {
  .skl, .skl-inline { animation: none; opacity: 0.7; }
}
/* dashboard: summary strip + tabbed sections, chat in a floating panel */
.dash-wrap { max-width: 1400px; padding-top: 1.5rem; }
.dash-wrap .topbar { margin-bottom: 1.1rem; }
.dash-wrap .warn-banner { margin-bottom: 1rem; }
.dash-summary { display: flex; flex-wrap: wrap; gap: 0.6rem 2rem; align-items: baseline;
  background: var(--surface-1); border: 1px solid var(--line); border-radius: var(--r-l);
  padding: 0.85rem 1.3rem; margin-bottom: 1rem; }
.sum-item { display: flex; flex-direction: column; }
.sum-item .k { font-size: 0.72rem; font-weight: 600; color: var(--ink-3);
  text-transform: uppercase; letter-spacing: 0.05em; }
.sum-item .v { font-size: 1.25rem; font-weight: 650; color: var(--ink);
  font-variant-numeric: tabular-nums; }
.sum-item .v .sub { font-size: 0.85rem; font-weight: 500; color: var(--ink-3); }
.sum-digest-chip { margin-left: auto; align-self: center; font-size: 0.85rem;
  color: var(--accent-text); background: var(--accent-wash); border: 1px solid var(--line);
  border-radius: 999px; padding: 0.3rem 0.8rem; cursor: pointer; font-family: var(--font); }
.dash-tabs { display: flex; gap: 0.25rem; border-bottom: 1px solid var(--line-strong);
  margin-bottom: 1rem; overflow-x: auto; scrollbar-width: none; }
.dash-tabs::-webkit-scrollbar { display: none; }
.dash-tab { background: none; border: none; border-bottom: 2px solid transparent;
  font-family: var(--font); font-size: 0.95rem; font-weight: 600; color: var(--ink-3);
  padding: 0.55rem 0.9rem 0.65rem; cursor: pointer; white-space: nowrap;
  margin-bottom: -1px; transition: color 0.15s var(--ease); }
.dash-tab:hover { color: var(--ink); }
.dash-tab[aria-selected="true"] { color: var(--accent-text); border-bottom-color: var(--accent); }
.dash-panel { display: none; flex-direction: column; gap: 1rem; min-width: 0; }
.dash-panel.active { display: flex; }
.dash-card { background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-l); padding: 1.15rem 1.3rem 1.25rem; }
/* floating chat: pill launcher + anchored slide-out panel */
.chat-fab { position: fixed; right: 1.25rem; bottom: 1.25rem; z-index: 70;
  display: inline-flex; align-items: center; gap: 0.5rem; min-height: 48px;
  padding: 0 1.2rem; border: none; border-radius: 999px; background: var(--accent);
  color: white; font-family: var(--font); font-size: 0.95rem; font-weight: 650;
  cursor: pointer; box-shadow: 0 10px 28px oklch(35% 0.05 300 / 0.35); }
.chat-fab:hover { background: var(--accent-hover); }
.chat-panel { position: fixed; right: 1.25rem; bottom: 5.6rem; z-index: 71;
  width: min(400px, calc(100vw - 2rem)); height: min(70vh, 620px);
  display: none; flex-direction: column; background: var(--surface-1);
  border: 1px solid var(--line-strong); border-radius: var(--r-l);
  padding: 1rem 1.15rem 1.05rem; box-shadow: 0 18px 48px oklch(35% 0.05 300 / 0.3); }
.chat-panel.open { display: flex; }
.chat-panel h3 { display: flex; justify-content: space-between; align-items: baseline; }
.chat-panel .chat-log { flex: 1; min-height: 0; max-height: none; }
.chat-close { background: none; border: none; color: var(--ink-3); cursor: pointer;
  font-size: 1.1rem; padding: 0.2rem 0.4rem; font-family: var(--font); }
/* holdings tab: table beside allocation donut */
.holdings-split { display: grid; grid-template-columns: minmax(0, 1fr) 250px;
  gap: 1.5rem; align-items: start; margin-top: 0.5rem; }
@media (max-width: 900px) { .holdings-split { grid-template-columns: 1fr; } }
.pie-box svg { display: block; width: 100%; max-width: 220px; height: auto; margin: 0 auto; }
.pie-slice { cursor: pointer; transition: opacity 0.15s var(--ease); }
.pie-leg-row { transition: opacity 0.15s var(--ease); }
.pie-box.has-hover .pie-slice:not(.hl),
.pie-box.has-hover .pie-leg-row:not(.hl) { opacity: 0.35; }
.pie-legend { margin-top: 0.75rem; font-size: 0.82rem; }
.pie-leg-row { display: flex; align-items: center; gap: 0.55rem; padding: 0.16rem 0;
  color: var(--ink-2); font-variant-numeric: tabular-nums; cursor: default; }
/* Legend avatar: slice-color disc doubling as the lettermark fallback; the
   fetched logo lands on an inset white disc, leaving a 2px slice-color ring
   so the color mapping to the donut survives the logo. */
.pie-leg-row .lg { width: 20px; height: 20px; border-radius: 50%; flex: none;
  position: relative; display: flex; align-items: center; justify-content: center; }
.pie-leg-row .lg .ch { font-size: 0.6rem; font-weight: 700; color: #fff;
  line-height: 1; user-select: none; }
.pie-leg-row .lg img { position: absolute; inset: 2px;
  /* imgs are replaced elements: inset alone won't size them */
  width: calc(100% - 4px); height: calc(100% - 4px); border-radius: 50%;
  background: var(--surface-1); object-fit: contain; padding: 1px;
  animation: logo-in 0.15s var(--ease); }
@keyframes logo-in { from { opacity: 0; } }
@media (prefers-reduced-motion: reduce) {
  .pie-leg-row .lg img { animation: none; }
}
.pie-leg-row .t { font-weight: 600; color: var(--ink); flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; }
.dash-card h3 { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
.dash-card h3 .tag { font-size: 0.8rem; font-weight: 600; color: var(--ink-3);
  font-variant-numeric: tabular-nums; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 0.75rem;
  font-variant-numeric: tabular-nums; }
th { text-align: left; color: var(--ink-3); font-weight: 600; font-size: 0.72rem;
  text-transform: uppercase; letter-spacing: 0.05em; padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--line-strong); }
td { padding: 0.55rem 0.5rem; border-bottom: 1px solid var(--line); }
tr:last-child td { border-bottom: none; }
.pos { color: var(--gain); } .neg { color: var(--loss); } .mid { color: var(--warn); }
.digest-body { white-space: pre-wrap; color: var(--ink-2); font-size: 0.95rem;
  margin-top: 0.75rem; line-height: 1.6; }
.alert-item { padding: 0.75rem 0; border-bottom: 1px solid var(--line); }
.alert-item:last-child { border-bottom: none; }
.alert-item .head { font-weight: 600; font-size: 0.95rem; color: var(--ink); }
.alert-item .meta { color: var(--ink-3); font-size: 0.8rem; margin-top: 0.15rem; }
.sev-high { color: var(--loss); } .sev-medium { color: var(--warn); } .sev-low { color: var(--ink-3); }
/* chat */
.chat-log { max-height: 320px; overflow-y: auto; margin: 0.75rem 0; }
.chat-msg { padding: 0.6rem 0.9rem; border-radius: var(--r-m); margin: 0.5rem 0;
  font-size: 0.93rem; line-height: 1.55; white-space: pre-wrap; color: var(--ink-2); }
.chat-msg.user { background: var(--surface-2); margin-left: 2rem; }
.chat-msg.bot { background: var(--accent-wash); margin-right: 2rem; }
.chat-step { display: flex; align-items: center; gap: 0.45rem; color: var(--ink-3);
  font-size: 0.82rem; margin: 0.15rem 0; }
.chat-step .st { width: 1em; text-align: center; }
.chat-step.done .st { color: var(--gain); }
.chat-step.fail .st { color: var(--loss); }
.chat-note { color: var(--ink-3); font-size: 0.85rem; font-style: italic; margin: 0.2rem 0; }
/* deep dive */
.dd-stages { list-style: none; padding: 0; margin: 0.75rem 0 0.25rem; }
.dd-stages li { display: flex; align-items: center; gap: 0.5rem; margin: 0.35rem 0;
  font-size: 0.9rem; color: var(--ink-2); flex-wrap: wrap; }
.dd-stages .st { width: 1.1em; text-align: center; color: var(--ink-3); }
.dd-stages li.done .st { color: var(--gain); }
.dd-stages li.fail .st { color: var(--loss); }
.dd-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-left: 0.4rem; }
.dd-chip { font-size: 0.78rem; padding: 0.15rem 0.55rem; border-radius: 999px;
  border: 1px solid var(--line); color: var(--ink-3); }
.dd-chip.running { border-color: var(--accent-hover); color: var(--ink-2); }
.dd-chip.done { border-color: var(--gain); }
.dd-chip.fail { border-color: var(--loss); }
.dd-activity { color: var(--ink-3); font-size: 0.8rem; margin-top: 0.4rem;
  min-height: 1.1em; font-style: italic; }
.dd-finding { margin: 0.5rem 0; padding: 0.4rem 0.75rem; border-left: 2px solid var(--line);
  font-size: 0.92rem; line-height: 1.5; }
.dd-finding .ev { color: var(--ink-3); font-size: 0.83rem; }
.dd-badge { font-size: 0.72rem; padding: 0.1rem 0.45rem; border-radius: 999px;
  border: 1px solid var(--line); color: var(--ink-3); margin-left: 0.4rem; white-space: nowrap; }
.dd-badge.verified { color: var(--gain); border-color: var(--gain); }
.dd-badge.challenged { color: var(--warn); border-color: var(--warn); }
.dd-summary-actions { margin-top: 0.75rem; }
.dd-layout { display: grid; grid-template-columns: 260px 1fr; gap: 1.25rem;
  align-items: start; margin-top: 0.75rem; }
@media (max-width: 780px) { .dd-layout { grid-template-columns: 1fr; } }
.dd-list { display: flex; flex-direction: column; gap: 0.5rem; }
.dd-list-item { text-align: left; padding: 0.6rem 0.75rem; border-radius: var(--r-s);
  border: 1px solid var(--line); background: var(--surface-2); color: var(--ink-2);
  font-family: var(--font); font-size: 0.85rem; cursor: pointer; line-height: 1.4; }
.dd-list-item:hover { border-color: var(--accent-hover); }
.dd-list-item.active { border-color: var(--accent-hover); color: var(--ink); }
.dd-list-item .when { font-weight: 600; }
.dd-list-item .head { display: block; color: var(--ink-3); font-size: 0.8rem;
  margin-top: 0.15rem; overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.chat-row { display: flex; gap: 0.5rem; }
.chat-row input { flex: 1; padding: 0.65rem 0.8rem; border-radius: var(--r-s);
  border: 1px solid var(--line); background: var(--surface-2); color: var(--ink);
  font-family: var(--font); font-size: 0.95rem; outline: none; }
.chat-row input:focus { border-color: var(--accent-hover); }
.chat-row .btn { border: none; }
.topbar { display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 1.5rem; gap: 1rem; }
.topbar .who { color: var(--ink-3); font-size: 0.9rem; }
.link-btn { background: none; border: none; color: var(--accent-text); cursor: pointer;
  font-family: var(--font); font-size: 0.9rem; padding: 0; }
.link-btn:hover { text-decoration: underline; }
.muted-note { color: var(--ink-3); font-size: 0.88rem; margin-top: 0.75rem; }
/* delivery channel picker (onboarding step 4 + dashboard card) */
.channel-options { display: flex; gap: 0.5rem; margin-top: 0.35rem; flex-wrap: wrap; }
.channel-opt { flex: 1; min-width: 108px; padding: 0.6rem 0.75rem; border-radius: var(--r-s);
  border: 1px solid var(--line); background: var(--surface-2); cursor: pointer;
  font-size: 0.9rem; font-weight: 600; color: var(--ink-2); text-align: center;
  transition: border-color 0.15s var(--ease), background 0.15s var(--ease); }
.channel-opt.selected { border-color: var(--accent); color: var(--ink);
  background: var(--accent-wash); }
.consent-row { display: flex; gap: 0.6rem; align-items: flex-start; margin-top: 1rem;
  font-size: 0.82rem; color: var(--ink-3); font-weight: 500; cursor: pointer; }
.consent-row input { margin-top: 0.2rem; }
.chip-ok { color: var(--gain); font-size: 0.8rem; font-weight: 600; }
.chip-warn { color: var(--warn); font-size: 0.8rem; font-weight: 600; }
/* broken-connection banner (error-box vocabulary, --warn tinted) */
.warn-banner { display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 0.75rem 1rem; padding: 0.85rem 1.1rem;
  border: 1px solid oklch(54% 0.12 75 / 0.4); background: oklch(54% 0.12 75 / 0.08);
  border-radius: var(--r-m); font-size: 0.9rem; color: var(--ink-2); }
.warn-banner strong { color: var(--warn); font-weight: 650; }
.warn-banner .actions { display: flex; align-items: center; gap: 0.9rem; }
/* setup nudge variant: accent-tinted, for onboarding prompts, not errors */
.warn-banner.setup { border-color: oklch(52% 0.16 295 / 0.45);
  background: oklch(52% 0.16 295 / 0.08); }
.warn-banner.setup strong { color: var(--accent-text); }
/* holdings + news dashboard */
.holdings-row { cursor: pointer; transition: background 0.15s var(--ease); }
.holdings-row:hover { background: var(--surface-2); }
.ticker-link { color: var(--ink); text-decoration: none; }
.ticker-link::after { content: ' \\2192'; color: var(--accent-text);
  opacity: 0; transition: opacity 0.15s var(--ease); }
.holdings-row:hover .ticker-link::after { opacity: 1; }
/* inline shimmer for metric cells that arrive on the second call */
.skl-inline { display: inline-block; width: 2.6rem; height: 0.7rem;
  border-radius: 4px; background: var(--surface-2); vertical-align: middle;
  animation: skl-pulse 1.4s ease-in-out infinite; }
.earn-soon { color: var(--accent-text); font-weight: 650; }
/* holdings: horizontal swipe with the Ticker column pinned left */
#holdings { position: relative; }
.table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.table-scroll table { min-width: 720px; }
#holdings th:first-child, #holdings td:first-child {
  position: sticky; left: 0; z-index: 2; background: var(--surface-1); }
.holdings-row:hover td:first-child { background: var(--surface-2); }
/* scroll affordances only when the table actually overflows */
#holdings.is-scrollable th:first-child, #holdings.is-scrollable td:first-child {
  box-shadow: 6px 0 10px -6px oklch(35% 0.05 300 / 0.18); }
#holdings.is-scrollable::after {
  content: ""; position: absolute; top: 0; right: 0; bottom: 0; width: 32px;
  pointer-events: none; background: linear-gradient(to left, var(--surface-1), transparent);
  transition: opacity 0.2s var(--ease); }
#holdings.is-scrollable.at-end::after { opacity: 0; }
.acct-count { font-size: 0.72rem; color: var(--ink-3); margin-left: 0.5rem; }
.watchlist-badge { font-size: 0.68rem; font-weight: 650; color: var(--accent-text);
  border: 1px solid var(--accent); border-radius: 999px; padding: 0.1rem 0.45rem;
  margin-left: 0.4rem; vertical-align: middle; }
.filters-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1rem 0 0.75rem;
  align-items: center; }
.filters-row label { margin: 0; font-size: 0.78rem; }
.filters-row select { width: auto; min-width: 7rem; padding: 0.45rem 0.6rem;
  font-size: 0.85rem; }
.news-feed { max-height: 420px; overflow-y: auto; margin-top: 0.75rem; }
.news-day { color: var(--ink-3); font-size: 0.72rem; font-weight: 650;
  text-transform: uppercase; letter-spacing: 0.06em; margin: 0.9rem 0 0.1rem; }
.news-day:first-child { margin-top: 0; }
.news-item { padding: 0.85rem 0; border-bottom: 1px solid var(--line); }
.news-item:last-child { border-bottom: none; }
.news-item .head { font-weight: 650; font-size: 0.95rem; color: var(--ink); line-height: 1.4; }
.news-item .body { color: var(--ink-2); font-size: 0.88rem; margin-top: 0.35rem;
  line-height: 1.55; white-space: pre-wrap; }
.news-item .meta { color: var(--ink-3); font-size: 0.78rem; margin-top: 0.25rem; }
.news-item a { color: var(--accent-text); }
.watchlist-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.5rem; margin: 0.75rem 0; }
.watchlist-opt { padding: 0.65rem 0.75rem; border-radius: var(--r-s);
  border: 1px solid var(--line); background: var(--surface-2); cursor: pointer;
  font-size: 0.9rem; font-weight: 600; text-align: center;
  transition: border-color 0.15s var(--ease), background 0.15s var(--ease); }
.watchlist-opt.selected { border-color: var(--accent);
  background: var(--accent-wash); color: var(--ink); }
.refresh-row { display: flex; align-items: center; gap: 0.75rem; }
.updated-at { color: var(--ink-3); font-size: 0.82rem; }
/* stock detail page */
.stock-layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px;
  gap: 1rem; align-items: start; }
.stock-main, .stock-rail { display: flex; flex-direction: column; gap: 1rem;
  min-width: 0; }
@media (max-width: 1080px) { .stock-layout { grid-template-columns: 1fr; } }
.back-link { color: var(--ink-3); text-decoration: none; font-size: 0.88rem; }
.back-link:hover { color: var(--ink); }
.stock-head { display: flex; align-items: baseline; gap: 0.85rem; flex-wrap: wrap;
  margin-top: 0.4rem; }
.stock-head .sub { color: var(--ink-3); font-size: 0.9rem; }
.watch-wrap { text-align: right; }
.watch-wrap .muted-note { max-width: 30ch; margin-top: 0.45rem; font-size: 0.82rem; }
.stock-price { font-size: 1.25rem; font-weight: 700;
  font-variant-numeric: tabular-nums; }
.metric-trio { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
@media (max-width: 800px) { .metric-trio { grid-template-columns: 1fr; } }
.metric-list { margin-top: 0.6rem; }
.metric-row { display: flex; justify-content: space-between; gap: 1rem;
  padding: 0.42rem 0; border-bottom: 1px solid var(--line); font-size: 0.9rem; }
.metric-row:last-child { border-bottom: none; }
.metric-row .k { color: var(--ink-3); }
.metric-row .v { color: var(--ink); font-variant-numeric: tabular-nums;
  text-align: right; }
.chart-controls { display: flex; gap: 0.4rem; }
.chart-controls button { background: var(--surface-2); border: 1px solid var(--line);
  color: var(--ink-3); border-radius: 999px; padding: 0.22rem 0.7rem;
  font-size: 0.78rem; font-weight: 600; cursor: pointer; font-family: var(--font);
  transition: border-color 0.15s var(--ease), color 0.15s var(--ease); }
.chart-controls button.active { background: var(--accent-deep);
  color: var(--accent-text); border-color: var(--accent); }
#chart { position: relative; }
/* pan-y keeps vertical page scroll alive while a horizontal drag traces */
#chart svg { display: block; width: 100%; height: auto; margin-top: 0.75rem;
  touch-action: pan-y; cursor: crosshair; }
.chart-tip { position: absolute; top: 0.9rem; display: none; pointer-events: none;
  transform: translateX(-50%); background: var(--surface-3);
  border: 1px solid var(--line-strong); border-radius: var(--r-s);
  padding: 0.22rem 0.55rem; font-size: 0.8rem; color: var(--ink);
  font-variant-numeric: tabular-nums; white-space: nowrap; z-index: 5; }
.range-bar { position: relative; height: 4px; border-radius: 999px;
  background: var(--surface-3); margin: 0.9rem 0 0.35rem; }
.range-bar .dot { position: absolute; top: 50%; width: 10px; height: 10px;
  border-radius: 50%; background: var(--accent-text);
  transform: translate(-50%, -50%); }
.range-ends { display: flex; justify-content: space-between; color: var(--ink-3);
  font-size: 0.78rem; font-variant-numeric: tabular-nums; }
/* settings: single quiet column of cards */
.settings-wrap { max-width: 640px; }
.settings-wrap .dash-card { margin-top: 1rem; }
.plan-limits { margin: 0.75rem 0 0; padding-left: 1.15rem; color: var(--ink-2);
  font-size: 0.92rem; }
.plan-limits li { margin: 0.3rem 0; }
.danger-card { border-color: oklch(50% 0.15 25 / 0.4); }
.danger-card h3 { color: var(--loss); }
/* nav stock search: inline input between logo and links, absolute dropdown */
.nav-search { position: relative; flex: 1; max-width: 300px; margin: 0 1.25rem; }
.nav-search input[type=search] { width: 100%; padding: 0.42rem 0.75rem;
  border-radius: var(--r-s); border: 1px solid var(--line);
  background: var(--surface-2); color: var(--ink); font-family: var(--font);
  font-size: 0.88rem; outline: none;
  transition: border-color 0.15s var(--ease); }
.nav-search input[type=search]:focus { border-color: var(--accent-hover); }
.search-results { position: absolute; top: calc(100% + 6px); left: 0; right: 0;
  background: var(--surface-1); border: 1px solid var(--line-strong);
  border-radius: var(--r-m); overflow: hidden; display: none; z-index: 60;
  box-shadow: 0 12px 32px oklch(35% 0.05 300 / 0.16); }
.search-results.open { display: block; }
.search-results a { display: flex; align-items: baseline; gap: 0.55rem;
  padding: 0.6rem 0.8rem; text-decoration: none; font-size: 0.88rem;
  color: var(--ink); border-bottom: 1px solid var(--line); }
.search-results a:last-child { border-bottom: none; }
.search-results a:hover, .search-results a.focused { background: var(--surface-2); }
.search-results .sym { font-weight: 700; flex: none; }
.search-results .nm { color: var(--ink-2); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; min-width: 0; flex: 1; }
.search-results .exch { color: var(--ink-3); font-size: 0.78rem; flex: none; }
.search-results .empty { padding: 0.6rem 0.8rem; color: var(--ink-3);
  font-size: 0.85rem; }
/* phone tier: tighter shell, wrapping headers, 16px inputs (stops iOS
   focus-zoom), and >=44px tap targets */
@media (max-width: 640px) {
  .app-wrap { padding: 1.4rem 1rem 3rem; }
  .nav-search { margin: 0 0.7rem; min-width: 0; }
  .nav-search input[type=search] { font-size: 1rem; }
  .nav-links { gap: 0.9rem; font-size: 0.88rem; }
  .nav-links a.keep, .nav-links .link-btn { padding: 0.6rem 0.1rem; }
  .topbar { flex-wrap: wrap; gap: 0.25rem 1rem; }
  .dash-card { padding: 0.95rem 1rem 1.1rem; }
  .dash-card h3 { flex-wrap: wrap; row-gap: 0.35rem; }
  .refresh-row { flex-wrap: wrap; }
  .filters-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
  .filters-row select { width: 100%; min-width: 0; }
  .chat-msg.user { margin-left: 1rem; }
  .chat-msg.bot { margin-right: 1rem; }
  input[type=email], input[type=password], input[type=time], input[type=tel],
  input[type=url], input[type=text], select, .chat-row input { font-size: 1rem; }
  .btn { display: inline-flex; align-items: center; justify-content: center;
    min-height: 44px; }
  .link-btn { padding: 0.5rem 0.25rem; margin: -0.5rem -0.25rem; }
  .link-btn:hover { text-decoration: none; }
  .chart-controls button { padding: 0.45rem 0.9rem; }
  .chat-panel { inset: 0; width: auto; height: auto; border-radius: 0; z-index: 75; }
  .chat-fab { bottom: 0.9rem; right: 0.9rem; }
  .dash-summary { gap: 0.5rem 1.25rem; padding: 0.75rem 1rem; }
  .sum-digest-chip { margin-left: 0; }
  .auth-form-col { padding: 2.5rem 1.25rem; }
  .ob-rail { overflow-x: auto; }
  .step-panel { padding: 1.25rem 1rem; }
}
"""

_SHELL_JS = """
const SB_URL = window.CIRVIA_CONFIG.supabaseUrl;
const SB_KEY = window.CIRVIA_CONFIG.supabaseAnonKey;
const sb = window.supabase.createClient(SB_URL, SB_KEY);

async function getToken() {
  const { data } = await sb.auth.getSession();
  return data.session ? data.session.access_token : null;
}

// Cached per-user page data (see the dashboard boot sequence) must never
// outlive the session it belongs to.
function clearBootCaches() {
  try {
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith('cirvia:boot:')) localStorage.removeItem(k);
    }
  } catch (e) { /* storage unavailable */ }
}

async function api(path, opts = {}) {
  const token = await getToken();
  if (!token) { clearBootCaches(); window.location.href = '/app'; throw new Error('not signed in'); }
  const resp = await fetch(path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + token,
      ...(opts.headers || {}),
    },
  });
  if (resp.status === 401) { clearBootCaches(); window.location.href = '/app'; throw new Error('session expired'); }
  return resp;
}

async function requireSession() {
  const token = await getToken();
  if (!token) { window.location.href = '/app'; return false; }
  return true;
}

async function signOut() {
  clearBootCaches();
  await sb.auth.signOut();
  window.location.href = '/app';
}

// Product-register motion: short state transitions only, skipped for
// reduced-motion users or if the Motion CDN script failed to load.
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
const EASE = [0.22, 1, 0.36, 1];

function riseIn(el, duration = 0.22) {
  if (REDUCED || !window.Motion || !el) return;
  Motion.animate(el,
    { opacity: [0, 1], transform: ['translateY(6px)', 'translateY(0px)'] },
    { duration, ease: EASE });
}

function staggerIn(els, duration = 0.25, gap = 0.04) {
  if (REDUCED || !window.Motion || !els || !els.length) return;
  Motion.animate(els, { opacity: [0, 1] }, { duration, delay: Motion.stagger(gap), ease: EASE });
}

// Nav stock search: debounced type-ahead against /stocks/search; every chrome
// page has the input. Enter opens the first result, Escape/blur closes.
(function initNavSearch() {
  const input = document.getElementById('nav-search');
  const box = document.getElementById('nav-search-results');
  if (!input || !box) return;
  const escText = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let timer = null;
  let seq = 0;
  function close() { box.classList.remove('open'); box.innerHTML = ''; }
  function render(results) {
    if (!results.length) {
      box.innerHTML = '<div class="empty">No matches.</div>';
      box.classList.add('open');
      return;
    }
    box.innerHTML = results.map((r) =>
      '<a href="/app/stock/' + encodeURIComponent(r.symbol) + '">' +
      '<span class="sym">' + escText(r.symbol) + '</span>' +
      '<span class="nm">' + escText(r.name) + '</span>' +
      (r.exchange ? '<span class="exch">' + escText(r.exchange) + '</span>' : '') +
      '</a>').join('');
    box.classList.add('open');
  }
  async function search(q) {
    const mySeq = ++seq;
    try {
      const resp = await api('/stocks/search?q=' + encodeURIComponent(q));
      if (!resp.ok || mySeq !== seq) return;
      const data = await resp.json();
      if (mySeq !== seq || document.activeElement !== input) return;
      render(data.results || []);
    } catch (e) { /* search is a convenience; stay quiet */ }
  }
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { close(); return; }
    timer = setTimeout(() => search(q), 250);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { close(); input.blur(); }
    if (e.key === 'Enter') {
      const first = box.querySelector('a');
      if (first) window.location.href = first.getAttribute('href');
    }
  });
  input.addEventListener('blur', () => setTimeout(close, 150));
})();
"""


def _page(
    title: str,
    body: str,
    *,
    supabase_url: str,
    anon_key: str,
    extra_js: str,
    chrome: bool = True,
    wrap_class: str = "app-wrap",
    extra_config: dict | None = None,
) -> str:
    # Page parameters (e.g. the stock page's ticker) travel through the JSON
    # config blob — never interpolated into markup or script text.
    config = json.dumps(
        {"supabaseUrl": supabase_url, "supabaseAnonKey": anon_key, **(extra_config or {})}
    )
    if chrome:
        shell = f"""<nav><div class="nav-inner">
<a class="logo" href="/">Cir<span>via</span></a>
<div class="nav-search">
<input id="nav-search" type="search" placeholder="Search stocks…" autocomplete="off"
 spellcheck="false" aria-label="Search stocks">
<div class="search-results" id="nav-search-results" role="listbox"></div>
</div>
<div class="nav-links"><a class="keep" href="/app/dashboard">Dashboard</a>
<a class="keep" href="/app/picks">Top Picks</a>
<a class="keep" href="/app/risk">Risk Lab</a>
<a class="keep" href="/app/deep-dives">Deep Dives</a>
<a class="keep" href="/app/settings">Settings</a>
<button class="link-btn" onclick="signOut()">Sign out</button></div>
</div></nav>
<main class="{wrap_class}">
{body}
</main>
<footer class="app-foot">
<a href="/privacy">Privacy</a>
<a href="/terms">Terms</a>
<a href="/contact">Contact</a>
<span>Not financial advice.</span>
</footer>"""
    else:
        shell = body
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="robots" content="noindex">
{ICON_LINKS}{_FONT_LINKS}<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<style>{_CSS}{_APP_CSS}</style>
</head>
<body>
{shell}
<script>window.CIRVIA_CONFIG = {config};</script>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
<script src="{MOTION_CDN}"></script>
<script>{_SHELL_JS}</script>
<script>{extra_js}</script>
</body>
</html>"""


# --------------------------------------------------------------------------
# /app — sign in / sign up
# --------------------------------------------------------------------------

_LOGIN_BODY = """
<div class="auth-split">
  <aside class="auth-brand">
    <a class="logo" href="/">Cir<span>via</span></a>
    <div>
      <h2 id="brand-title">Welcome back.</h2>
      <p class="brand-sub" id="brand-sub">Sign in to catch up on your digest, alerts, and holdings.</p>
      <div class="auth-steps" id="brand-steps" style="display:none;">
        <div class="auth-step active"><span class="n">1</span> Create your account</div>
        <div class="auth-step"><span class="n">2</span> Connect your brokerage</div>
        <div class="auth-step"><span class="n">3</span> Get your morning digest</div>
      </div>
    </div>
    <p class="brand-note">Read-only by design. Cirvia can never trade or move money.</p>
  </aside>
  <div class="auth-form-col">
    <div class="auth-form">
      <a class="logo form-logo" href="/">Cir<span>via</span></a>
      <h1 id="auth-title">Sign in</h1>
      <p class="sub" id="auth-sub">Continue to your portfolio brief.</p>
      <div class="status-line" id="auth-redirecting" style="display:none;">
        <span class="spinner"></span><span>Taking you to your dashboard&hellip;</span>
      </div>
      <form id="auth-form">
        <label for="email">Email</label>
        <input type="email" id="email" autocomplete="email" required>
        <label for="password">Password</label>
        <input type="password" id="password" autocomplete="current-password" minlength="8" required>
        <p class="field-hint" id="pw-hint">At least 8 characters.</p>
        <p class="forgot-row" id="forgot-row">
          <button class="link-btn" id="forgot-btn" type="button">Forgot password?</button>
        </p>
        <button class="btn full" id="auth-btn" type="submit">Sign in</button>
      </form>
      <div class="error-box" id="auth-error"></div>
      <div class="notice-box" id="auth-notice"></div>
      <p class="switch-mode">
        <span id="switch-label">New to Cirvia?</span>
        <button class="link-btn" id="switch-btn" type="button">Create an account</button>
      </p>
    </div>
  </div>
</div>
"""

_LOGIN_JS = """
let mode = 'signin';
const form = document.getElementById('auth-form');
const errBox = document.getElementById('auth-error');
const noticeBox = document.getElementById('auth-notice');
const btn = document.getElementById('auth-btn');

// FLIP swap: measure both columns, flip the grid via .mode-signup, then
// slide each column from its old position to its new one.
function setSplitSides(animate) {
  const split = document.querySelector('.auth-split');
  const cols = [document.querySelector('.auth-brand'),
                document.querySelector('.auth-form-col')];
  cols.forEach((el) => el.getAnimations().forEach((a) => a.cancel()));
  const first = cols.map((el) => el.getBoundingClientRect().left);
  split.classList.toggle('mode-signup', mode === 'signup');
  if (!animate || REDUCED || !window.Motion) return;
  cols.forEach((el, i) => {
    const dx = first[i] - el.getBoundingClientRect().left;
    if (Math.abs(dx) < 1) return;  // mobile: brand hidden, nothing moves
    Motion.animate(el,
      { transform: ['translateX(' + dx + 'px)', 'translateX(0px)'] },
      { duration: 0.55, ease: EASE });
  });
  riseIn(document.querySelector('.auth-brand > div'), 0.45);
}

function applyMode(animate) {
  const signin = mode === 'signin';
  document.getElementById('auth-title').textContent =
    signin ? 'Sign in' : 'Create your account';
  document.getElementById('auth-sub').textContent =
    signin ? 'Continue to your portfolio brief.'
           : 'Free to start. No card required.';
  document.getElementById('switch-label').textContent =
    signin ? 'New to Cirvia?' : 'Already have an account?';
  document.getElementById('switch-btn').textContent =
    signin ? 'Create an account' : 'Sign in';
  btn.textContent = signin ? 'Sign in' : 'Create account';
  document.getElementById('pw-hint').style.display = signin ? 'none' : 'block';
  document.getElementById('forgot-row').style.display = signin ? 'block' : 'none';
  document.getElementById('password').setAttribute('autocomplete',
    signin ? 'current-password' : 'new-password');
  // The brand aside pitches the 3-step setup only to new users; returning
  // users get a plain welcome instead.
  document.getElementById('brand-title').textContent = signin
    ? 'Welcome back.'
    : 'Know what matters to your portfolio before the market opens.';
  document.getElementById('brand-sub').textContent = signin
    ? 'Sign in to catch up on your digest, alerts, and holdings.'
    : 'Three steps and your first morning digest is on its way.';
  document.getElementById('brand-steps').style.display = signin ? 'none' : '';
  errBox.style.display = 'none'; noticeBox.style.display = 'none';
  setSplitSides(animate);
}

document.getElementById('switch-btn').addEventListener('click', () => {
  mode = mode === 'signin' ? 'signup' : 'signin';
  applyMode(true);
});

// Marketing CTAs deep-link to /app#signup so new visitors start on the
// create-account view instead of the sign-in form.
if (location.hash === '#signup') { mode = 'signup'; applyMode(false); }

document.getElementById('forgot-btn').addEventListener('click', async () => {
  errBox.style.display = 'none'; noticeBox.style.display = 'none';
  const email = document.getElementById('email').value.trim();
  if (!email) {
    errBox.textContent = 'Enter your email above first, then click Forgot password.';
    errBox.style.display = 'block';
    return;
  }
  const forgotBtn = document.getElementById('forgot-btn');
  forgotBtn.disabled = true;
  try {
    const { error } = await sb.auth.resetPasswordForEmail(email, {
      redirectTo: location.origin + '/app/reset',
    });
    if (error) throw error;
    noticeBox.textContent = 'Check your email for a link to reset your password.';
    noticeBox.style.display = 'block';
  } catch (e) {
    errBox.textContent = e.message || 'Could not send the reset email. Try again.';
    errBox.style.display = 'block';
  } finally {
    forgotBtn.disabled = false;
  }
});

async function routeAfterAuth() {
  // Onboarding is for users with no portfolio yet. An existing portfolio
  // (even with a dead brokerage link) routes to the dashboard — it shows a
  // reconnect banner; onboarding would trap a fully set-up user.
  try {
    const resp = await api('/portfolio/status');
    const status = await resp.json();
    window.location.href = (status.connected || status.has_positions)
      ? '/app/dashboard' : '/app/onboarding';
  } catch (e) {
    window.location.href = '/app/dashboard';
  }
}

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  errBox.style.display = 'none'; noticeBox.style.display = 'none';
  btn.disabled = true;
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  try {
    if (mode === 'signup') {
      // Without emailRedirectTo, Supabase sends the confirmation link to the
      // project-wide Site URL — wrong origin for every other environment.
      const { data, error } = await sb.auth.signUp({
        email, password,
        options: { emailRedirectTo: location.origin + '/app' },
      });
      if (error) throw error;
      if (data.session) { await routeAfterAuth(); return; }
      noticeBox.textContent = 'Check your email to confirm your account, then sign in.';
      noticeBox.style.display = 'block';
    } else {
      const { error } = await sb.auth.signInWithPassword({ email, password });
      if (error) throw error;
      await routeAfterAuth();
    }
  } catch (e) {
    errBox.textContent = e.message || 'Something went wrong. Try again.';
    errBox.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
});

// Already signed in? Skip the form — and don't flash it first: a synchronous
// localStorage peek hides it before paint, then the authoritative
// getSession() routes onward (or restores the form if the stored session
// turns out to be dead).
function showRedirecting(on) {
  form.style.display = on ? 'none' : '';
  document.querySelector('.switch-mode').style.display = on ? 'none' : '';
  document.getElementById('auth-redirecting').style.display = on ? 'flex' : 'none';
  document.getElementById('auth-title').textContent = on ? 'Welcome back' : 'Sign in';
  document.getElementById('auth-sub').textContent =
    on ? '' : 'Continue to your portfolio brief.';
}
let precheckHid = false;
try {
  const key = 'sb-' + new URL(SB_URL).hostname.split('.')[0] + '-auth-token';
  const s = JSON.parse(localStorage.getItem(key) || 'null');
  if (s && (s.refresh_token || (s.expires_at && s.expires_at * 1000 > Date.now()))) {
    precheckHid = true;
    showRedirecting(true);
  }
} catch (e) { /* fall through to the visible form */ }
getToken().then((t) => {
  if (t) { routeAfterAuth(); return; }
  if (precheckHid) showRedirecting(false);
});

// Entrance: same motion language as the landing page — brand copy rises in a
// stagger, the form follows. Skipped for reduced motion, a dead Motion CDN,
// or when a live session is about to redirect away anyway.
(function () {
  if (REDUCED || !window.Motion || precheckHid) return;
  const items = Array.from(document.querySelectorAll(
    '.auth-brand .logo, #brand-title, #brand-sub, .auth-step, .brand-note'
  )).filter((el) => el.offsetParent !== null);  // skip hidden steps / mobile aside
  const card = document.querySelector('.auth-form');
  const all = items.concat([card]);
  all.forEach((el) => {
    el.style.opacity = '0'; el.style.transform = 'translateY(14px)';
  });
  // Conceal now (before first paint), but start the clock only on the first
  // rendered frame: WAAPI timelines are clock-based, so on a slow load the
  // animation would otherwise finish behind a still-blank screen.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (items.length) {
      Motion.animate(items, { opacity: 1, transform: 'translateY(0px)' },
        { duration: 0.7, delay: Motion.stagger(0.09), ease: EASE });
    }
    Motion.animate(card, { opacity: 1, transform: 'translateY(0px)' },
      { duration: 0.7, delay: 0.25, ease: EASE });
  }));
  // Safety net (same idea as the landing page's revealAll): never leave the
  // page concealed if an animation gets interrupted.
  setTimeout(() => {
    all.forEach((el) => { el.style.opacity = ''; el.style.transform = ''; });
  }, 2500);
})();
"""


# --------------------------------------------------------------------------
# /app/reset — set a new password (Supabase recovery-link redirect)
# --------------------------------------------------------------------------

_RESET_BODY = """
<div class="auth-form-col" style="min-height:100dvh;">
  <div class="auth-form">
    <a class="logo" href="/" style="display:inline-block;margin-bottom:2rem;">Cir<span>via</span></a>
    <h1>Set a new password</h1>
    <p class="sub">Choose a new password for your account.</p>
    <div class="status-line" id="reset-checking">
      <span class="spinner"></span><span>Checking your reset link…</span>
    </div>
    <form id="reset-form" style="display:none;">
      <label for="new-password">New password</label>
      <input type="password" id="new-password" autocomplete="new-password" minlength="8" required>
      <p class="field-hint" style="display:block;">At least 8 characters.</p>
      <label for="confirm-password">Confirm new password</label>
      <input type="password" id="confirm-password" autocomplete="new-password" minlength="8" required>
      <button class="btn full" id="reset-btn" type="submit">Set new password</button>
    </form>
    <div class="error-box" id="reset-error"></div>
    <div class="notice-box" id="reset-notice"></div>
    <p class="switch-mode" id="reset-back" style="display:none;">
      <a href="/app">Back to sign in</a>
    </p>
  </div>
</div>
"""

_RESET_JS = """
const resetForm = document.getElementById('reset-form');
const resetErr = document.getElementById('reset-error');
const resetNotice = document.getElementById('reset-notice');
const resetChecking = document.getElementById('reset-checking');
let recoveryReady = false;

function showResetForm() {
  if (recoveryReady) return;
  recoveryReady = true;
  resetChecking.style.display = 'none';
  resetForm.style.display = 'block';
  riseIn(resetForm);
  document.getElementById('new-password').focus();
}

function showLinkInvalid() {
  if (recoveryReady) return;
  resetChecking.style.display = 'none';
  resetErr.textContent = 'This reset link is invalid or has expired. ' +
    'Request a new one from the sign-in page.';
  resetErr.style.display = 'block';
  document.getElementById('reset-back').style.display = 'block';
}

// supabase-js turns the recovery token in the URL hash into a session and
// fires PASSWORD_RECOVERY (or SIGNED_IN) once it has.
sb.auth.onAuthStateChange((event, session) => {
  if (event === 'PASSWORD_RECOVERY' || session) showResetForm();
});

// Expired/used links come back as #error=... instead of a token.
const resetHash = new URLSearchParams(location.hash.replace(/^#/, ''));
if (resetHash.get('error')) {
  showLinkInvalid();
} else {
  // Fallback: if no auth event lands, poll for a session a few times (slow
  // networks can take several seconds) before declaring the link invalid.
  const checkSession = async (triesLeft) => {
    if (recoveryReady) return;
    const { data } = await sb.auth.getSession();
    if (data.session) showResetForm();
    else if (triesLeft > 0) setTimeout(() => checkSession(triesLeft - 1), 2500);
    else showLinkInvalid();
  };
  setTimeout(() => checkSession(3), 2500);
}

resetForm.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  resetErr.style.display = 'none'; resetNotice.style.display = 'none';
  const password = document.getElementById('new-password').value;
  const confirm = document.getElementById('confirm-password').value;
  if (password !== confirm) {
    resetErr.textContent = 'Passwords do not match.';
    resetErr.style.display = 'block';
    return;
  }
  const btn = document.getElementById('reset-btn');
  btn.disabled = true;
  try {
    const { error } = await sb.auth.updateUser({ password });
    if (error) throw error;
    resetNotice.textContent = 'Password updated. Taking you to your dashboard…';
    resetNotice.style.display = 'block';
    setTimeout(() => { window.location.href = '/app/dashboard'; }, 900);
  } catch (e) {
    resetErr.textContent = e.message || 'Could not update your password. Try again.';
    resetErr.style.display = 'block';
    btn.disabled = false;
  }
});
"""


# --------------------------------------------------------------------------
# Shared delivery-channel picker (onboarding step 4 + dashboard settings card)
# --------------------------------------------------------------------------

_DELIVERY_PICKER_HTML = """
<div id="delivery-picker">
  <label>Notification method</label>
  <div class="channel-options" id="channel-options"></div>
  <div id="discord-connect-block" style="display:none;">
    <p class="muted-note" id="discord-connect-help" style="margin-top:0.4rem;"></p>
    <button class="btn full" id="discord-connect-btn">Connect Discord</button>
    <p class="muted-note" style="margin-top:0.5rem;"><button class="link-btn"
      id="discord-manual-btn">Paste a webhook URL instead</button></p>
  </div>
  <div id="dest-block" style="display:none;">
    <label id="dest-label" for="dest-input">Destination</label>
    <input id="dest-input" type="text">
    <p class="muted-note" id="dest-help" style="margin-top:0.4rem;"></p>
    <label class="consent-row" id="consent-row" style="display:none;">
      <input type="checkbox" id="consent-check">
      <span>I agree to receive automated daily texts from Cirvia at this number.
      Msg &amp; data rates may apply. Reply STOP to cancel, HELP for help.</span>
    </label>
    <button class="btn full" id="send-code-btn">Send verification code</button>
  </div>
  <div id="code-block" style="display:none;">
    <label for="code-input">Enter the 6-digit code we sent you</label>
    <input id="code-input" type="text" inputmode="numeric" maxlength="6"
      autocomplete="one-time-code" placeholder="123456">
    <button class="btn full" id="verify-btn">Verify</button>
    <p class="muted-note"><button class="link-btn" id="resend-btn">Resend code</button></p>
  </div>
  <div class="error-box" id="delivery-error"></div>
</div>
"""

_DELIVERY_JS = """
// Shared by onboarding (prefs step) and the dashboard schedule editor.
const COMMON_TZS = ['America/Toronto','America/Vancouver','America/Edmonton',
  'America/Winnipeg','America/Halifax','America/St_Johns','America/New_York',
  'America/Chicago','America/Denver','America/Los_Angeles','Europe/London',
  'Europe/Paris'];

function fillTzSelect(sel, current) {
  const guess = current || Intl.DateTimeFormat().resolvedOptions().timeZone;
  const list = COMMON_TZS.includes(guess) ? COMMON_TZS : [guess, ...COMMON_TZS];
  sel.innerHTML = '';
  for (const z of list) {
    const o = document.createElement('option');
    o.value = z; o.textContent = z; if (z === guess) o.selected = true;
    sel.appendChild(o);
  }
}

const CHANNEL_META = {
  sms: { label: 'Text message', type: 'tel', destLabel: 'Phone number',
    placeholder: '+14165550123',
    help: 'Use full international format, e.g. +14165550123. Reply STOP anytime to unsubscribe.' },
  email: { label: 'Email', type: 'email', destLabel: 'Email address',
    placeholder: 'you@example.com', help: '' },
  discord: { label: 'Discord', type: 'url', destLabel: 'Discord webhook URL',
    placeholder: 'https://discord.com/api/webhooks/…',
    help: 'In Discord: Server Settings \\u2192 Integrations \\u2192 Webhooks \\u2192 New Webhook, then copy the URL. A free personal server works.' },
};

let dpChannel = null;
let dpOnVerified = null;
let dpBound = false;
let dpDiscordOauth = false;  // server offers one-click OAuth connect

function dpError(msg) {
  const box = document.getElementById('delivery-error');
  if (msg) { box.textContent = msg; box.style.display = 'block'; }
  else { box.style.display = 'none'; }
}

function dpSelect(ch, el, existing) {
  if (dpChannel !== ch) document.getElementById('dest-input').value = '';
  dpChannel = ch;
  document.querySelectorAll('.channel-opt').forEach(
    (o) => o.classList.toggle('selected', o === el));
  const meta = CHANNEL_META[ch];
  // Discord with OAuth configured: offer one-click connect instead of the
  // paste-a-webhook form (still reachable via the manual link).
  const useOauth = ch === 'discord' && dpDiscordOauth;
  document.getElementById('discord-connect-block').style.display =
    useOauth ? 'block' : 'none';
  if (useOauth) {
    document.getElementById('discord-connect-help').textContent =
      (existing && existing.destination_masked
        ? 'Currently ' + existing.destination_masked + '. Connecting again replaces it. '
        : '') +
      "Pick a server and channel on Discord \\u2014 we'll set up the webhook for you.";
  }
  document.getElementById('dest-block').style.display = useOauth ? 'none' : 'block';
  document.getElementById('code-block').style.display = 'none';
  dpError(null);
  const input = document.getElementById('dest-input');
  input.type = meta.type; input.placeholder = meta.placeholder;
  document.getElementById('dest-label').textContent = meta.destLabel;
  let help = meta.help;
  if (existing && existing.destination_masked) {
    help = 'Currently ' + existing.destination_masked +
      (existing.verified ? ' (verified). Enter a new destination to change it.'
                         : ' (unverified).') + (help ? ' ' + help : '');
  }
  document.getElementById('dest-help').textContent = help;
  document.getElementById('consent-row').style.display = ch === 'sms' ? 'flex' : 'none';
}

function dpReset() {
  dpChannel = null;
  document.getElementById('discord-connect-block').style.display = 'none';
  document.getElementById('dest-block').style.display = 'none';
  document.getElementById('code-block').style.display = 'none';
  document.getElementById('dest-input').value = '';
  document.getElementById('code-input').value = '';
  document.getElementById('consent-check').checked = false;
  dpError(null);
}

async function dpSendCode() {
  const btn = document.getElementById('send-code-btn');
  const destination = document.getElementById('dest-input').value.trim();
  const consent = document.getElementById('consent-check').checked;
  if (!dpChannel || !destination) { dpError('Pick a method and enter a destination.'); return; }
  if (dpChannel === 'sms' && !consent) { dpError('Please check the consent box to receive texts.'); return; }
  btn.disabled = true; dpError(null);
  try {
    const resp = await api('/me/notifications/channel', {
      method: 'POST',
      body: JSON.stringify({ channel: dpChannel, destination, consent }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Could not send the code');
    }
    document.getElementById('code-block').style.display = 'block';
    riseIn(document.getElementById('code-block'));
    document.getElementById('code-input').focus();
  } catch (e) { dpError(e.message); }
  finally { btn.disabled = false; }
}

async function dpVerify() {
  const btn = document.getElementById('verify-btn');
  const code = document.getElementById('code-input').value.trim();
  if (!code) return;
  btn.disabled = true; dpError(null);
  try {
    const resp = await api('/me/notifications/verify', {
      method: 'POST',
      body: JSON.stringify({ channel: dpChannel, code }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Verification failed');
    if (dpOnVerified) dpOnVerified(data);
  } catch (e) { dpError(e.message); }
  finally { btn.disabled = false; }
}

async function dpDiscordConnect() {
  const btn = document.getElementById('discord-connect-btn');
  btn.disabled = true; dpError(null);
  try {
    const ret = window.location.pathname.indexOf('onboarding') !== -1
      ? 'onboarding' : 'settings';
    const resp = await api('/me/notifications/discord/connect-url?return_to=' + ret);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Discord connect is unavailable');
    window.location.href = data.url;  // Discord shows its server+channel picker
  } catch (e) { dpError(e.message); btn.disabled = false; }
}

async function initDeliveryPicker(onVerified) {
  dpOnVerified = onVerified;
  if (!dpBound) {
    dpBound = true;
    document.getElementById('send-code-btn').addEventListener('click', dpSendCode);
    document.getElementById('resend-btn').addEventListener('click', dpSendCode);
    document.getElementById('verify-btn').addEventListener('click', dpVerify);
    document.getElementById('code-input').addEventListener('keydown',
      (e) => { if (e.key === 'Enter') dpVerify(); });
    document.getElementById('discord-connect-btn')
      .addEventListener('click', dpDiscordConnect);
    document.getElementById('discord-manual-btn').addEventListener('click', () => {
      document.getElementById('discord-connect-block').style.display = 'none';
      document.getElementById('dest-block').style.display = 'block';
    });
  }
  dpReset();
  try {
    const info = await (await api('/me/notifications')).json();
    dpDiscordOauth = !!info.discord_oauth;
    const registered = {};
    for (const c of info.channels || []) registered[c.channel] = c;
    const opts = document.getElementById('channel-options');
    const optEls = {};
    opts.innerHTML = '';
    for (const ch of info.available_channels) {
      const meta = CHANNEL_META[ch];
      if (!meta) continue;
      const el = document.createElement('div');
      el.className = 'channel-opt';
      el.textContent = meta.label;
      el.addEventListener('click', () => dpSelect(ch, el, registered[ch]));
      opts.appendChild(el);
      optEls[ch] = el;
    }
    // Start from the user's current channel, or the only one available.
    const shown = Object.keys(optEls);
    const pre = optEls[info.preferred_channel] ? info.preferred_channel
      : (shown.length === 1 ? shown[0] : null);
    if (pre) dpSelect(pre, optEls[pre], registered[pre]);
    return info;
  } catch (e) { return null; }
}
"""


# --------------------------------------------------------------------------
# /app/onboarding — connect brokerage -> sync -> preferences -> delivery
# --------------------------------------------------------------------------

_ONBOARDING_BODY = """
<h1 id="ob-title">Set up Cirvia</h1>
<div class="ob-layout">
  <div class="ob-rail" aria-label="Setup progress">
    <div class="ob-step active" id="step-1">
      <span class="n">1</span><span class="t">About you</span>
      <span class="d">How you invest, so Cirvia can speak your language.</span>
    </div>
    <div class="ob-step" id="step-2">
      <span class="n">2</span><span class="t">Connect your brokerage</span>
      <span class="d">Link your brokerage through SnapTrade's secure portal.</span>
    </div>
    <div class="ob-step" id="step-3">
      <span class="n">3</span><span class="t">Sync your holdings</span>
      <span class="d">Cirvia pulls your positions, read-only.</span>
    </div>
    <div class="ob-step" id="step-4">
      <span class="n">4</span><span class="t">Risk comfort</span>
      <span class="d">See your real portfolio at three risk levels and pick one.</span>
    </div>
    <div class="ob-step" id="step-5">
      <span class="n">5</span><span class="t">Choose holdings</span>
      <span class="d">Pick which positions get news on Free.</span>
    </div>
    <div class="ob-step" id="step-6">
      <span class="n">6</span><span class="t">Digest preferences</span>
      <span class="d">Pick when your morning brief arrives.</span>
    </div>
    <div class="ob-step" id="step-7">
      <span class="n">7</span><span class="t">Delivery</span>
      <span class="d">Get it by text, email, or Discord.</span>
    </div>
  </div>
  <div class="ob-content">

  <div class="step-panel q-flow" id="panel-profile">
    <div class="q-head">
      <button class="q-back" id="q-back" type="button"
        style="visibility:hidden;">&larr; Back</button>
      <span class="q-count" id="q-count">1 of 3</span>
    </div>
    <div class="q-track" aria-hidden="true">
      <div class="q-track-fill" id="q-track-fill" style="width:33.34%;"></div>
    </div>

    <div class="q-stage" id="q-stage">
      <section class="q-screen" id="qs-experience">
        <h2 class="q-title">How long have you been investing?</h2>
        <p class="q-sub">Three quick questions so your digest, news, and risk
        analysis fit how you actually invest.</p>
        <div class="q-opts" id="q-experience" data-single="1" role="radiogroup"
          aria-label="How long have you been investing?">
          <div class="q-opt" data-v="new" role="radio" aria-checked="false" tabindex="0"><span class="k">1</span>Just starting<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="lt_1y" role="radio" aria-checked="false" tabindex="0"><span class="k">2</span>Under a year<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="1_5y" role="radio" aria-checked="false" tabindex="0"><span class="k">3</span>1&ndash;5 years<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="5_10y" role="radio" aria-checked="false" tabindex="0"><span class="k">4</span>5&ndash;10 years<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="10y_plus" role="radio" aria-checked="false" tabindex="0"><span class="k">5</span>10+ years<span class="ck">&#10003;</span></div>
        </div>
      </section>

      <section class="q-screen" id="qs-goals" style="display:none;">
        <h2 class="q-title">What are you investing for?</h2>
        <p class="q-sub">Pick all that apply.</p>
        <div class="q-opts" id="q-goals" role="group"
          aria-label="What are you investing for?">
          <div class="q-opt" data-v="grow_long_term" role="checkbox" aria-checked="false" tabindex="0"><span class="k">1</span>Grow wealth long-term<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="income" role="checkbox" aria-checked="false" tabindex="0"><span class="k">2</span>Income from my investments<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="preserve_capital" role="checkbox" aria-checked="false" tabindex="0"><span class="k">3</span>Protect what I've built<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="short_term_gains" role="checkbox" aria-checked="false" tabindex="0"><span class="k">4</span>Short-term trading gains<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="retirement" role="checkbox" aria-checked="false" tabindex="0"><span class="k">5</span>Retirement<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="big_purchase" role="checkbox" aria-checked="false" tabindex="0"><span class="k">6</span>A big purchase<span class="ck">&#10003;</span></div>
        </div>
      </section>

      <section class="q-screen" id="qs-horizon" style="display:none;">
        <h2 class="q-title">When do you typically act on an investment?</h2>
        <p class="q-sub">Your digest and news get framed around this window.</p>
        <div class="q-opts" id="q-horizon" data-single="1" role="radiogroup"
          aria-label="When do you typically act on an investment?">
          <div class="q-opt" data-v="days" role="radio" aria-checked="false" tabindex="0"><span class="k">1</span>Within days<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="weeks_months" role="radio" aria-checked="false" tabindex="0"><span class="k">2</span>Weeks to months<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="years" role="radio" aria-checked="false" tabindex="0"><span class="k">3</span>Years<span class="ck">&#10003;</span></div>
          <div class="q-opt" data-v="decade_plus" role="radio" aria-checked="false" tabindex="0"><span class="k">4</span>A decade or more<span class="ck">&#10003;</span></div>
        </div>
      </section>
    </div>

    <div class="q-foot">
      <button class="btn" id="profile-btn">Continue</button>
      <a href="#" id="profile-skip" class="q-skip">Skip for now</a>
    </div>
  </div>

  <div class="step-panel" id="panel-connect" style="display:none;">
    <h2>Connect your brokerage</h2>
    <p>Link your brokerage through SnapTrade's secure portal. Read-only: Cirvia can
    never trade or move money, and your brokerage password is never shared with us.</p>
    <div class="status-line" id="connect-status" style="display:none;">
      <span class="spinner"></span><span id="connect-status-text">Waiting for connection…</span>
    </div>
    <button class="btn full" id="connect-btn">Connect brokerage</button>
    <button class="btn ghost full" id="connected-btn" style="display:none;">I've finished connecting</button>
    <div class="error-box" id="connect-error"></div>
    <p class="muted-note">A new tab will open. Come back here when you're done.</p>
    <p class="muted-note" style="text-align:center;"><a href="#" id="manual-link">No
    brokerage link? Type your holdings instead</a></p>
    <div id="manual-panel" style="display:none;">
      <p class="muted-note">Ticker and share count, one per row — e.g.
      <strong>NVDA</strong> or <strong>RY.TO</strong>. You can link a brokerage
      later to keep this synced automatically.</p>
      <div id="manual-rows"></div>
      <p class="muted-note"><a href="#" id="manual-add-row">+ Add another</a></p>
      <button class="btn full" id="manual-save-btn">Analyze these holdings</button>
      <div class="error-box" id="manual-error"></div>
    </div>
  </div>

  <div class="step-panel" id="panel-sync" style="display:none;">
    <h2>Syncing your holdings</h2>
    <div class="status-line" id="sync-status-line"><span class="spinner"></span>
    <span id="sync-status-text">Pulling your positions…</span></div>
    <div class="error-box" id="sync-error"></div>
    <button class="btn full" id="sync-retry-btn" style="display:none;">Try again</button>
  </div>

  <div class="step-panel" id="panel-risk-picker" style="display:none;">
    <h2>Pick your risk comfort</h2>
    <p id="posture-intro">Here's <strong>your actual portfolio</strong> replayed
    5,000 times over the next year at three risk levels. The shaded range holds
    90% of the simulated outcomes, and all three charts share one scale &mdash;
    wider means wilder. Which ride looks right to you?</p>
    <div class="status-line" id="posture-status"><span class="spinner"></span>
    <span id="posture-status-text">Crunching two years of your holdings' history&hellip;</span></div>
    <div class="posture-cards" id="posture-cards" style="display:none;"></div>
    <div class="error-box" id="posture-error"></div>
    <button class="btn full" id="posture-retry-btn" style="display:none;">Try again</button>
    <button class="btn full" id="posture-btn" style="display:none;" disabled>Continue</button>
    <p class="muted-note" style="text-align:center;"><a href="#" id="posture-skip">Skip
    this step</a> (not a commitment; it only tunes how Cirvia frames risk for you)</p>
  </div>

  <div class="step-panel" id="panel-watchlist" style="display:none;">
    <h2>Choose holdings to follow</h2>
    <p>On the Free plan, Cirvia tracks news for up to <strong id="wl-limit">3</strong>
    holdings. Your largest positions are pre-selected — adjust to taste.</p>
    <div class="watchlist-grid" id="watchlist-grid"></div>
    <p class="muted-note" id="wl-hint"></p>
    <button class="btn full" id="watchlist-btn">Continue</button>
    <div class="error-box" id="watchlist-error"></div>
  </div>

  <div class="step-panel" id="panel-prefs" style="display:none;">
    <h2>Digest preferences</h2>
    <p>When should your morning digest arrive?</p>
    <label for="tz">Timezone</label>
    <select id="tz"></select>
    <label for="send-time">Send time</label>
    <input type="time" id="send-time" value="09:00">
    <button class="btn full" id="prefs-btn">Continue</button>
    <div class="error-box" id="prefs-error"></div>
  </div>

  <div class="step-panel" id="panel-delivery" style="display:none;">
    <h2>How should we reach you?</h2>
    <p>Your morning digest and alerts, delivered where you'll actually see them.
    We send a one-time code to confirm it works.</p>
""" + _DELIVERY_PICKER_HTML + """
    <p class="muted-note" style="text-align:center;"><a href="/app/dashboard">Skip for
    now</a> — you can set this up anytime from the dashboard.</p>
  </div>

  </div>
</div>
"""

_ONBOARDING_JS = """
requireSession();

const tzSel = document.getElementById('tz');
fillTzSelect(tzSel);

const PANELS = ['panel-profile','panel-connect','panel-sync','panel-risk-picker',
  'panel-watchlist','panel-prefs','panel-delivery'];
const STEP_IDS = ['step-1','step-2','step-3','step-4','step-5','step-6','step-7'];

// Re-personalization mode (?personalize=1, from the dashboard prompt or
// Settings): only the two profile steps, no setup rail, back to the dashboard
// at the end. Never gates anything — it's always reachable AND always skippable.
const PERSONALIZE = new URLSearchParams(window.location.search).get('personalize') === '1';
if (PERSONALIZE) {
  document.getElementById('ob-title').textContent = 'Personalize your Cirvia';
  document.querySelector('.ob-rail').style.display = 'none';
  // Full-page focus mode: the title becomes a quiet topline and the active
  // question owns the viewport (see .personalize rules in _APP_CSS).
  document.querySelector('main').classList.add('personalize');
}

function showPanel(id) {
  let changed = false;
  for (const p of PANELS) {
    const el = document.getElementById(p);
    const show = p === id;
    if (show && el.style.display === 'none') changed = true;
    el.style.display = show ? 'block' : 'none';
  }
  if (changed) riseIn(document.getElementById(id));
  const current = PANELS.indexOf(id) + 1;
  for (let n = 1; n <= PANELS.length; n++) {
    const step = document.getElementById('step-' + n);
    const wasDone = step.classList.contains('done');
    step.classList.toggle('active', n === current);
    step.classList.toggle('done', n < current);
    const marker = step.querySelector('.n');
    marker.textContent = n < current ? '\\u2713' : String(n);
    // A step that just completed gets a small tick pulse on its marker.
    if (!wasDone && n < current && !REDUCED && window.Motion) {
      Motion.animate(marker, { scale: [1, 1.18, 1] }, { duration: 0.3, ease: EASE });
    }
  }
}

function showError(id, msg) {
  const box = document.getElementById(id);
  box.textContent = msg; box.style.display = 'block';
}

let pollTimer = null;

async function pollStatus() {
  try {
    const resp = await api('/portfolio/status');
    const s = await resp.json();
    if (s.connected) {
      clearInterval(pollTimer); pollTimer = null;
      await runSync();
    }
  } catch (e) { /* keep polling */ }
}

async function afterSync() {
  try {
    const me = await (await api('/me')).json();
    const pf = await (await api('/portfolio')).json();
    // Largest positions first, matching the digest's own fallback ordering.
    const byValue = [...(pf.positions || [])].sort(
      (a, b) => (b.market_value ?? -1) - (a.market_value ?? -1));
    const tickers = [...new Set(byValue.map((p) => p.ticker))];
    const limit = me.digest_tickers_limit || 3;
    if (me.plan === 'pro' || tickers.length <= limit) {
      if (tickers.length) {
        await api('/me', {
          method: 'PATCH',
          body: JSON.stringify({ digest_tickers: tickers.slice(0, limit) }),
        });
      }
      showPanel('panel-prefs');
      return;
    }
    document.getElementById('wl-limit').textContent = String(limit);
    buildWatchlistPicker(tickers, limit);
    showPanel('panel-watchlist');
  } catch (e) {
    showPanel('panel-prefs');
  }
}

const wlSelected = new Set();
let wlLimit = 3;

function wlHint() {
  document.getElementById('wl-hint').textContent =
    wlSelected.size + ' of up to ' + wlLimit + ' selected';
}

function buildWatchlistPicker(tickers, limit) {
  wlSelected.clear();
  wlLimit = limit;
  const grid = document.getElementById('watchlist-grid');
  grid.innerHTML = '';
  for (const t of tickers) {
    const el = document.createElement('div');
    el.className = 'watchlist-opt';
    el.textContent = t;
    el.dataset.ticker = t;
    if (wlSelected.size < limit) {
      wlSelected.add(t);
      el.classList.add('selected');
    }
    el.addEventListener('click', () => {
      if (wlSelected.has(t)) {
        wlSelected.delete(t);
        el.classList.remove('selected');
      } else if (wlSelected.size < limit) {
        wlSelected.add(t);
        el.classList.add('selected');
      }
      wlHint();
    });
    grid.appendChild(el);
  }
  wlHint();
  staggerIn([...grid.children]);
}

document.getElementById('watchlist-btn').addEventListener('click', async () => {
  const btn = document.getElementById('watchlist-btn');
  btn.disabled = true;
  document.getElementById('watchlist-error').style.display = 'none';
  try {
    if (wlSelected.size === 0) {
      throw new Error('Select at least one holding.');
    }
    const resp = await api('/me', {
      method: 'PATCH',
      body: JSON.stringify({ digest_tickers: [...wlSelected] }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Could not save watchlist');
    }
    showPanel('panel-prefs');
  } catch (e) {
    showError('watchlist-error', e.message);
  } finally {
    btn.disabled = false;
  }
});

async function runSync(attempt = 0) {
  showPanel('panel-sync');
  // Reset from a previous failed attempt (retry path).
  document.getElementById('sync-status-line').style.display = '';
  document.getElementById('sync-retry-btn').style.display = 'none';
  document.getElementById('sync-error').style.display = 'none';
  try {
    const resp = await api('/portfolio/sync', { method: 'POST' });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      const detail = err.detail || 'Sync failed';
      // Right after connecting, SnapTrade needs ~30-60s to import accounts.
      if (detail.startsWith('No investment accounts found') && attempt < 8) {
        document.getElementById('sync-status-text').textContent =
          'Waiting for your brokerage to finish importing accounts…';
        setTimeout(() => runSync(attempt + 1), 8000);
        return;
      }
      throw new Error(detail);
    }
    const result = await resp.json();
    document.getElementById('sync-status-text').textContent =
      'Synced ' + result.positions_upserted + ' positions across ' +
      result.accounts_synced + ' accounts.';
    // Kick off the Monte Carlo fetch now: the first call may backfill two
    // years of prices, so starting during this beat hides most of the wait.
    startProjections();
    setTimeout(showRiskPicker, 900);
  } catch (e) {
    // Stop the spinner and offer a retry so a transient failure isn't a dead end.
    document.getElementById('sync-status-line').style.display = 'none';
    document.getElementById('sync-retry-btn').style.display = '';
    showError('sync-error', e.message);
  }
}

document.getElementById('sync-retry-btn').addEventListener('click', () => runSync());

document.getElementById('connect-btn').addEventListener('click', async () => {
  const btn = document.getElementById('connect-btn');
  btn.disabled = true;
  document.getElementById('connect-error').style.display = 'none';
  try {
    const regResp = await api('/portfolio/snaptrade/register', { method: 'POST' });
    if (!regResp.ok) {
      const err = await regResp.json().catch(() => ({}));
      throw new Error(err.detail || 'Brokerage registration failed');
    }
    const resp = await api('/portfolio/connect-url');
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Could not get the connection link');
    }
    const { url } = await resp.json();
    window.open(url, '_blank');
    document.getElementById('connect-status').style.display = 'flex';
    document.getElementById('connected-btn').style.display = 'block';
    if (!pollTimer) pollTimer = setInterval(pollStatus, 5000);
  } catch (e) {
    showError('connect-error', e.message);
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('connected-btn').addEventListener('click', pollStatus);

// --- manual holdings fallback: convert the users who won't link a brokerage
// to an unknown site on day one; SnapTrade can upsell later.

function manualAddRow(ticker = '', qty = '') {
  const row = document.createElement('div');
  row.className = 'manual-row';
  row.style.cssText = 'display:flex;gap:0.5rem;margin-top:0.5rem;';
  row.innerHTML =
    '<input type="text" placeholder="Ticker (e.g. NVDA)" class="m-ticker" ' +
    'style="flex:2;text-transform:uppercase;" value="' + ticker + '">' +
    '<input type="number" placeholder="Shares" class="m-qty" min="0" ' +
    'step="any" style="flex:1;" value="' + qty + '">';
  document.getElementById('manual-rows').appendChild(row);
}

document.getElementById('manual-link').addEventListener('click', (e) => {
  e.preventDefault();
  const panel = document.getElementById('manual-panel');
  if (panel.style.display === 'none') {
    panel.style.display = 'block';
    if (!document.querySelector('.manual-row')) {
      for (let i = 0; i < 3; i++) manualAddRow();
    }
  } else {
    panel.style.display = 'none';
  }
});

document.getElementById('manual-add-row').addEventListener('click', (e) => {
  e.preventDefault();
  manualAddRow();
});

document.getElementById('manual-save-btn').addEventListener('click', async () => {
  const btn = document.getElementById('manual-save-btn');
  document.getElementById('manual-error').style.display = 'none';
  const positions = [];
  document.querySelectorAll('.manual-row').forEach((row) => {
    const t = row.querySelector('.m-ticker').value.trim().toUpperCase();
    const q = parseFloat(row.querySelector('.m-qty').value);
    if (t && q > 0) positions.push({ ticker: t, quantity: q });
  });
  if (!positions.length) {
    showError('manual-error', 'Add at least one ticker with a share count.');
    return;
  }
  btn.disabled = true;
  try {
    const resp = await api('/portfolio/manual', {
      method: 'POST',
      body: JSON.stringify({ positions }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Could not save your holdings');
    }
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    // Same beat as a brokerage sync: straight to the risk picker.
    startProjections();
    showRiskPicker();
  } catch (e) {
    showError('manual-error', e.message);
  } finally {
    btn.disabled = false;
  }
});

// --- step 1: investor profile, one question per screen ------------------------
// Typeform-style: a single question owns the stage; single-select questions
// advance on their own, multi-select waits for Continue. Transitions are
// direction-aware (forward exits up, back exits down) via Motion, and every
// path degrades to an instant swap for reduced-motion or a failed CDN load.

const obProfile = { experience: null, goals: [], horizon: null };
const Q_SCREENS = ['qs-experience', 'qs-goals', 'qs-horizon'];
let qIndex = 0;
let qBusy = false;

function qChrome() {
  document.getElementById('q-count').textContent =
    (qIndex + 1) + ' of ' + Q_SCREENS.length;
  document.getElementById('q-back').style.visibility =
    qIndex === 0 ? 'hidden' : 'visible';
  const fill = document.getElementById('q-track-fill');
  const w = (((qIndex + 1) / Q_SCREENS.length) * 100).toFixed(2) + '%';
  if (REDUCED || !window.Motion) fill.style.width = w;
  else Motion.animate(fill, { width: w }, { duration: 0.35, ease: EASE });
}

async function qGo(next, dir) {
  if (qBusy || next === qIndex || next < 0 || next >= Q_SCREENS.length) return;
  qBusy = true;
  const from = document.getElementById(Q_SCREENS[qIndex]);
  const to = document.getElementById(Q_SCREENS[next]);
  qIndex = next;
  qChrome();
  if (REDUCED || !window.Motion) {
    from.style.display = 'none';
    to.style.display = 'block';
    qBusy = false;
    return;
  }
  try {
    await Motion.animate(from,
      { opacity: [1, 0], translate: ['0px 0px', '0px ' + (-14 * dir) + 'px'] },
      { duration: 0.16, ease: EASE });
  } catch (e) { /* interrupted; swap anyway */ }
  from.style.display = 'none';
  from.style.opacity = '';
  from.style.translate = '';
  to.style.display = 'block';
  Motion.animate(to,
    { opacity: [0, 1], translate: ['0px ' + (18 * dir) + 'px', '0px 0px'] },
    { duration: 0.26, ease: EASE });
  Motion.animate(to.querySelectorAll('.q-opt'),
    { opacity: [0, 1], translate: ['0px 10px', '0px 0px'] },
    { duration: 0.3, delay: Motion.stagger(0.035, { startDelay: 0.06 }), ease: EASE });
  qBusy = false;
}

function qNext() {
  if (qIndex < Q_SCREENS.length - 1) {
    qGo(qIndex + 1, 1);
  } else {
    readProfileChips();
    leaveProfilePanel();
  }
}

function qPulse(el) {
  if (REDUCED || !window.Motion) return;
  Motion.animate(el, { scale: [1, 0.97, 1] }, { duration: 0.2, ease: EASE });
}

function initChips(id) {
  const group = document.getElementById(id);
  const single = group.dataset.single === '1';
  group.querySelectorAll('.q-opt').forEach((el) => {
    const pick = () => {
      if (single) {
        const was = el.classList.contains('selected');
        group.querySelectorAll('.q-opt').forEach((o) => {
          o.classList.remove('selected');
          o.setAttribute('aria-checked', 'false');
        });
        if (!was) {
          el.classList.add('selected');
          el.setAttribute('aria-checked', 'true');
          qPulse(el);
          // Let the selection state land before the screen moves on.
          setTimeout(qNext, 300);
        }
      } else {
        const on = el.classList.toggle('selected');
        el.setAttribute('aria-checked', String(on));
        if (on) qPulse(el);
      }
    };
    el.addEventListener('click', pick);
    el.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); }
    });
  });
}
['q-experience', 'q-goals', 'q-horizon'].forEach(initChips);

// Number keys pick an option, Enter advances — active only while the profile
// step is on screen and focus isn't in a form control.
document.addEventListener('keydown', (ev) => {
  if (document.getElementById('panel-profile').style.display === 'none') return;
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
  const tag = (ev.target.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
  const isOpt = ev.target.classList && ev.target.classList.contains('q-opt');
  if (ev.key === 'Enter' && !isOpt) { ev.preventDefault(); qNext(); return; }
  const n = parseInt(ev.key, 10);
  if (!Number.isNaN(n) && n >= 1 && n <= 9) {
    const opts = document.querySelectorAll(
      '#' + Q_SCREENS[qIndex].replace('qs-', 'q-') + ' .q-opt');
    if (opts[n - 1]) opts[n - 1].click();
  }
});

// First question's options rise in on load (skipped when a resume/OAuth-return
// branch below immediately routes to a later panel — the animation ends on a
// hidden element, which is harmless).
if (!REDUCED && window.Motion) {
  Motion.animate(document.querySelectorAll('#qs-experience .q-opt'),
    { opacity: [0, 1], translate: ['0px 10px', '0px 0px'] },
    { duration: 0.32, delay: Motion.stagger(0.04, { startDelay: 0.08 }), ease: EASE });
}

function readProfileChips() {
  const one = (id) => {
    const el = document.querySelector('#' + id + ' .q-opt.selected');
    return el ? el.dataset.v : null;
  };
  obProfile.experience = one('q-experience');
  obProfile.horizon = one('q-horizon');
  obProfile.goals = [...document.querySelectorAll('#q-goals .q-opt.selected')]
    .map((el) => el.dataset.v);
}

async function leaveProfilePanel() {
  if (!PERSONALIZE) { showPanel('panel-connect'); return; }
  // Re-personalizing: the portfolio usually already exists, so jump straight
  // to the risk picker; fall back to the connect flow when it doesn't.
  try {
    const s = await (await api('/portfolio/status')).json();
    if (s.connected || s.has_positions) { startProjections(); await showRiskPicker(); return; }
  } catch (e) { /* fall through to connect */ }
  showPanel('panel-connect');
}

document.getElementById('profile-btn').addEventListener('click', qNext);
document.getElementById('q-back').addEventListener('click', () => qGo(qIndex - 1, -1));
document.getElementById('profile-skip').addEventListener('click', (e) => {
  e.preventDefault();
  readProfileChips();
  leaveProfilePanel();
});

// --- step 4: risk-comfort picker (live Monte Carlo of the user's book) -------

const POSTURE_ORDER = ['defensive', 'current', 'aggressive'];
const POSTURE_META = {
  defensive: { title: 'A smoother ride', sub: 'your holdings, dialed to lower volatility' },
  current: { title: 'Your current mix', sub: 'your holdings as they are today' },
  aggressive: { title: 'Higher octane', sub: 'your holdings, dialed to higher volatility' },
};
let projectionsPromise = null;
let chosenPosture = null;

function startProjections() {
  if (!projectionsPromise) {
    projectionsPromise = api('/me/profile/projections').then(async (resp) => {
      if (!resp.ok) throw new Error('Projections are unavailable right now.');
      return resp.json();
    });
    // A failed prewarm must not poison the picker's own retry.
    projectionsPromise.catch(() => {});
  }
  return projectionsPromise;
}

const obPct = (n) => (n >= 0 ? '+' : '\\u2212') + Math.abs(n).toFixed(0) + '%';

// All three cards share the same [lo, hi] percent domain, so a calm book is a
// visibly thin wedge and a wild one fills the frame — the shapes carry the
// comparison. The right gutter holds the great-year / brutal-year tip labels.
function miniFan(p, lo, hi) {
  const b = p.bands_pct;
  const m = b.p50.length, W = 260, H = 120, padL = 4, padR = 74, padT = 7, padB = 7;
  const span = Math.max(1e-6, hi - lo);
  const x = (i) => padL + (i / (m - 1)) * (W - padL - padR);
  const y = (v) => padT + (1 - (v - lo) / span) * (H - padT - padB);
  const line = (arr) => arr.map((v, i) =>
    (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join(' ');
  const band = (top, bot) => 'M' +
    top.map((v, i) => x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join(' L') +
    ' L' + bot.map((v, i) => x(i).toFixed(1) + ' ' + y(v).toFixed(1)).reverse().join(' L') + ' Z';
  const cad = p.terminal_cad, tp = p.terminal_pct;
  const great = cad ? fmtCadOb(cad.p95) : obPct(tp.p95);
  const brutal = cad ? fmtCadOb(cad.p5) : obPct(tp.p5);
  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block;"' +
    ' role="img" aria-label="Simulated one-year outcome range: a great year ' + great +
    ', a brutal year ' + brutal + '">';
  if (lo < 0 && hi > 0) {
    svg += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + y(0) + '" y2="' + y(0) + '" class="mf-zero"></line>';
  }
  svg += '<path d="' + band(b.p95, b.p5) + '" class="mf-outer"></path>';
  svg += '<path d="' + band(b.p75, b.p25) + '" class="mf-inner"></path>';
  // pathLength=1 normalizes the dash math so the median can draw in on load.
  svg += '<path d="' + line(b.p50) + '" class="mf-median" pathLength="1"></path>';
  // Tip labels, nudged apart so a thin (defensive) wedge can't overlap them.
  let yTop = y(b.p95[m - 1]) + 3.5, yBot = y(b.p5[m - 1]) + 3.5;
  yTop = Math.max(yTop, 10);
  yBot = Math.min(Math.max(yBot, yTop + 13), H - 3);
  yTop = Math.min(yTop, yBot - 13);
  svg += '<text x="' + (W - padR + 7) + '" y="' + yTop.toFixed(1) + '" class="mf-endlbl ' +
    (tp.p95 >= 0 ? 'pos' : 'neg') + '">' + great + '</text>';
  svg += '<text x="' + (W - padR + 7) + '" y="' + yBot.toFixed(1) + '" class="mf-endlbl ' +
    (tp.p5 >= 0 ? 'pos' : 'neg') + '">' + brutal + '</text>';
  return svg + '</svg>';
}

function renderPostures(data) {
  document.getElementById('posture-status').style.display = 'none';
  const box = document.getElementById('posture-cards');
  box.style.display = 'grid';
  if (data.fallback) {
    document.getElementById('posture-intro').innerHTML =
      'These are <strong>typical portfolios</strong> at three risk levels, replayed ' +
      '5,000 times over the next year &mdash; yours will appear in the Risk Lab once ' +
      'there\\u2019s enough price history. The shaded range holds 90% of outcomes, and ' +
      'all three charts share one scale &mdash; wider means wilder. ' +
      'Which ride looks right to you?';
  } else if (data.portfolio_value_cad) {
    document.getElementById('posture-intro').innerHTML =
      'Here\\u2019s <strong>your actual portfolio</strong> &mdash; ' +
      fmtCadOb(data.portfolio_value_cad) + ' today &mdash; replayed 5,000 times over ' +
      'the next year at three risk levels. The shaded range holds 90% of the simulated ' +
      'outcomes, and all three charts share one scale &mdash; wider means wilder. ' +
      'Which ride looks right to you?';
  }
  // One percent-domain across all three fans, so their shapes are comparable.
  const avail = POSTURE_ORDER.map((k) => data.postures[k]).filter(Boolean);
  const fanLo = Math.min.apply(null, avail.map((p) => Math.min.apply(null, p.bands_pct.p5)));
  const fanHi = Math.max.apply(null, avail.map((p) => Math.max.apply(null, p.bands_pct.p95)));
  box.innerHTML = '';
  POSTURE_ORDER.forEach((key) => {
    const p = data.postures[key];
    if (!p) return;
    const meta = POSTURE_META[key];
    const card = document.createElement('div');
    card.className = 'posture-card';
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    const cad = p.terminal_cad, tp = p.terminal_pct;
    const great = cad ? fmtCadOb(cad.p95) + ' (' + obPct(tp.p95) + ')' : obPct(tp.p95);
    const brutal = cad ? fmtCadOb(cad.p5) + ' (' + obPct(tp.p5) + ')' : obPct(tp.p5);
    card.innerHTML =
      '<span class="pc-title">' + meta.title + '</span>' +
      '<span class="pc-sub">' + (data.fallback ? 'a typical portfolio at this level' : meta.sub) + '</span>' +
      '<div class="pc-fan">' + miniFan(p, fanLo, fanHi) + '</div>' +
      '<div class="pc-nums">' +
      '<span class="pn-l">a great year</span><span class="pn-v ' +
      (tp.p95 >= 0 ? 'pos' : 'neg') + '">' + great + '</span>' +
      '<span class="pn-l">a brutal year</span><span class="pn-v ' +
      (tp.p5 >= 0 ? 'pos' : 'neg') + '">' + brutal + '</span>' +
      '<span class="pn-l">typical swing</span><span class="pn-v">\\u00b1' +
      p.annualized_vol_pct.toFixed(0) + '%/yr</span>' +
      '<span class="pn-l">odds of a down year</span><span class="pn-v">' +
      Math.round(p.probability_of_loss_pct) + ' in 100</span>' +
      '</div>';
    const pick = () => {
      chosenPosture = key;
      box.querySelectorAll('.posture-card').forEach((c) => c.classList.remove('selected'));
      card.classList.add('selected');
      qPulse(card);
      document.getElementById('posture-btn').disabled = false;
    };
    card.addEventListener('click', pick);
    card.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); }
    });
    box.appendChild(card);
  });
  document.getElementById('posture-btn').style.display = 'block';
  // The three futures deal themselves out, each median line drawing forward
  // through its simulated year.
  if (!REDUCED && window.Motion) {
    const cards = [...box.querySelectorAll('.posture-card')];
    Motion.animate(cards,
      { opacity: [0, 1], translate: ['0px 16px', '0px 0px'] },
      { duration: 0.32, delay: Motion.stagger(0.08), ease: EASE });
    cards.forEach((c, i) => {
      const median = c.querySelector('.mf-median');
      if (!median) return;
      median.style.strokeDasharray = '1';
      Motion.animate(median, { strokeDashoffset: [1, 0] },
        { duration: 0.8, delay: 0.2 + i * 0.08, ease: EASE });
    });
    riseIn(document.getElementById('posture-btn'), 0.3);
  }
}

const fmtCadOb = (n) => '$' + Math.round(n).toLocaleString('en-CA');

async function showRiskPicker() {
  showPanel('panel-risk-picker');
  document.getElementById('posture-status').style.display = '';
  document.getElementById('posture-retry-btn').style.display = 'none';
  document.getElementById('posture-error').style.display = 'none';
  try {
    renderPostures(await startProjections());
  } catch (e) {
    document.getElementById('posture-status').style.display = 'none';
    document.getElementById('posture-retry-btn').style.display = '';
    showError('posture-error', e.message || 'Could not compute projections.');
  }
}

document.getElementById('posture-retry-btn').addEventListener('click', () => {
  projectionsPromise = null;
  showRiskPicker();
});

async function submitProfileAndContinue(posture) {
  readProfileChips();
  const answered = obProfile.experience || obProfile.horizon ||
    obProfile.goals.length || posture;
  if (answered) {
    // One write for the whole flow; a failure must never dead-end setup —
    // the profile is re-doable anytime from Settings.
    try {
      await api('/me/profile', {
        method: 'PUT',
        body: JSON.stringify({
          experience: obProfile.experience,
          goals: obProfile.goals,
          horizon: obProfile.horizon,
          chosen_posture: posture,
        }),
      });
    } catch (e) { /* non-fatal */ }
  }
  if (PERSONALIZE) {
    // Quick fade toward the dashboard instead of a hard cut.
    const stage = document.querySelector('.ob-content');
    if (!REDUCED && window.Motion && stage) {
      try {
        await Motion.animate(stage, { opacity: [1, 0] }, { duration: 0.15, ease: EASE });
      } catch (e) { /* never block the redirect */ }
    }
    window.location.href = '/app/dashboard';
    return;
  }
  afterSync();
}

document.getElementById('posture-btn').addEventListener('click', () => {
  submitProfileAndContinue(chosenPosture);
});
document.getElementById('posture-skip').addEventListener('click', (e) => {
  e.preventDefault();
  submitProfileAndContinue(null);
});

document.getElementById('prefs-btn').addEventListener('click', async () => {
  const btn = document.getElementById('prefs-btn');
  btn.disabled = true;
  try {
    const resp = await api('/me', {
      method: 'PATCH',
      body: JSON.stringify({
        timezone: tzSel.value,
        digest_send_time: document.getElementById('send-time').value,
        digest_enabled: true,
      }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Could not save preferences');
    }
    showPanel('panel-delivery');
    initDeliveryPicker(finishOnboarding);
  } catch (e) {
    showError('prefs-error', e.message);
  } finally {
    btn.disabled = false;
  }
});


// Onboarding's last beat: kick the instant first briefing (202s immediately,
// runs server-side), then land on the dashboard in welcome mode so the
// digest card polls for it. The aha moment should be minutes away, not
// tomorrow at 9am.
async function finishOnboarding() {
  try { await api('/digest/first', { method: 'POST' }); } catch (e) { /* best-effort */ }
  window.location.href = '/app/dashboard?welcome=1';
}

// Back from the Discord OAuth connect flow (delivery is the last step):
// success means the channel is already verified server-side, so onboarding
// is done; failure reopens the delivery picker to try again.
const dcStatus = new URLSearchParams(window.location.search).get('discord');
if (dcStatus === 'connected') {
  finishOnboarding();
} else if (dcStatus) {
  showPanel('panel-delivery');
  initDeliveryPicker(finishOnboarding)
    .then(() => dpError(dcStatus === 'cancelled'
      ? 'Discord connection was cancelled. Try again, or paste a webhook URL instead.'
      : 'Discord connection failed. Try again, or paste a webhook URL instead.'));
} else if (PERSONALIZE) {
  // Stay on the questions panel; prewarm the Monte Carlo while they answer.
  api('/portfolio/status').then(async (resp) => {
    const s = await resp.json();
    if (s.connected || s.has_positions) startProjections();
  }).catch(() => {});
} else {
  // Returning mid-onboarding: if already connected, jump ahead to sync.
  api('/portfolio/status').then(async (resp) => {
    const s = await resp.json();
    if (s.connected) await runSync();
  }).catch(() => {});
}
"""


# --------------------------------------------------------------------------
# /app/dashboard
# --------------------------------------------------------------------------

_DASHBOARD_BODY = """
<div class="topbar">
  <h1 style="font-size:1.5rem;">Dashboard</h1>
  <span class="who" id="who"></span>
</div>
  <div class="warn-banner" id="trial-banner" style="display:none;">
    <span><strong>Your Pro trial has ended and your digests are paused.</strong>
    Keep Pro or continue on Free to start receiving them again — if you do
    nothing, we’ll move you to Free automatically in about a week.</span>
    <span class="actions">
      <a class="btn" href="/app/settings?billing=upgrade">Choose a plan</a>
    </span>
  </div>
  <div class="warn-banner setup" id="delivery-banner" style="display:none;">
    <span><strong>Get your digest delivered.</strong> Add text, email, or Discord
    and your morning brief reaches you before the market opens.</span>
    <span class="actions">
      <a class="btn" href="/app/settings/delivery">Set up delivery</a>
      <button class="link-btn" id="delivery-banner-dismiss">Dismiss</button>
    </span>
  </div>
  <div class="warn-banner setup" id="personalize-banner" style="display:none;">
    <span><strong>Make Cirvia yours.</strong> Answer three quick questions and
    pick your risk comfort so your digest, news, and risk analysis fit how you
    invest.</span>
    <span class="actions">
      <a class="btn" href="/app/onboarding?personalize=1">Personalize now</a>
      <button class="link-btn" id="personalize-banner-dismiss">Maybe later</button>
    </span>
  </div>
  <div class="warn-banner" id="connection-banner" style="display:none;">
    <span id="connection-banner-msg"><strong>Your brokerage connection needs
    attention.</strong> Your digest may be out of date.</span>
    <span class="actions">
      <button class="btn" id="reconnect-btn">Reconnect</button>
      <button class="link-btn" id="connection-banner-dismiss">Dismiss</button>
    </span>
  </div>

  <section class="dash-summary" id="dash-summary">
    <div class="sum-item"><span class="k">Portfolio value</span>
      <span class="v" id="sum-value">&mdash;</span></div>
    <div class="sum-item"><span class="k">Day</span>
      <span class="v" id="sum-day">&mdash;</span></div>
    <div class="sum-item"><span class="k">Total return</span>
      <span class="v" id="sum-total">&mdash;</span></div>
    <button class="sum-digest-chip" id="sum-digest" style="display:none;"></button>
  </section>

  <nav class="dash-tabs" role="tablist" aria-label="Dashboard sections">
    <button class="dash-tab" role="tab" data-tab="digest">Digest</button>
    <button class="dash-tab" role="tab" data-tab="deep-dive">Deep Dive</button>
    <button class="dash-tab" role="tab" data-tab="news">News</button>
    <button class="dash-tab" role="tab" data-tab="holdings">Holdings</button>
    <button class="dash-tab" role="tab" data-tab="watching" style="display:none;">Watching</button>
  </nav>

  <div class="dash-panel" data-panel="digest" role="tabpanel">
  <div class="dash-card" id="digest-card" style="display:none;">
    <h3>Today's digest <span class="updated-at" id="digest-updated"></span></h3>
    <div class="digest-body" id="digest-body"></div>
  </div>
  <p class="muted-note" id="digest-empty">No digest yet today. Your morning brief
  lands here before the market opens.</p>
  </div>

  <div class="dash-panel" data-panel="deep-dive" role="tabpanel">
  <div class="dash-card" id="deep-dive-card">
    <h3>Deep Dive <span class="tag">Pro</span>
      <span class="refresh-row">
        <a class="link-btn" href="/app/deep-dives" id="dd-history-link">Past reports</a>
        <button class="btn" id="dd-run-btn">Run deep dive</button>
      </span>
    </h3>
    <p class="muted-note" id="dd-blurb" style="margin-top:0.5rem;">A team of AI
    research agents — fundamentals, technical, risk, and news — investigates
    your portfolio in parallel, a verifier adversarially re-checks their
    claims against live data, and a final agent writes the report.</p>
    <div id="dd-progress" style="display:none;"></div>
    <div class="dd-activity" id="dd-activity" style="display:none;"></div>
    <div id="dd-report" style="display:none;"></div>
    <div class="error-box" id="dd-error"></div>
  </div>
  </div>

  <div class="dash-panel" data-panel="news" role="tabpanel">
  <div class="dash-card">
    <h3>News</h3>
    <div class="filters-row" id="news-filters">
      <label>Period
        <select id="filter-period">
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
          <option value="all" selected>All time</option>
        </select>
      </label>
      <label>Kind
        <select id="filter-kind">
          <option value="all">All</option>
          <option value="digest">Digests</option>
          <option value="alert">Alerts</option>
          <option value="holding">Holding news</option>
        </select>
      </label>
      <label>Severity
        <select id="filter-severity">
          <option value="">Any</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </label>
      <label>Category
        <select id="filter-category">
          <option value="">Any</option>
          <option value="geopolitical">Geopolitical</option>
          <option value="monetary">Monetary</option>
          <option value="energy">Energy</option>
          <option value="regulatory_climate">Regulatory</option>
          <option value="price_anomaly">Price anomaly</option>
        </select>
      </label>
    </div>
    <div class="news-feed" id="general-news"><div aria-hidden="true">
      <div class="skl"></div><div class="skl short"></div>
    </div></div>
  </div>
  </div>

  <div class="dash-panel" data-panel="holdings" role="tabpanel">
  <div class="dash-card">
    <h3>Holdings
      <span class="refresh-row">
        <span class="updated-at" id="holdings-updated"></span>
        <button class="link-btn" id="refresh-holdings-btn">Refresh</button>
        <span class="tag" id="totals"></span>
      </span>
    </h3>
    <div class="holdings-split">
      <div id="holdings"><div aria-hidden="true">
        <div class="skl"></div><div class="skl"></div><div class="skl short"></div>
      </div></div>
      <div class="pie-box" id="holdings-pie" style="display:none;"></div>
    </div>
  </div>

  <div class="dash-card" id="watchlist-card" style="display:none;">
    <h3>Digest coverage <span class="tag" id="watchlist-limit-tag"></span></h3>
    <p class="muted-note" style="margin-top:0.5rem;">Free plan: choose which holdings get news in your digest.</p>
    <div class="watchlist-grid" id="dash-watchlist-grid"></div>
    <button class="btn" id="save-watchlist-btn" style="margin-top:0.75rem;">Save watchlist</button>
    <div class="error-box" id="watchlist-save-error"></div>
  </div>
  </div>

  <div class="dash-panel" data-panel="watching" role="tabpanel">
  <div class="dash-card" id="watching-card" style="display:none;">
    <h3>Watching <span class="tag" id="watching-count"></span></h3>
    <p class="muted-note" style="margin-top:0.5rem;">Stocks you follow without
    holding them: news coverage, a digest line, and anomaly alerts. Find more
    with the search bar above.</p>
    <div id="watching-list"></div>
  </div>
  </div>

<button class="chat-fab" id="chat-fab" aria-expanded="false" aria-controls="chat-panel">
  Ask Cirvia</button>
<div class="chat-panel" id="chat-panel" role="dialog" aria-label="Ask Cirvia">
  <h3>Ask Cirvia <button class="chat-close" id="chat-close" aria-label="Close chat">&#10005;</button></h3>
  <div class="chat-log" id="chat-log"></div>
  <div class="chat-row">
    <input id="chat-input" placeholder="Any news on my holdings today?" maxlength="500">
    <button class="btn" id="chat-btn">Send</button>
  </div>
  <p class="muted-note" id="chat-quota" style="display:none;"></p>
  <p class="muted-note">Informational only. Cirvia never gives buy or sell advice.</p>
</div>
"""

_DASHBOARD_JS = """
requireSession();

let meProfile = null;
let portfolioTickers = [];
const dashWlSelected = new Set();

function esc(s) {
  // Quotes must be escaped too: values land inside HTML attributes.
  const d = document.createElement('div'); d.textContent = s ?? '';
  return d.innerHTML.replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
function fmtMoney(v) {
  return v == null ? '—' : v.toLocaleString('en-CA', { style: 'currency', currency: 'CAD' });
}
function pctCell(v) {
  if (v == null) return '<td>—</td>';
  const cls = v >= 0 ? 'pos' : 'neg';
  return `<td class="${cls}">${v >= 0 ? '+' : ''}${v.toFixed(2)}%</td>`;
}

// /me resolves in parallel with the other loaders (assigned in the fan-out
// at the bottom); anything that needs meProfile awaits this instead of
// serializing the whole dashboard behind /me.
let meReady = null;
// Deep-dive data is lazy: fetched on first activation of its tab, not on
// every dashboard load (the payload is a full report markdown).
let deepDiveWanted = false;
let deepDiveInited = false;
function maybeInitDeepDive() {
  if (deepDiveInited) return;
  if (!meReady) { deepDiveWanted = true; return; }  // tab restored pre-fan-out
  deepDiveInited = true;
  meReady.then(() => initDeepDive());
}

// Tabbed sections: hash > saved tab > digest. Panels hide via .active so the
// loaders keep writing into their usual elements whether visible or not.
const TAB_KEY = 'cirvia-dash-tab';
const TAB_NAMES = ['digest', 'deep-dive', 'news', 'holdings', 'watching'];
function tabBtn(name) { return document.querySelector('.dash-tab[data-tab="' + name + '"]'); }
// Hashes are #tab-<name>: a bare #holdings would collide with id="holdings"
// and make the browser scroll to the table on load.
function hashTab() {
  return location.hash.startsWith('#tab-') ? location.hash.slice(5) : '';
}
function activateTab(name, save = true) {
  if (!TAB_NAMES.includes(name) || tabBtn(name).style.display === 'none') name = 'digest';
  document.querySelectorAll('.dash-tab').forEach((b) =>
    b.setAttribute('aria-selected', String(b.dataset.tab === name)));
  document.querySelectorAll('.dash-panel').forEach((p) =>
    p.classList.toggle('active', p.dataset.panel === name));
  if (name === 'deep-dive') maybeInitDeepDive();
  if (save) localStorage.setItem(TAB_KEY, name);
  if ('#tab-' + name !== location.hash) history.replaceState(null, '', '#tab-' + name);
  // Panels render while hidden (they measure 0); re-run scroll affordances.
  window.dispatchEvent(new Event('resize'));
}
document.querySelectorAll('.dash-tab').forEach((b) =>
  b.addEventListener('click', () => activateTab(b.dataset.tab)));
window.addEventListener('hashchange', () => activateTab(hashTab(), false));
activateTab(hashTab() || localStorage.getItem(TAB_KEY) || 'digest', Boolean(hashTab()));

function filterSince() {
  const p = document.getElementById('filter-period').value;
  if (p === 'all') return null;
  const d = new Date();
  d.setDate(d.getDate() - parseInt(p, 10));
  return d.toISOString().slice(0, 10);
}

function newsQuery(extra) {
  const params = new URLSearchParams();
  // Full bodies ride along with every item; 20 keeps the payload sane and
  // the feed still fills the panel (server default is 50).
  params.set('limit', '20');
  const since = filterSince();
  if (since) params.set('since', since);
  const kind = document.getElementById('filter-kind').value;
  if (kind && kind !== 'all') params.set('kind', kind);
  const sev = document.getElementById('filter-severity').value;
  if (sev) params.set('severity', sev);
  const cat = document.getElementById('filter-category').value;
  if (cat) params.set('category', cat);
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v != null && v !== '') params.set(k, v);
    }
  }
  return params.toString();
}

// Digest bodies are labeled plain-text sections; bold the labels so they read
// as headings. Applied to already-escaped text, so no injection surface.
function formatNewsBody(body) {
  return esc(body).replace(
    /^(PORTFOLIO:|TOP RISK|NOTABLE|WATCH TODAY:|HOLDINGS|WATCHLIST|QUIET:)/gm, '<strong>$1</strong>');
}

// Day buckets use the item's publish time when known (holding articles) and
// insertion time otherwise (digests, alerts), in the browser's timezone —
// which can differ from the server TZ that fetched the item by up to a day.
function newsDayKey(item) {
  const ts = item.published_at || item.created_at;
  return ts ? new Date(ts).toDateString() : '';
}
function newsDayLabel(item) {
  const ts = item.published_at || item.created_at;
  if (!ts) return 'Earlier';
  const d = new Date(ts), now = new Date();
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === now.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function renderNewsItems(el, items, emptyMsg) {
  if (!items || items.length === 0) {
    el.innerHTML = '<p class="muted-note">' + esc(emptyMsg) + '</p>';
    return;
  }
  const parts = [];
  let lastDay = null;
  for (const item of items) {
    const day = newsDayKey(item);
    if (day !== lastDay) {
      parts.push('<div class="news-day">' + esc(newsDayLabel(item)) + '</div>');
      lastDay = day;
    }
    const meta = [];
    if (item.kind) meta.push(item.kind);
    if (item.severity) meta.push(item.severity);
    if (item.category) meta.push(item.category);
    if (item.source) meta.push(item.source);
    // News URLs come from external providers; only ever link http(s).
    const low = (item.url ?? '').toLowerCase();
    const urlOk = low.startsWith('http://') || low.startsWith('https://');
    const link = urlOk
      ? ' <a href="' + esc(item.url) + '" target="_blank" rel="noopener">Read</a>' : '';
    parts.push('<div class="news-item">' +
      '<div class="head">' + esc(item.headline) + link + '</div>' +
      (item.body ? '<div class="body">' + formatNewsBody(item.body) + '</div>' : '') +
      '<div class="meta">' + esc(meta.join(' · ')) + '</div></div>');
  }
  el.innerHTML = parts.join('');
  staggerIn(el.querySelectorAll('.news-item'));
}

async function loadDigest(data) {
  const card = document.getElementById('digest-card');
  const empty = document.getElementById('digest-empty');
  const chip = document.getElementById('sum-digest');
  const noDigest = () => {
    card.style.display = 'none';
    empty.style.display = 'block';
    chip.style.display = 'none';
  };
  try {
    if (data === undefined) {
      const res = await api('/digest/latest');
      if (!res.ok) { noDigest(); return; }  // 404 until today's runs
      data = await res.json();
    }
    if (!data || !data.body) { noDigest(); return; }
    document.getElementById('digest-body').innerHTML = formatNewsBody(data.body);
    let when = '';
    if (data.generated_at) {
      when = new Date(data.generated_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      document.getElementById('digest-updated').textContent = when;
    }
    card.style.display = 'block';
    empty.style.display = 'none';
    chip.textContent = 'Digest' + (when ? ' · ' + when : '');
    chip.style.display = 'inline-block';
  } catch (e) {
    noDigest();
  }
}
document.getElementById('sum-digest').addEventListener('click', () => activateTab('digest'));

async function loadGeneralNews(data) {
  const el = document.getElementById('general-news');
  try {
    // No forced kind: the Kind filter drives the feed (per-holding articles
    // also live on each stock's detail page).
    if (data === undefined) data = await (await api('/news?' + newsQuery())).json();
    renderNewsItems(el, data.items,
      'No news yet. Digests, alerts, and holding articles appear here once Cirvia surfaces them.');
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load news.</p>';
  }
}

function reloadNewsFeeds() {
  loadGeneralNews();
}

async function loadMe(data) {
  try {
    meProfile = data || await (await api('/me')).json();
    const trial = meProfile.trial || {};
    const planLabel = trial.active ? 'Pro trial'
      : ((meProfile.effective_plan || meProfile.plan) === 'pro' ? 'Pro' : 'Free');
    document.getElementById('who').textContent =
      (meProfile.email || '') + ' · ' + planLabel;
    // Lapsed trial = digests paused until the user picks a plan; this banner
    // is deliberately not dismissible.
    document.getElementById('trial-banner').style.display =
      trial.decision_pending ? 'flex' : 'none';
    if (meProfile.digest_tickers_editable) {
      document.getElementById('watchlist-card').style.display = 'block';
      document.getElementById('watchlist-limit-tag').textContent =
        'up to ' + (meProfile.digest_tickers_limit || 3);
    }
    renderChatQuota(meProfile.chat_quota);
  } catch (e) {}
}

// Question-quota counter under the chat input. Hidden for the owner
// (quota is null) and until the first /me or /chat response arrives.
function renderChatQuota(q) {
  const el = document.getElementById('chat-quota');
  if (!el) return;
  if (!q) { el.style.display = 'none'; return; }
  const windowLabel = q.window === 'day' ? 'today' : 'this week';
  if (q.remaining > 0) {
    el.textContent = q.remaining + ' of ' + q.limit + ' questions left ' + windowLabel + '.';
  } else {
    let msg = 'No questions left ' + windowLabel + '.';
    if (q.resets_at) {
      const d = new Date(q.resets_at);
      msg += q.window === 'day'
        ? ' Next unlocks at ' + d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) + '.'
        : ' Next unlocks ' + d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }) + '.';
    }
    el.textContent = msg;
  }
  el.style.display = 'block';
}

async function loadHoldings(data) {
  const el = document.getElementById('holdings');
  try {
    const pf = data || await (await api('/portfolio')).json();
    document.getElementById('holdings-updated').textContent =
      'Updated ' + new Date().toLocaleTimeString();
    if (!pf.positions || pf.positions.length === 0) {
      el.innerHTML = '<p class="muted-note">No holdings yet. ' +
        '<a href="/app/onboarding">Connect your brokerage</a> to sync your portfolio.</p>';
      renderSummary([], {});
      renderHoldingsPie([], {});
      return;
    }
    portfolioTickers = [...new Set(pf.positions.map((p) => p.ticker))];
    // /portfolio and /me race in parallel; the badge set needs meProfile,
    // so settle /me here (normally already resolved — zero added wait).
    if (meReady) { try { await meReady; } catch (e) {} }
    const watchlist = new Set(meProfile && meProfile.digest_tickers ? meProfile.digest_tickers : []);
    const totals = pf.totals || {};
    if (totals.total_market_value_cad != null) {
      document.getElementById('totals').textContent =
        fmtMoney(totals.total_market_value_cad) +
        (totals.total_unrealized_pnl_pct != null
          ? ' · ' + (totals.total_unrealized_pnl_pct >= 0 ? '+' : '') +
            totals.total_unrealized_pnl_pct.toFixed(1) + '%'
          : '');
    }
    // One row per ticker: the same instrument held in several accounts
    // (TFSA + RRSP, say) arrives as separate positions, but this table has
    // no account column, so ungrouped it reads as a duplicate-row bug.
    const byTicker = new Map();
    for (const p of pf.positions) {
      const g = byTicker.get(p.ticker);
      if (!g) {
        byTicker.set(p.ticker, {
          ...p, accounts: 1, cost: p.quantity * p.avg_cost,
        });
        continue;
      }
      g.accounts += 1;
      g.quantity += p.quantity;
      g.cost += p.quantity * p.avg_cost;
      if (p.market_value != null) g.market_value = (g.market_value ?? 0) + p.market_value;
      if (g.day_change_pct == null) g.day_change_pct = p.day_change_pct;
    }
    const skl = '<span class="skl-inline" aria-hidden="true"></span>';
    let rows = '';
    for (const g of byTicker.values()) {
      if (g.accounts > 1 && g.market_value != null && g.cost > 0) {
        // Re-derive the total return across accounts (cost-weighted).
        g.unrealized_pnl_pct = (g.market_value / g.cost - 1) * 100;
      }
      const badge = watchlist.has(g.ticker) ? '<span class="watchlist-badge">watchlist</span>' : '';
      const acct = g.accounts > 1
        ? `<span class="acct-count">${g.accounts} accounts</span>` : '';
      rows += `<tr class="holdings-row" data-ticker="${esc(g.ticker)}">` +
        `<td><a class="ticker-link" href="/app/stock/${encodeURIComponent(g.ticker)}">` +
        `<strong>${esc(g.ticker)}</strong></a>${badge}${acct}</td>` +
        `<td>${Number(g.quantity.toFixed(6))}</td><td>${fmtMoney(g.market_value)}</td>` +
        pctCell(g.day_change_pct) + pctCell(g.unrealized_pnl_pct) +
        `<td>${weightCell(g, totals)}</td>` +
        `<td class="m-fpe">${skl}</td><td class="m-yield">${skl}</td>` +
        `<td class="m-52w">${skl}</td><td class="m-earn">${skl}</td></tr>`;
    }
    el.innerHTML = '<div class="table-scroll"><table><thead><tr><th>Ticker</th><th>Qty</th><th>Value</th>' +
      '<th>Day</th><th>Total</th><th>Weight</th><th>Fwd P/E</th><th>Yield</th>' +
      '<th>Off high</th><th>Earnings</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
    renderSummary([...byTicker.values()], totals);
    renderHoldingsPie([...byTicker.values()], totals);
    el.querySelectorAll('.holdings-row').forEach((row) => {
      // The whole row navigates; the ticker anchor keeps middle-click/new-tab.
      row.addEventListener('click', () => {
        window.location.href = '/app/stock/' + encodeURIComponent(row.dataset.ticker);
      });
    });
    // Fade + pinned-column shadow only while there is more table to swipe to.
    const sc = el.querySelector('.table-scroll');
    const updScroll = () => {
      el.classList.toggle('is-scrollable', sc.scrollWidth > sc.clientWidth + 1);
      el.classList.toggle('at-end', sc.scrollLeft + sc.clientWidth >= sc.scrollWidth - 4);
    };
    sc.addEventListener('scroll', updScroll, { passive: true });
    window.addEventListener('resize', updScroll, { passive: true });
    updScroll();
    staggerIn(el.querySelectorAll('tbody tr'));
    buildDashWatchlist();
    loadMetrics();
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load holdings.</p>';
  }
}

// Weight is client-side math: /portfolio already carries per-row market value,
// currency, and the USDCAD rate used for the CAD totals.
function mvCadOf(g, totals) {
  if (g.market_value == null) return null;
  if (g.currency === 'CAD') return g.market_value;
  if (g.currency === 'USD' && totals.usdcad_rate != null) {
    return g.market_value * totals.usdcad_rate;
  }
  return null;
}

function weightCell(g, totals) {
  const total = totals.total_market_value_cad;
  const mvCad = mvCadOf(g, totals);
  if (mvCad == null || !total) return '—';
  return (mvCad / total * 100).toFixed(1) + '%';
}

function sumCell(id, amount, pct) {
  const el = document.getElementById(id);
  if (amount == null) { el.textContent = '—'; el.className = 'v'; return; }
  const sign = amount >= 0 ? '+' : '';
  el.className = 'v ' + (amount >= 0 ? 'pos' : 'neg');
  el.innerHTML = sign + esc(fmtMoney(amount)) +
    (pct == null ? '' : ' <span class="sub">' + sign + pct.toFixed(2) + '%</span>');
}

function renderSummary(groups, totals) {
  const valEl = document.getElementById('sum-value');
  if (totals.total_market_value_cad == null) {
    valEl.textContent = '—';
    sumCell('sum-day', null);
    sumCell('sum-total', null);
    return;
  }
  valEl.innerHTML = esc(fmtMoney(totals.total_market_value_cad)) +
    (totals.includes_all_positions === false
      ? ' <span class="sub">some unpriced</span>' : '');
  // No portfolio-level day change server-side: back it out of each priced
  // group's value and day % (value / (1 + pct) recovers yesterday's value).
  let dayPnl = null, covered = 0;
  for (const g of groups) {
    const mvCad = mvCadOf(g, totals);
    if (mvCad == null || g.day_change_pct == null) continue;
    dayPnl = (dayPnl ?? 0) + mvCad - mvCad / (1 + g.day_change_pct / 100);
    covered += mvCad;
  }
  sumCell('sum-day', dayPnl,
    dayPnl == null || !covered ? null : dayPnl / (covered - dayPnl) * 100);
  sumCell('sum-total', totals.total_unrealized_pnl_cad, totals.total_unrealized_pnl_pct);
}

// Allocation donut: hand-rolled SVG (same approach as the Risk Lab charts).
// Lavender-anchored OKLCH categorical scale at matched lightness/chroma.
const PIE_COLORS = [
  'oklch(55% 0.17 295)', 'oklch(50% 0.11 155)', 'oklch(58% 0.12 75)',
  'oklch(55% 0.13 230)', 'oklch(55% 0.14 335)', 'oklch(52% 0.11 195)',
  'oklch(52% 0.13 25)', 'oklch(48% 0.09 120)',
];
const PIE_OTHER = 'oklch(65% 0.02 300)';

// ticker -> Promise<objectURL|null>, memoized: the pie re-renders on every
// portfolio refresh and this keeps that from refetching every logo each time.
const LOGO_URLS = new Map();

function fetchLogoUrl(ticker) {
  if (!LOGO_URLS.has(ticker)) {
    LOGO_URLS.set(ticker, (async () => {
      const resp = await api('/portfolio/logo/' + encodeURIComponent(ticker));
      if (!resp.ok) return null;  // 404: lettermark stays
      return URL.createObjectURL(await resp.blob());
    })().catch(() => { LOGO_URLS.delete(ticker); return null; }));
  }
  return LOGO_URLS.get(ticker);
}

async function loadLegendLogo(el, ticker) {
  const url = await fetchLogoUrl(ticker);
  if (!url || !el.isConnected || el.querySelector('img')) return;
  const img = new Image();
  img.alt = '';
  // Append only once loaded: no broken-image flash, and the CSS entrance
  // animation runs on insertion.
  img.onload = () => { if (el.isConnected) el.appendChild(img); };
  img.src = url;
}

function renderHoldingsPie(groups, totals) {
  const box = document.getElementById('holdings-pie');
  const priced = groups.map((g) => ({ t: g.ticker, v: mvCadOf(g, totals) }))
    .filter((s) => s.v != null && s.v > 0).sort((a, b) => b.v - a.v);
  if (!priced.length) { box.style.display = 'none'; box.innerHTML = ''; return; }
  const excluded = groups.length - priced.length;
  const total = priced.reduce((s, x) => s + x.v, 0);
  const MAX_SLICES = 8;
  const slices = priced.slice(0, MAX_SLICES);
  if (priced.length > MAX_SLICES) {
    slices.push({ t: 'Other', v: priced.slice(MAX_SLICES).reduce((s, x) => s + x.v, 0), other: true });
  }
  const R = 80, RI = 48, C = 100;
  const pt = (r, frac) => {
    const a = frac * 2 * Math.PI - Math.PI / 2;  // start at 12 o'clock, clockwise
    return (C + r * Math.cos(a)).toFixed(2) + ' ' + (C + r * Math.sin(a)).toFixed(2);
  };
  let paths = '', legend = '', acc = 0;
  slices.forEach((s, i) => {
    const frac = s.v / total;
    const pctTxt = (frac * 100).toFixed(1) + '%';
    const color = s.other ? PIE_OTHER : PIE_COLORS[i % PIE_COLORS.length];
    const label = esc(s.t) + ' ' + pctTxt;
    if (slices.length === 1) {
      // A 360-degree arc has coincident endpoints and renders nothing.
      paths += '<circle class="pie-slice" data-idx="0" cx="' + C + '" cy="' + C +
        '" r="' + ((R + RI) / 2) + '" fill="none" stroke="' + color +
        '" stroke-width="' + (R - RI) + '"><title>' + label + '</title></circle>';
    } else {
      const a0 = acc, a1 = acc + frac;
      const large = frac > 0.5 ? 1 : 0;
      paths += '<path class="pie-slice" data-idx="' + i + '" fill="' + color + '" d="' +
        'M ' + pt(R, a0) + ' A ' + R + ' ' + R + ' 0 ' + large + ' 1 ' + pt(R, a1) +
        ' L ' + pt(RI, a1) + ' A ' + RI + ' ' + RI + ' 0 ' + large + ' 0 ' + pt(RI, a0) +
        ' Z"><title>' + label + '</title></path>';
    }
    legend += '<div class="pie-leg-row" data-idx="' + i + '">' +
      '<span class="lg" style="background:' + color + '"' +
      (s.other ? '' : ' data-ticker="' + esc(s.t) + '"') + '>' +
      (s.other ? '' : '<span class="ch">' + esc(s.t[0]) + '</span>') +
      '</span><span class="t">' + esc(s.t) + '</span><span>' + pctTxt + '</span></div>';
    acc += frac;
  });
  box.innerHTML = '<svg viewBox="0 0 200 200" role="img" aria-label="Portfolio allocation">' +
    paths + '<text x="100" y="104" text-anchor="middle" fill="var(--ink-3)" ' +
    'font-size="13" font-family="inherit">' + priced.length +
    (priced.length === 1 ? ' holding' : ' holdings') + '</text></svg>' +
    '<div class="pie-legend">' + legend + '</div>' +
    (excluded > 0
      ? '<p class="muted-note">' + excluded + ' unpriced position' +
        (excluded === 1 ? '' : 's') + ' not shown.</p>' : '');
  box.style.display = 'block';
  // Company logos load out-of-band: an <img src> can't carry the bearer
  // header, so each avatar fetches through api() and lands as a blob URL
  // over its lettermark. 404 (no logo known) just leaves the lettermark.
  box.querySelectorAll('.lg[data-ticker]').forEach((el2) => {
    loadLegendLogo(el2, el2.dataset.ticker);
  });
  // Hovering a slice or its legend row highlights both and dims the rest.
  box.querySelectorAll('[data-idx]').forEach((el2) => {
    el2.addEventListener('pointerenter', () => {
      box.classList.add('has-hover');
      box.querySelectorAll('[data-idx="' + el2.dataset.idx + '"]')
        .forEach((m) => m.classList.add('hl'));
    });
    el2.addEventListener('pointerleave', () => {
      box.classList.remove('has-hover');
      box.querySelectorAll('.hl').forEach((m) => m.classList.remove('hl'));
    });
  });
}

function fmtRatio(v) { return v == null ? '—' : v.toFixed(1); }
function fmtPct(v) { return v == null ? '—' : v.toFixed(2) + '%'; }

function fmtEarnings(d) {
  if (!d) return '—';
  const dt = new Date(d + 'T12:00:00');
  const days = Math.round((dt - Date.now()) / 86400000);
  const label = dt.toLocaleDateString('en-CA', { month: 'short', day: 'numeric' });
  // An earnings date within a week is actionable — surface it.
  return days <= 7 ? '<span class="earn-soon">' + label + '</span>' : label;
}

function fillMetricCells(row, m) {
  const set = (sel, html) => { const c = row.querySelector(sel); if (c) c.innerHTML = html; };
  set('.m-fpe', m.quote_type === 'ETF' ? '—' : fmtRatio(m.forward_pe));
  set('.m-yield', fmtPct(m.dividend_yield_pct));
  set('.m-52w', fmtPct(m.pct_from_52w_high));
  set('.m-earn', fmtEarnings(m.next_earnings_date));
}

async function loadMetrics() {
  // Second call by design: /portfolio renders the table instantly, this
  // fills the fundamental columns in when they arrive.
  let metrics = {};
  try {
    metrics = (await (await api('/portfolio/metrics')).json()).metrics || {};
  } catch (e) { /* cells fall through to em dashes */ }
  document.querySelectorAll('#holdings .holdings-row').forEach((row) => {
    fillMetricCells(row, metrics[row.dataset.ticker] || {});
  });
}

async function loadWatching(data) {
  const card = document.getElementById('watching-card');
  const list = document.getElementById('watching-list');
  try {
    if (data === undefined) data = await (await api('/watchlist')).json();
  } catch (e) { return; }
  const items = data.items || [];
  if (!items.length) {
    card.style.display = 'none';
    tabBtn('watching').style.display = 'none';
    // A saved/active "watching" tab with nothing to show falls back home.
    if (document.querySelector('.dash-panel[data-panel="watching"]').classList.contains('active')) {
      activateTab('digest');
    }
    return;
  }
  tabBtn('watching').style.display = '';
  document.getElementById('watching-count').textContent =
    data.limit == null ? String(data.used) : data.used + '/' + data.limit;
  let rows = '';
  for (const it of items) {
    const held = it.held ? '<span class="watchlist-badge">held</span>' : '';
    const price = it.last_price == null ? '—'
      : Number(it.last_price).toLocaleString('en-CA',
          { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    rows += `<tr class="watching-row" data-ticker="${esc(it.ticker)}">` +
      `<td><a class="ticker-link" href="/app/stock/${encodeURIComponent(it.ticker)}">` +
      `<strong>${esc(it.ticker)}</strong></a>${held}</td>` +
      `<td>${price}</td>` + pctCell(it.day_change_pct) +
      `<td style="text-align:right;"><button class="link-btn unwatch-btn" ` +
      `data-ticker="${esc(it.ticker)}" title="Stop watching">&#10005;</button></td></tr>`;
  }
  list.innerHTML = '<div class="table-scroll"><table><thead><tr><th>Ticker</th>' +
    '<th>Price</th><th>Day</th><th></th></tr></thead><tbody>' + rows +
    '</tbody></table></div>';
  card.style.display = 'block';
  list.querySelectorAll('.unwatch-btn').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      btn.disabled = true;
      try {
        await api('/watchlist/' + encodeURIComponent(btn.dataset.ticker),
          { method: 'DELETE' });
      } catch (err) { /* api() handles auth redirects */ }
      loadWatching();
    });
  });
  list.querySelectorAll('.watching-row').forEach((row) => {
    row.addEventListener('click', () => {
      window.location.href = '/app/stock/' + encodeURIComponent(row.dataset.ticker);
    });
  });
}

function buildDashWatchlist() {
  if (!meProfile || !meProfile.digest_tickers_editable) return;
  dashWlSelected.clear();
  const limit = meProfile.digest_tickers_limit || 3;
  (meProfile.digest_tickers || []).forEach((t) => dashWlSelected.add(t));
  const grid = document.getElementById('dash-watchlist-grid');
  grid.innerHTML = '';
  for (const t of portfolioTickers) {
    const el = document.createElement('div');
    el.className = 'watchlist-opt' + (dashWlSelected.has(t) ? ' selected' : '');
    el.textContent = t;
    el.addEventListener('click', () => {
      if (dashWlSelected.has(t)) {
        dashWlSelected.delete(t);
        el.classList.remove('selected');
      } else if (dashWlSelected.size < limit) {
        dashWlSelected.add(t);
        el.classList.add('selected');
      }
    });
    grid.appendChild(el);
  }
}

document.getElementById('save-watchlist-btn').addEventListener('click', async () => {
  const btn = document.getElementById('save-watchlist-btn');
  const errBox = document.getElementById('watchlist-save-error');
  errBox.style.display = 'none';
  btn.disabled = true;
  try {
    if (dashWlSelected.size === 0) {
      throw new Error('Select at least one holding.');
    }
    const resp = await api('/me', {
      method: 'PATCH',
      body: JSON.stringify({ digest_tickers: [...dashWlSelected] }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Could not save watchlist');
    }
    meProfile = await resp.json();
    await loadHoldings();
  } catch (e) {
    errBox.textContent = e.message;
    errBox.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('refresh-holdings-btn').addEventListener('click', () => loadHoldings());
['filter-period','filter-kind','filter-severity','filter-category'].forEach((id) => {
  document.getElementById(id).addEventListener('change', reloadNewsFeeds);
});

const log = document.getElementById('chat-log');
const input = document.getElementById('chat-input');
const sendBtn = document.getElementById('chat-btn');

const chatPanel = document.getElementById('chat-panel');
const chatFab = document.getElementById('chat-fab');
let chatHistoryLoaded = false;
function setChatOpen(open) {
  chatPanel.classList.toggle('open', open);
  chatFab.setAttribute('aria-expanded', String(open));
  if (open) {
    // History is lazy: fetched on first open, not on every dashboard load.
    if (!chatHistoryLoaded) { chatHistoryLoaded = true; loadChatHistory(); }
    // History loaded while the panel was display:none sits at scroll 0.
    log.scrollTop = log.scrollHeight;
    if (matchMedia('(min-width: 641px)').matches) input.focus();
  }
}
chatFab.addEventListener('click', () => setChatOpen(!chatPanel.classList.contains('open')));
document.getElementById('chat-close').addEventListener('click', () => setChatOpen(false));
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && chatPanel.classList.contains('open')) setChatOpen(false);
});

function addMsg(text, cls) {
  const div = document.createElement('div');
  div.className = 'chat-msg ' + cls;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  riseIn(div, 0.18);
  return div;
}

async function sendChat() {
  const message = input.value.trim();
  if (!message) return;
  input.value = ''; sendBtn.disabled = true;
  addMsg(message, 'user');
  const pending = addMsg('Thinking…', 'bot');
  try {
    await sendChatStream(message, pending);
  } catch (e) {
    // Transport failed before the stream produced anything (proxy buffering,
    // old deploy without /chat/stream): retry once via the JSON endpoint.
    try { await sendChatFallback(message, pending); }
    catch (e2) { pending.textContent = 'Network error. Try again.'; }
  } finally {
    sendBtn.disabled = false; input.focus();
  }
}

// SSE over fetch: EventSource can't POST or send the Bearer header, so we
// parse text/event-stream frames off the response body by hand.
async function sendChatStream(message, pending) {
  const resp = await api('/chat/stream', { method: 'POST', body: JSON.stringify({ message }) });
  if (!resp.ok) {
    // Quota/concurrency errors are real answers, not transport failures.
    const data = await resp.json().catch(() => ({}));
    pending.textContent = data.detail || 'Something went wrong.';
    return;
  }
  if (!resp.body) throw new Error('streaming unsupported');
  pending.textContent = '';
  const steps = document.createElement('div');
  const live = document.createElement('div');
  pending.appendChild(steps); pending.appendChild(live);
  const openSteps = {};   // tool name -> [step elements awaiting tool_end]
  let webStep = null;
  let gotEvent = false, finished = false;

  function addStep(icon, text) {
    const step = document.createElement('div');
    step.className = 'chat-step';
    const st = document.createElement('span'); st.className = 'st'; st.textContent = icon;
    const label = document.createElement('span'); label.textContent = text;
    step.appendChild(st); step.appendChild(label);
    steps.appendChild(step);
    return step;
  }

  function handleEvent(name, data) {
    gotEvent = true;
    if (name === 'text_delta') {
      live.textContent += data.text || '';
    } else if (name === 'tool_start') {
      // Narration before a tool call is thinking-out-loud, not the answer:
      // demote it to a muted note. The final answer arrives via 'done'.
      if (live.textContent.trim()) {
        const note = document.createElement('div');
        note.className = 'chat-note';
        note.textContent = live.textContent.trim();
        steps.appendChild(note);
        live.textContent = '';
      }
      const suffix = data.input_summary ? ' — ' + data.input_summary : '';
      const step = addStep('⚙', (data.label || data.name) + suffix + '…');
      (openSteps[data.name] = openSteps[data.name] || []).push(step);
    } else if (name === 'tool_end') {
      const step = (openSteps[data.name] || []).shift();
      if (step) {
        step.classList.add(data.ok ? 'done' : 'fail');
        step.firstChild.textContent = data.ok ? '✓' : '✗';
      }
    } else if (name === 'server_tool') {
      if (!webStep) webStep = addStep('⚙', 'Searching the web…');
    } else if (name === 'done') {
      finished = true;
      pending.textContent = data.answer || '(no answer)';   // authoritative
      if (data.chat_quota) renderChatQuota(data.chat_quota);
    } else if (name === 'error') {
      finished = true;
      pending.textContent = data.detail || 'Something went wrong.';
    }
    log.scrollTop = log.scrollHeight;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\\n\\n')) >= 0) {
        const frame = buf.slice(0, idx); buf = buf.slice(idx + 2);
        let ev = 'message', dataStr = '';
        for (const line of frame.split('\\n')) {
          if (line.startsWith('event:')) ev = line.slice(6).trim();
          else if (line.startsWith('data:')) dataStr += line.slice(5).trim();
          // lines starting with ':' are heartbeats — ignored
        }
        if (!dataStr) continue;
        try { handleEvent(ev, JSON.parse(dataStr)); } catch (e) { /* skip bad frame */ }
      }
    }
  } catch (e) {
    if (!gotEvent) throw e;   // nothing received yet -> caller may fall back
  }
  if (!finished) {
    if (!gotEvent) throw new Error('stream ended without events');
    // Mid-run drop: the run finishes server-side; history has the answer.
    pending.textContent = 'Connection lost — refresh to see the answer in chat history.';
  }
}

async function sendChatFallback(message, pending) {
  pending.textContent = 'Thinking…';
  const resp = await api('/chat', { method: 'POST', body: JSON.stringify({ message }) });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    pending.textContent = data.detail || 'Something went wrong.';
  } else {
    pending.textContent = data.answer || '(no answer)';
    if (data.chat_quota) renderChatQuota(data.chat_quota);
  }
}

sendBtn.addEventListener('click', sendChat);
input.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChat(); });

async function loadChatHistory() {
  log.innerHTML = '<div aria-hidden="true"><div class="skl"></div>' +
    '<div class="skl short"></div></div>';
  try {
    const data = await (await api('/chat/history')).json();
    log.innerHTML = '';
    for (const t of data.turns || []) {
      const div = document.createElement('div');
      div.className = 'chat-msg ' + (t.role === 'user' ? 'user' : 'bot');
      div.textContent = t.content;
      log.appendChild(div);
    }
    log.scrollTop = log.scrollHeight;
  } catch (e) {
    log.innerHTML = ''; // empty log; sendChat still works
  }
}

// --- deep dive (multi-agent research) ----------------------------------------
// POST /deep-dive kicks off the pipeline server-side; progress arrives over
// SSE (fetch + reader, same reason as chat: EventSource can't send the Bearer
// header). The server persists a progress snapshot, so a refresh mid-run
// rehydrates from the first dd_snapshot frame.

const DD_STAGES = [
  ['plan', 'Plan research questions'],
  ['research', 'Specialists investigate in parallel'],
  ['verify', 'Adversarial verification'],
  ['synthesize', 'Write the report'],
];
const DD_SPECIALISTS = {
  fundamentals: 'Fundamentals', technical: 'Technical',
  risk: 'Risk', news_macro: 'News & macro',
};

async function readSse(resp, handle) {
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\\n\\n')) >= 0) {
      const frame = buf.slice(0, idx); buf = buf.slice(idx + 2);
      let ev = 'message', dataStr = '';
      for (const line of frame.split('\\n')) {
        if (line.startsWith('event:')) ev = line.slice(6).trim();
        else if (line.startsWith('data:')) dataStr += line.slice(5).trim();
      }
      if (!dataStr) continue;
      try { handle(ev, JSON.parse(dataStr)); } catch (e) { /* skip bad frame */ }
    }
  }
}

function ddStatusIcon(status) {
  return status === 'completed' ? '✓' : status === 'failed' ? '✗'
    : status === 'started' || status === 'running' ? '◌' : '·';
}

function ddRenderProgress(progress) {
  const box = document.getElementById('dd-progress');
  box.style.display = 'block';
  document.getElementById('dd-report').style.display = 'none';
  const ul = document.createElement('ul');
  ul.className = 'dd-stages';
  for (const [key, label] of DD_STAGES) {
    const status = progress[key] || 'pending';
    const li = document.createElement('li');
    if (status === 'completed') li.className = 'done';
    if (status === 'failed') li.className = 'fail';
    const st = document.createElement('span'); st.className = 'st';
    st.textContent = ddStatusIcon(status);
    const lbl = document.createElement('span'); lbl.textContent = label;
    li.appendChild(st); li.appendChild(lbl);
    if (key === 'research') {
      const chips = document.createElement('span'); chips.className = 'dd-chips';
      const specs = progress.specialists || {};
      for (const [name, human] of Object.entries(DD_SPECIALISTS)) {
        const chip = document.createElement('span');
        const s = specs[name] || 'pending';
        chip.className = 'dd-chip ' +
          (s === 'completed' ? 'done' : s === 'failed' ? 'fail' : s === 'running' ? 'running' : '');
        chip.textContent = human;
        chips.appendChild(chip);
      }
      li.appendChild(chips);
    }
    ul.appendChild(li);
  }
  box.innerHTML = '';
  box.appendChild(ul);
}

// The dashboard shows only the report's essence — headline, the short summary,
// and verification counts. The full report (sections, findings, evidence)
// lives on /app/deep-dives, which also keeps the history.
function ddRenderSummary(r) {
  const box = document.getElementById('dd-report');
  const report = r.report || {};
  document.getElementById('dd-progress').style.display = 'none';
  document.getElementById('dd-activity').style.display = 'none';
  box.innerHTML = '';
  box.style.display = 'block';

  const meta = document.createElement('p');
  meta.className = 'muted-note';
  const when = r.completed_at || r.created_at;
  meta.textContent = (r.status === 'partial' ? 'Partial report · ' : '') +
    (when ? new Date(when).toLocaleString() : '');
  box.appendChild(meta);

  if (report.headline) {
    const h = document.createElement('h4'); h.textContent = report.headline;
    box.appendChild(h);
  }
  for (const para of String(r.summary || report.summary || report.overview || '').split('\\n\\n')) {
    if (!para.trim()) continue;
    const p = document.createElement('p'); p.textContent = para.trim();
    box.appendChild(p);
  }
  const foot = document.createElement('p'); foot.className = 'muted-note';
  const vs = report.verification_summary || {};
  foot.textContent = vs.checked
    ? vs.checked + ' claims checked, ' + vs.verified + ' verified, ' + vs.challenged + ' challenged.'
    : (report.disclaimer || 'Informational only — not investment advice.');
  box.appendChild(foot);

  const actions = document.createElement('div');
  actions.className = 'dd-summary-actions';
  const link = document.createElement('a');
  link.className = 'btn';
  link.href = '/app/deep-dives?report=' + encodeURIComponent(r.report_id);
  link.textContent = 'View full report';
  actions.appendChild(link);
  box.appendChild(actions);
}

async function ddOpenStream(reportId) {
  const activity = document.getElementById('dd-activity');
  let progress = {};
  let sawDone = false;
  try {
    const resp = await api('/deep-dive/' + reportId + '/events');
    if (!resp.ok || !resp.body) throw new Error('stream unavailable');
    await readSse(resp, (ev, data) => {
      if (ev === 'dd_snapshot') {
        progress = data.progress || {};
        ddRenderProgress(progress);
        if (data.status && data.status !== 'running') { sawDone = true; ddLoadLatest(reportId); }
        else activity.style.display = 'block';
      } else if (ev === 'dd_stage') {
        progress[data.stage] = data.status;
        ddRenderProgress(progress);
      } else if (ev === 'dd_specialist') {
        progress.specialists = progress.specialists || {};
        progress.specialists[data.name] = data.status;
        ddRenderProgress(progress);
      } else if (ev === 'dd_tool') {
        activity.style.display = 'block';
        activity.textContent = (data.specialist_label || data.specialist) + ': ' + (data.label || data.name) + '…';
      } else if (ev === 'dd_done') {
        sawDone = true;
        ddLoadLatest(data.report_id);
      }
    });
  } catch (e) { /* fall through to polling below */ }
  if (!sawDone) ddLoadLatest(reportId); // stream dropped: state is in the DB
}

async function ddLoadLatest(reportId) {
  try {
    const r = await (await api('/deep-dive/' + reportId)).json();
    if (r.status === 'running') {
      ddRenderProgress(r.progress || {});
    } else if (r.status === 'error') {
      document.getElementById('dd-progress').style.display = 'none';
      document.getElementById('dd-activity').style.display = 'none';
      const err = document.getElementById('dd-error');
      err.textContent = 'The deep dive failed — nothing was charged beyond the work done. Try again.';
      err.style.display = 'block';
    } else {
      ddRenderSummary(r);
    }
  } catch (e) {}
}

document.getElementById('dd-run-btn').addEventListener('click', async () => {
  const btn = document.getElementById('dd-run-btn');
  const err = document.getElementById('dd-error');
  err.style.display = 'none';
  const eff = meProfile && (meProfile.effective_plan || meProfile.plan);
  if (eff !== 'pro') {
    window.location.href = '/app/settings?billing=upgrade';
    return;
  }
  btn.disabled = true;
  try {
    const resp = await api('/deep-dive', { method: 'POST' });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      err.textContent = data.detail || 'Could not start the deep dive.';
      err.style.display = 'block';
      return;
    }
    document.getElementById('dd-report').style.display = 'none';
    ddRenderProgress({ plan: 'started' });
    await ddOpenStream(data.report_id);
  } catch (e) {
    err.textContent = 'Network error. Try again.';
    err.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
});

async function initDeepDive() {
  const eff = meProfile && (meProfile.effective_plan || meProfile.plan);
  if (eff !== 'pro') {
    document.getElementById('dd-run-btn').textContent = 'Upgrade to run';
    return;
  }
  let latest = null;
  try {
    const data = await (await api('/deep-dive?limit=1')).json();
    latest = (data.reports || [])[0] || null;
  } catch (e) { return; }
  if (!latest) return;
  if (latest.status === 'running') {
    ddRenderProgress(latest.progress || {});
    ddOpenStream(latest.report_id);
  } else if (latest.status !== 'error') {
    ddRenderSummary(latest);
  }
}

// --- delivery-setup nudge ----------------------------------------------------
// Shown when no verified, non-opted-out channel is active: the digest only
// lands on this dashboard until the user adds text/email/Discord delivery.
// Managed on /app/settings/delivery; this banner just points there.
const DELIVERY_BANNER_KEY = 'cirvia-delivery-banner-dismissed';

async function checkDeliverySetup(data) {
  if (sessionStorage.getItem(DELIVERY_BANNER_KEY)) return;
  // One nudge at a time: a broken connection is the more urgent problem.
  const connBanner = document.getElementById('connection-banner');
  if (connBanner && connBanner.style.display !== 'none') return;
  try {
    const info = data || await (await api('/me/notifications')).json();
    const active = (info.channels || []).find(
      (c) => c.channel === info.preferred_channel);
    if (!(active && active.verified && !active.opted_out)) {
      const banner = document.getElementById('delivery-banner');
      banner.style.display = 'flex';
      riseIn(banner);
    }
  } catch (e) { /* advisory; never block the dashboard */ }
}

document.getElementById('delivery-banner-dismiss').addEventListener('click', () => {
  sessionStorage.setItem(DELIVERY_BANNER_KEY, '1');
  document.getElementById('delivery-banner').style.display = 'none';
});

// --- personalize nudge ---------------------------------------------------------
// One-time "make Cirvia yours" prompt for accounts without an investor
// profile. Dismissal persists SERVER-SIDE (profile_prompt_dismissed_at), so it
// shows at most once per account across devices. Purely an overlay: profile
// state must never influence routing (the 1a2d393 login-trap guard).
async function checkPersonalize() {
  const p = meProfile && meProfile.profile;
  if (!p || p.completed || p.prompt_dismissed) return;
  // One nudge at a time: connection and delivery problems come first.
  for (const id of ['connection-banner', 'delivery-banner']) {
    const el = document.getElementById(id);
    if (el && el.style.display !== 'none') return;
  }
  const banner = document.getElementById('personalize-banner');
  banner.style.display = 'flex';
  riseIn(banner);
}

document.getElementById('personalize-banner-dismiss').addEventListener('click', () => {
  document.getElementById('personalize-banner').style.display = 'none';
  api('/me/profile/dismiss', { method: 'POST' }).catch(() => {});
});

// --- broken-connection banner ------------------------------------------------
// Shown when the brokerage link existed but is broken now: SnapTrade reports
// the connection disabled, the last sync errored, or a previously synced
// account has no connection left. Fresh accounts (never connected, never
// synced) keep the empty-state link to onboarding instead.
const BANNER_DISMISS_KEY = 'cirvia-connection-banner-dismissed';
let reconnectPollTimer = null;

function connectionBroken(s) {
  if (!s.registered) return false;
  return Boolean(s.connection_disabled || s.last_sync_error ||
    (!s.connected && s.last_sync_at));
}

async function checkConnection(data) {
  if (sessionStorage.getItem(BANNER_DISMISS_KEY)) return;
  try {
    const s = data || await (await api('/portfolio/status')).json();
    if (connectionBroken(s)) {
      const banner = document.getElementById('connection-banner');
      banner.style.display = 'flex';
      riseIn(banner);
    }
  } catch (e) { /* status is advisory; never block the dashboard */ }
}

function hideConnectionBanner() {
  document.getElementById('connection-banner').style.display = 'none';
}

document.getElementById('connection-banner-dismiss').addEventListener('click', () => {
  sessionStorage.setItem(BANNER_DISMISS_KEY, '1');
  hideConnectionBanner();
});

async function pollReconnect() {
  try {
    const s = await (await api('/portfolio/status')).json();
    if (s.connected) {
      clearInterval(reconnectPollTimer); reconnectPollTimer = null;
      await api('/portfolio/sync', { method: 'POST' }).catch(() => {});
      hideConnectionBanner();
      sessionStorage.removeItem(BANNER_DISMISS_KEY);
      await loadHoldings();
    }
  } catch (e) { /* keep polling */ }
}

document.getElementById('reconnect-btn').addEventListener('click', async () => {
  const btn = document.getElementById('reconnect-btn');
  btn.disabled = true;
  try {
    // Same portal flow as onboarding: ensure registration, then open the
    // SnapTrade connection portal in a new tab and wait for the round-trip.
    await api('/portfolio/snaptrade/register', { method: 'POST' });
    const resp = await api('/portfolio/connect-url');
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Could not get the connection link');
    }
    const { url } = await resp.json();
    window.open(url, '_blank');
    btn.textContent = 'Waiting for connection…';
    if (!reconnectPollTimer) reconnectPollTimer = setInterval(pollReconnect, 5000);
  } catch (e) {
    btn.textContent = 'Reconnect';
    document.getElementById('connection-banner-msg').textContent =
      e.message || 'Could not start the reconnect. Try again.';
  } finally {
    btn.disabled = false;
  }
});

// --- boot sequence -----------------------------------------------------------
// 1) Instant paint: render the last bootstrap payload from localStorage
//    (per-user key, 0 network — repeat visits paint in one frame).
// 2) One aggregated GET /dashboard/bootstrap replaces the old ~8-call
//    fan-out and re-renders every panel fresh.
// 3) A section that failed server-side (or the whole endpoint) falls back
//    to the individual endpoints — loaders fetch when passed no data.
// Loaders that need meProfile await meReady internally; the banner chain
// stays ordered (connection > delivery > personalize).
const BOOT_VERSION = 1;

function readBootCache(key) {
  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (!saved || saved.v !== BOOT_VERSION) return null;
    if (Date.now() - (saved.saved_at || 0) > 24 * 3600 * 1000) return null;
    return saved.payload;
  } catch (e) { return null; }
}

function writeBootCache(key, payload) {
  try {
    const blob = JSON.stringify({ v: BOOT_VERSION, saved_at: Date.now(), payload });
    if (blob.length <= 200 * 1024) localStorage.setItem(key, blob);
  } catch (e) { /* quota / private mode */ }
}

function applyBootstrap(boot) {
  const s = (boot && boot.sections) || {};
  const val = (n) => (s[n] && s[n].error === undefined) ? s[n].data : undefined;
  meReady = loadMe(val('me'));
  if (deepDiveWanted) maybeInitDeepDive();
  const banners = checkConnection(val('status'))
    .then(() => checkDeliverySetup(val('notifications')));
  loadHoldings(val('portfolio'));
  loadWatching(val('watchlist'));
  loadDigest(val('digest'));  // data: null is valid ("no digest yet")
  if (WELCOME && !val('digest')) pollFirstBriefing();
  loadGeneralNews(val('news'));
  Promise.allSettled([meReady, banners]).then(checkPersonalize);
}

// Welcome mode (?welcome=1, set by onboarding): the first briefing is being
// written server-side right now — poll for it so the aha moment lands on
// this very page instead of in tomorrow's inbox.
const WELCOME = new URLSearchParams(window.location.search).get('welcome') === '1';
let firstBriefingPolls = 0;
function pollFirstBriefing() {
  const empty = document.getElementById('digest-empty');
  if (empty) empty.innerHTML = '<span class="spinner"></span> Your first ' +
    'briefing is being written from your holdings right now \u2014 it lands ' +
    'here in a minute or two.';
  const tick = async () => {
    firstBriefingPolls += 1;
    try {
      const res = await api('/digest/latest');
      if (res.ok) { loadDigest(await res.json()); return; }
    } catch (e) { /* keep polling */ }
    if (firstBriefingPolls < 24) setTimeout(tick, 8000);
    else if (empty) empty.textContent = 'Your first briefing is taking longer ' +
      'than usual \u2014 it will appear here shortly, and your daily brief ' +
      'arrives tomorrow morning either way.';
  };
  setTimeout(tick, 8000);
}

let bootRepolls = 0;
async function fetchBootstrap(key) {
  const resp = await api('/dashboard/bootstrap');
  if (!resp.ok) throw new Error('bootstrap ' + resp.status);
  const boot = await resp.json();
  if (key) writeBootCache(key, boot);
  applyBootstrap(boot);
  // Stale-while-revalidate: the server flags sections it is rebuilding in
  // the background; re-poll briefly so they swap in when ready.
  if ((boot.refreshing || []).length && bootRepolls < 3) {
    bootRepolls++;
    setTimeout(() => fetchBootstrap(key).catch(() => {}), 1500);
  }
}

(async () => {
  let key = null;
  try {
    const { data } = await sb.auth.getSession();
    const uid = data && data.session && data.session.user && data.session.user.id;
    if (uid) key = 'cirvia:boot:v' + BOOT_VERSION + ':' + uid;
  } catch (e) { /* requireSession redirects if truly signed out */ }
  const cached = key && readBootCache(key);
  if (cached) applyBootstrap(cached);
  try {
    await fetchBootstrap(key);
  } catch (e) {
    applyBootstrap(null);  // full fallback: individual endpoints fetch fresh
  }
})();
"""


# --------------------------------------------------------------------------
# /app/stock/{ticker} — full-page holding detail
# --------------------------------------------------------------------------

_STOCK_BODY = """
<div class="topbar">
  <div>
    <a class="back-link" href="/app/dashboard">&larr; Dashboard</a>
    <div class="stock-head">
      <h1 id="stock-title" style="font-size:1.5rem;">&hellip;</h1>
      <span class="sub" id="stock-sub"></span>
      <span class="stock-price" id="stock-price"></span>
      <span id="stock-day"></span>
    </div>
  </div>
  <div class="watch-wrap">
    <button class="btn ghost" id="watch-btn" style="display:none;"></button>
    <div class="muted-note" id="watch-note" style="display:none;"></div>
  </div>
</div>
<div class="stock-layout">
<div class="stock-main">
  <div class="dash-card">
    <h3>Price
      <span class="chart-controls" id="chart-controls">
        <button data-days="1">1D</button>
        <button data-days="30">1M</button>
        <button data-days="182" class="active">6M</button>
        <button data-days="365">1Y</button>
      </span>
    </h3>
    <div id="chart"><div aria-hidden="true">
      <div class="skl"></div><div class="skl"></div><div class="skl short"></div>
    </div></div>
  </div>
  <div class="metric-trio" id="fund-cards">
    <div class="dash-card"><h3 id="card-a-title">Valuation</h3>
      <div class="metric-list" id="card-a"><div aria-hidden="true">
        <div class="skl"></div><div class="skl short"></div></div></div></div>
    <div class="dash-card"><h3 id="card-b-title">Growth &amp; profitability</h3>
      <div class="metric-list" id="card-b"><div aria-hidden="true">
        <div class="skl"></div><div class="skl short"></div></div></div></div>
    <div class="dash-card" id="card-c-wrap"><h3 id="card-c-title">Financial health</h3>
      <div class="metric-list" id="card-c"><div aria-hidden="true">
        <div class="skl"></div><div class="skl short"></div></div></div></div>
  </div>
  <div class="dash-card" id="price-action-card">
    <h3>Price action</h3>
    <div class="range-bar" id="range-bar" style="display:none;">
      <div class="dot" id="range-dot"></div>
    </div>
    <div class="range-ends" id="range-ends" style="display:none;">
      <span id="range-low"></span><span>52-week range</span><span id="range-high"></span>
    </div>
    <div class="metric-list" id="price-action"></div>
  </div>
  <p class="muted-note" id="no-fundamentals" style="display:none;">
    Fundamentals aren't available for this instrument.</p>
</div>
<aside class="stock-rail">
  <div class="dash-card"><h3>Your position</h3>
    <div class="metric-list" id="position"><div aria-hidden="true">
      <div class="skl"></div><div class="skl short"></div></div></div></div>
  <div class="dash-card"><h3>Key dates</h3>
    <div class="metric-list" id="key-dates"></div></div>
  <div class="dash-card"><h3>News &amp; digests</h3>
    <div class="news-feed" id="stock-news"><div aria-hidden="true">
      <div class="skl"></div><div class="skl short"></div></div></div></div>
</aside>
</div>
"""

_STOCK_JS = """
requireSession();
const TICKER = window.CIRVIA_CONFIG.ticker;
document.getElementById('stock-title').textContent = TICKER;
document.title = TICKER + ' — Cirvia';

function esc(s) {
  const d = document.createElement('div'); d.textContent = s ?? '';
  return d.innerHTML.replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
function fmtNum(v, dp = 2) { return v == null ? '—' : Number(v).toFixed(dp); }
function fmtPct(v) { return v == null ? '—' : Number(v).toFixed(2) + '%'; }
function pctSpan(v) {
  if (v == null) return '—';
  const cls = v >= 0 ? 'pos' : 'neg';
  return `<span class="${cls}">${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%</span>`;
}
function fmtBig(v) {
  if (v == null) return '—';
  const a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toFixed(2) + 'T';
  if (a >= 1e9) return (v / 1e9).toFixed(2) + 'B';
  if (a >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  return Number(v).toLocaleString('en-CA');
}
function fmtCur(v, cur) {
  if (v == null) return '—';
  try {
    return v.toLocaleString('en-CA', { style: 'currency', currency: cur || 'CAD' });
  } catch (e) { return Number(v).toFixed(2); }
}
function rows(pairs) {
  const out = pairs
    .map(([k, v]) => `<div class="metric-row"><span class="k">${k}</span>` +
      `<span class="v">${v}</span></div>`)
    .join('');
  return out || '<p class="muted-note">No data available.</p>';
}

// Rule-of-thumb grading (green / yellow / red) for the metrics that drive
// buy/sell judgment. Only metrics with defensible universal bands get a
// color — sector-relative ones (P/S, P/B, EV/EBITDA, gross margin) stay
// neutral. Bands are deliberately generous: this is a glance cue, not a
// verdict. `good`/`bad` are the thresholds nearest green and red; direction
// (higher- vs lower-is-better) is inferred from their order.
function grade(v, text, good, bad) {
  if (v == null) return text;
  const higherIsBetter = good > bad;
  const cls = higherIsBetter
    ? (v >= good ? 'pos' : v >= bad ? 'mid' : 'neg')
    : (v <= good ? 'pos' : v <= bad ? 'mid' : 'neg');
  return `<span class="${cls}">${text}</span>`;
}

// P/E needs its own guard: negative means unprofitable, which the plain
// lower-is-better scale would happily paint green.
function gradePE(v, text) {
  if (v != null && v < 0) return `<span class="neg">${text}</span>`;
  return grade(v, text, 18, 35);
}

// --- header + cards ----------------------------------------------------------

function fillHeader(d) {
  const p = d.profile || {};
  const sub = [p.name, p.sector || (d.etf ? 'ETF' : null)].filter(Boolean).join(' · ');
  document.getElementById('stock-sub').textContent = sub;
  if (d.quote && d.quote.last_price != null) {
    document.getElementById('stock-price').textContent =
      fmtCur(d.quote.last_price, p.currency);
    document.getElementById('stock-day').innerHTML = pctSpan(d.quote.day_change_pct);
  }
}

function fillPosition(d) {
  if (!d.position) {
    document.getElementById('position').innerHTML =
      '<p class="muted-note">You don\\u2019t hold this stock.' +
      (d.watching ? '' :
        ' Watch it to get news coverage and a line in your digest.') + '</p>';
    return;
  }
  const pos = d.position;
  const cur = pos.currency;
  const pairs = [
    ['Quantity', fmtNum(pos.quantity, 4)],
    ['Avg cost', fmtCur(pos.avg_cost, cur)],
    ['Cost basis', fmtCur(pos.cost_basis, cur)],
    ['Market value', fmtCur(pos.market_value, cur)],
    ['Unrealized P&L', pos.unrealized_pnl == null ? '—'
      : fmtCur(pos.unrealized_pnl, cur) + ' (' +
        (pos.unrealized_pnl_pct >= 0 ? '+' : '') + fmtNum(pos.unrealized_pnl_pct) + '%)'],
    ['Portfolio weight', fmtPct(pos.weight_pct)],
  ];
  if (pos.annual_dividend_income != null) {
    pairs.push(['Est. annual dividends', fmtCur(pos.annual_dividend_income, cur)]);
  }
  if ((pos.accounts || []).length > 1) {
    for (const a of pos.accounts) {
      pairs.push([esc(a.account), fmtNum(a.quantity, 4) + ' sh']);
    }
  }
  document.getElementById('position').innerHTML = rows(pairs);
}

function fillKeyDates(d) {
  const e = d.earnings || {};
  document.getElementById('key-dates').innerHTML = rows([
    ['Next earnings', e.next_earnings_date || '—'],
    ['Ex-dividend', e.ex_dividend_date || '—'],
    ['Data as of', d.fetched_at ? new Date(d.fetched_at).toLocaleDateString('en-CA') : '—'],
  ]);
}

function fillEquityCards(d) {
  const v = d.valuation || {}, g = d.growth || {}, pr = d.profitability || {},
    fh = d.financial_health || {};
  document.getElementById('card-a').innerHTML = rows([
    ['P/E (trailing)', fmtNum(v.trailing_pe, 1)],
    ['P/E (forward)', gradePE(v.forward_pe, fmtNum(v.forward_pe, 1))],
    ['PEG', grade(v.peg, fmtNum(v.peg), 1, 2)],
    ['Price / sales', fmtNum(v.price_to_sales, 1)],
    ['Price / book', fmtNum(v.price_to_book, 1)],
    ['EV / EBITDA', fmtNum(v.ev_to_ebitda, 1)],
    ['Price / FCF', grade(v.price_to_fcf, fmtNum(v.price_to_fcf, 1), 25, 50)],
  ]);
  document.getElementById('card-b').innerHTML = rows([
    ['Revenue growth', grade(g.revenue_growth_pct, fmtPct(g.revenue_growth_pct), 10, 0)],
    ['Earnings growth', grade(g.earnings_growth_pct, fmtPct(g.earnings_growth_pct), 10, 0)],
    ['Gross margin', fmtPct(pr.gross_margin_pct)],
    ['Operating margin', fmtPct(pr.operating_margin_pct)],
    ['Net margin', grade(pr.net_margin_pct, fmtPct(pr.net_margin_pct), 15, 5)],
    ['Return on equity', grade(pr.roe_pct, fmtPct(pr.roe_pct), 15, 8)],
  ]);
  document.getElementById('card-c').innerHTML = rows([
    ['Debt / equity', grade(fh.debt_to_equity, fmtNum(fh.debt_to_equity), 1, 2)],
    ['Current ratio', grade(fh.current_ratio, fmtNum(fh.current_ratio), 1.5, 1)],
    ['Market cap', fmtBig((d.profile || {}).market_cap)],
  ]);
}

function fillEtfCards(d) {
  const etf = d.etf || {};
  document.getElementById('card-a-title').textContent = 'Fund';
  document.getElementById('card-a').innerHTML = rows([
    ['Expense ratio', grade(etf.expense_ratio_pct, fmtPct(etf.expense_ratio_pct), 0.2, 0.6)],
    ['Assets', fmtBig(etf.total_assets)],
    ['Category', etf.category ? esc(etf.category) : '—'],
    ['Fund family', etf.fund_family ? esc(etf.fund_family) : '—'],
    ['Distribution yield', fmtPct((d.dividends || {}).dividend_yield_pct)],
  ]);
  document.getElementById('card-b-title').textContent = 'Top holdings';
  const holdings = etf.top_holdings || [];
  document.getElementById('card-b').innerHTML = holdings.length
    ? rows(holdings.map((h) => [
        `${esc(h.symbol)} <span style="color:var(--ink-3);">${esc(h.name)}</span>`,
        fmtPct(h.weight_pct),
      ]))
    : '<p class="muted-note">Holdings data unavailable.</p>';
  document.getElementById('card-c-wrap').style.display = 'none';
}

function fillPriceAction(d) {
  const pa = d.price_action || {}, div = d.dividends || {};
  const q = d.quote || {};
  if (pa.low_52w != null && pa.high_52w != null && q.last_price != null &&
      pa.high_52w > pa.low_52w) {
    const frac = Math.min(1, Math.max(0,
      (q.last_price - pa.low_52w) / (pa.high_52w - pa.low_52w)));
    document.getElementById('range-bar').style.display = 'block';
    document.getElementById('range-ends').style.display = 'flex';
    document.getElementById('range-dot').style.left = (frac * 100).toFixed(1) + '%';
    document.getElementById('range-low').textContent = fmtNum(pa.low_52w);
    document.getElementById('range-high').textContent = fmtNum(pa.high_52w);
  }
  const beta = pa.beta == null ? '—'
    : fmtNum(pa.beta) + (pa.beta_source === 'computed' ? ' (est.)' : '');
  const target = pa.analyst_target == null || q.last_price == null
    ? fmtNum(pa.analyst_target)
    : fmtNum(pa.analyst_target) + ' (' +
      pctSpan((pa.analyst_target / q.last_price - 1) * 100) + ')';
  const rating = pa.analyst_rating
    ? esc(pa.analyst_rating.replaceAll('_', ' ')) +
      (pa.analyst_count ? ` <span style="color:var(--ink-3);">(${pa.analyst_count})</span>` : '')
    : '—';
  document.getElementById('price-action').innerHTML = rows([
    ['Off 52-week high', pctSpan(pa.pct_from_52w_high)],
    ['Beta', beta],
    ['50-day average', fmtNum(pa.avg_50d)],
    ['200-day average', fmtNum(pa.avg_200d)],
    ['Analyst target', target],
    ['Analyst rating', rating],
    ['Short % of float', grade(pa.short_pct_of_float, fmtPct(pa.short_pct_of_float), 5, 15)],
    ['Dividend yield', fmtPct(div.dividend_yield_pct)],
    ['Payout ratio', grade(div.payout_ratio_pct, fmtPct(div.payout_ratio_pct), 60, 90)],
  ]);
}

// --- watchlist ---------------------------------------------------------------

let watchingNow = false;

function setWatchButton(watching) {
  watchingNow = !!watching;
  const btn = document.getElementById('watch-btn');
  btn.textContent = watchingNow ? '\\u2605 Watching' : '\\u2606 Watch';
  btn.title = watchingNow
    ? 'Watching: news, digest coverage, and alerts. Click to stop.'
    : 'Get news coverage, a digest line, and alerts for this stock.';
  btn.style.display = 'inline-flex';
}

async function toggleWatch() {
  const btn = document.getElementById('watch-btn');
  const note = document.getElementById('watch-note');
  note.style.display = 'none';
  btn.disabled = true;
  try {
    const resp = await api('/watchlist/' + encodeURIComponent(TICKER),
      { method: watchingNow ? 'DELETE' : 'POST' });
    if (resp.ok) {
      setWatchButton(!watchingNow);
    } else {
      const data = await resp.json().catch(() => ({}));
      note.innerHTML = esc(data.detail || 'Could not update your watchlist.')
        .replace('Upgrade to Pro to watch more.',
          '<a href="/app/settings?billing=upgrade">Upgrade to Pro</a> to watch more.');
      note.style.display = 'block';
    }
  } catch (e) { /* api() already redirected on auth loss */ }
  btn.disabled = false;
}

document.getElementById('watch-btn').addEventListener('click', toggleWatch);

async function loadDetail() {
  let resp;
  try {
    resp = await api('/stocks/' + encodeURIComponent(TICKER));
  } catch (e) { return; }
  if (!resp.ok) {
    document.querySelector('.stock-main').innerHTML =
      '<div class="dash-card"><p class="muted-note">' +
      (resp.status === 404
        ? 'Couldn\\u2019t find this ticker.'
        : 'Could not load this stock.') +
      ' <a href="/app/dashboard">Back to dashboard</a></p></div>';
    return;
  }
  const d = await resp.json();
  fillHeader(d);
  fillPosition(d);
  setWatchButton(d.watching);
  fillKeyDates(d);
  const qt = (d.profile || {}).quote_type;
  if (qt === 'ETF') {
    fillEtfCards(d);
    fillPriceAction(d);
  } else if (qt === 'EQUITY') {
    fillEquityCards(d);
    fillPriceAction(d);
  } else {
    // Crypto / FX / unknown: position, chart, and news still render.
    document.getElementById('fund-cards').style.display = 'none';
    document.getElementById('price-action-card').style.display = 'none';
    document.getElementById('no-fundamentals').style.display = 'block';
  }
  staggerIn(document.querySelectorAll('.dash-card'));
}

// --- chart (inline SVG, no libraries) ------------------------------------------

let chartDays = 182;
let chartTimer = null;

function barLabel(dateStr, intraday) {
  if (intraday) {
    return new Date(dateStr).toLocaleTimeString('en-CA',
      { hour: '2-digit', minute: '2-digit' });
  }
  return dateStr;
}

function renderChart(el, bars, intraday) {
  const closes = bars.map((b) => b.close);
  if (closes.length < 2) {
    el.innerHTML = '<p class="muted-note">' + (intraday
      ? 'No trades yet today — the 1D view fills in once the session opens.'
      : 'Not enough history to chart.') + '</p>';
    return;
  }
  const W = 640, H = 220, P = 12;
  const min = Math.min(...closes), max = Math.max(...closes);
  const span = (max - min) || 1;
  const lo = min - span * 0.04, hi = max + span * 0.04;
  const x = (i) => P + i * (W - 2 * P) / (closes.length - 1);
  const y = (c) => H - P - (c - lo) * (H - 2 * P) / (hi - lo);
  const pts = closes.map((c, i) => x(i).toFixed(1) + ',' + y(c).toFixed(1)).join(' ');
  const stroke = closes[closes.length - 1] >= closes[0] ? 'var(--gain)' : 'var(--loss)';
  const area = `${P},${H - P} ${pts} ${W - P},${H - P}`;
  const first = bars[0].date, last = bars[bars.length - 1].date;
  el.innerHTML =
    `<svg viewBox="0 0 ${W} ${H}" role="img">` +
    `<title>${esc(TICKER)} prices, ${first} to ${last}</title>` +
    `<polygon points="${area}" fill="${stroke}" opacity="0.08"></polygon>` +
    `<polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="1.8"></polyline>` +
    `<line id="chart-xhair" y1="${P}" y2="${H - P}" stroke="var(--line-strong)" ` +
    `stroke-width="1" visibility="hidden"></line>` +
    `<circle id="chart-dot" r="3.2" fill="${stroke}" visibility="hidden"></circle>` +
    `<text x="${P}" y="12" fill="var(--ink-3)" font-size="10">${max.toFixed(2)}</text>` +
    `<text x="${P}" y="${H - 2}" fill="var(--ink-3)" font-size="10">${min.toFixed(2)}</text>` +
    `<text x="${W - P}" y="${H - 2}" text-anchor="end" fill="var(--ink-3)" ` +
    `font-size="10">${barLabel(last, intraday)}</text>` +
    '</svg><div class="chart-tip" id="chart-tip"></div>';

  // Crosshair: pointer events cover mouse, touch drag, and pen. Geometry
  // stays in viewBox units (the SVG scales with the card); only the tooltip
  // needs pixel math.
  const svg = el.querySelector('svg');
  const xhair = el.querySelector('#chart-xhair');
  const dot = el.querySelector('#chart-dot');
  const tip = el.querySelector('#chart-tip');
  const trace = (ev) => {
    const rect = svg.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
    const i = Math.round(frac * (closes.length - 1));
    const vx = x(i);
    xhair.setAttribute('x1', vx); xhair.setAttribute('x2', vx);
    xhair.setAttribute('visibility', 'visible');
    dot.setAttribute('cx', vx); dot.setAttribute('cy', y(closes[i]));
    dot.setAttribute('visibility', 'visible');
    tip.textContent = closes[i].toFixed(2) + ' · ' + barLabel(bars[i].date, intraday);
    const px = vx / W * rect.width;
    tip.style.left = Math.min(rect.width - 8, Math.max(8, px)) + 'px';
    tip.style.display = 'block';
  };
  const clear = () => {
    xhair.setAttribute('visibility', 'hidden');
    dot.setAttribute('visibility', 'hidden');
    tip.style.display = 'none';
  };
  svg.addEventListener('pointermove', trace);
  svg.addEventListener('pointerdown', trace);
  svg.addEventListener('pointerleave', clear);
  svg.addEventListener('pointercancel', clear);
  riseIn(svg);
}

async function loadChart(days) {
  chartDays = days;
  const el = document.getElementById('chart');
  try {
    const data = await (
      await api('/stocks/' + encodeURIComponent(TICKER) + '/history?days=' + days)
    ).json();
    if (days !== chartDays) return; // a later toggle superseded this fetch
    renderChart(el, data.ohlcv || [], Boolean(data.intraday));
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load price history.</p>';
  }
}

// The 1D view re-fetches once a minute (matching the server's intraday cache
// TTL) while the tab is visible; historical views are static by nature.
function scheduleChartRefresh() {
  if (chartTimer) { clearInterval(chartTimer); chartTimer = null; }
  if (chartDays !== 1) return;
  chartTimer = setInterval(() => {
    if (document.visibilityState === 'visible' && chartDays === 1) loadChart(1);
  }, 60000);
}

document.querySelectorAll('#chart-controls button').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#chart-controls button').forEach((b) =>
      b.classList.toggle('active', b === btn));
    loadChart(parseInt(btn.dataset.days, 10)).then(scheduleChartRefresh);
  });
});

// --- news ----------------------------------------------------------------------

// Digest bodies are labeled plain-text sections; bold the labels so they read
// as headings. Applied to already-escaped text, so no injection surface.
function formatNewsBody(body) {
  return esc(body).replace(
    /^(PORTFOLIO:|TOP RISK|NOTABLE|WATCH TODAY:|HOLDINGS|WATCHLIST|QUIET:)/gm, '<strong>$1</strong>');
}

// Day buckets use publish time when known, insertion time otherwise, in the
// browser's timezone (duplicated from the dashboard feed, like formatNewsBody).
function newsDayKey(item) {
  const ts = item.published_at || item.created_at;
  return ts ? new Date(ts).toDateString() : '';
}
function newsDayLabel(item) {
  const ts = item.published_at || item.created_at;
  if (!ts) return 'Earlier';
  const d = new Date(ts), now = new Date();
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === now.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

async function loadNews() {
  const el = document.getElementById('stock-news');
  try {
    // All three kinds: articles tagged to this ticker, alerts naming it, and
    // morning digests whose text mentions it.
    const params = new URLSearchParams({ ticker: TICKER, kind: 'digest,holding,alert' });
    const data = await (await api('/news?' + params)).json();
    if (!data.items || data.items.length === 0) {
      el.innerHTML = '<p class="muted-note">Nothing stored for ' + esc(TICKER) +
        ' yet. Digests, alerts, and articles that mention it will appear here.</p>';
      return;
    }
    const parts = [];
    let lastDay = null;
    for (const item of data.items) {
      const day = newsDayKey(item);
      if (day !== lastDay) {
        parts.push('<div class="news-day">' + esc(newsDayLabel(item)) + '</div>');
        lastDay = day;
      }
      const meta = [item.kind, item.source].filter(Boolean);
      const low = (item.url ?? '').toLowerCase();
      const urlOk = low.startsWith('http://') || low.startsWith('https://');
      const link = urlOk
        ? ' <a href="' + esc(item.url) + '" target="_blank" rel="noopener">Read</a>' : '';
      parts.push('<div class="news-item">' +
        '<div class="head">' + esc(item.headline) + link + '</div>' +
        (item.body ? '<div class="body">' + formatNewsBody(item.body) + '</div>' : '') +
        '<div class="meta">' + esc(meta.join(' · ')) + '</div></div>');
    }
    el.innerHTML = parts.join('');
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load news.</p>';
  }
}

loadDetail();
loadChart(182);
loadNews();
"""


def stock_page(ticker: str, supabase_url: str, anon_key: str) -> str:
    return _page(
        f"{ticker} — Cirvia",
        _STOCK_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_STOCK_JS,
        wrap_class="app-wrap dash-wrap",
        extra_config={"ticker": ticker},
    )


# --------------------------------------------------------------------------
# /app/settings — account, brokerage connection, plan, danger zone
# --------------------------------------------------------------------------

_SETTINGS_BODY = """
<div class="topbar">
  <h1 style="font-size:1.5rem;">Settings</h1>
  <span class="who" id="who"></span>
</div>

<div class="dash-card">
  <h3>Account</h3>
  <p class="muted-note" style="margin-top:0.5rem;">Signed in as
    <strong id="account-email">&hellip;</strong></p>
  <form id="pw-form">
    <label for="new-password">New password</label>
    <input type="password" id="new-password" autocomplete="new-password"
      minlength="8" required>
    <label for="confirm-password">Confirm new password</label>
    <input type="password" id="confirm-password" autocomplete="new-password"
      minlength="8" required>
    <button class="btn" id="pw-btn" type="submit"
      style="margin-top:1rem;">Change password</button>
  </form>
  <div class="error-box" id="pw-error"></div>
  <div class="notice-box" id="pw-notice"></div>
</div>

<div class="dash-card">
  <h3>Brokerage connection <span class="tag" id="conn-chip"></span></h3>
  <div id="conn-summary"><div aria-hidden="true">
    <div class="skl"></div><div class="skl short"></div>
  </div></div>
  <div id="conn-actions" style="display:none;">
    <button class="btn ghost" id="disconnect-btn"
      style="margin-top:0.75rem;">Disconnect brokerage</button>
    <div id="disconnect-confirm" style="display:none;">
      <p class="muted-note">Disconnect brokerage? Your holdings stop syncing.</p>
      <button class="btn" id="disconnect-yes">Yes, disconnect</button>
      <button class="link-btn" id="disconnect-no"
        style="margin-left:0.75rem;">Cancel</button>
    </div>
  </div>
  <div class="error-box" id="conn-error"></div>
  <div class="notice-box" id="conn-notice"></div>
</div>

<div class="dash-card">
  <h3>Delivery <a class="link-btn" href="/app/settings/delivery">Manage</a></h3>
  <div id="delivery-overview"><div aria-hidden="true">
    <div class="skl short"></div>
  </div></div>
</div>

<div class="dash-card">
  <h3>Investor profile <span class="tag" id="profile-chip"></span>
    <a class="link-btn" href="/app/onboarding?personalize=1">Update</a></h3>
  <div id="profile-overview"><div aria-hidden="true">
    <div class="skl short"></div>
  </div></div>
</div>

<div class="dash-card" id="plan-card">
  <h3>Plan <span class="tag" id="plan-chip"></span></h3>
  <ul class="plan-limits" id="plan-limits"></ul>
  <div id="billing-actions" style="margin-top:0.75rem;"></div>
  <p class="muted-note" id="plan-note" style="display:none;">Pro billing is coming
  soon. Until then every account stays on the Free plan.</p>
  <div class="error-box" id="billing-error"></div>
  <div class="notice-box" id="billing-notice"></div>
</div>

<div class="dash-card danger-card">
  <h3>Danger zone</h3>
  <p class="muted-note" style="margin-top:0.5rem;">Deleting your account removes
  your holdings, digests, alerts, chat history, and notification settings from
  Cirvia. This cannot be undone.</p>
  <button class="btn ghost" id="delete-btn"
    style="margin-top:0.75rem;">Delete account</button>
  <div id="delete-confirm" style="display:none;">
    <label for="delete-input">Type DELETE to confirm</label>
    <input type="text" id="delete-input" autocomplete="off" placeholder="DELETE">
    <button class="btn" id="delete-yes" disabled
      style="margin-top:0.9rem;">Permanently delete my account</button>
    <button class="link-btn" id="delete-no"
      style="margin-left:0.75rem;">Cancel</button>
  </div>
  <div class="error-box" id="delete-error"></div>
</div>
"""

_SETTINGS_JS = """
requireSession();

function setBox(id, msg) {
  const box = document.getElementById(id);
  if (msg) { box.textContent = msg; box.style.display = 'block'; }
  else { box.style.display = 'none'; }
}

// ---- account + plan --------------------------------------------------------

async function loadAccount() {
  try {
    const me = await (await api('/me')).json();
    const trial = me.trial || {};
    const eff = me.effective_plan || me.plan;
    const plan = trial.active ? 'Pro trial' : (eff === 'pro' ? 'Pro' : 'Free');
    document.getElementById('who').textContent = (me.email || '') + ' \\u00b7 ' + plan;
    document.getElementById('account-email').textContent = me.email || 'unknown';
    document.getElementById('plan-chip').textContent = plan;
    const limits = document.getElementById('plan-limits');
    const items = eff === 'pro'
      ? ['Daily weekday digest across all your holdings',
         'Macro alerts when the world moves',
         '10 chat questions per day',
         'Unlimited connected accounts']
      : ['Weekly digest (Mondays) on up to ' + (me.digest_tickers_limit || 3) +
           ' holdings',
         '3 chat questions per week',
         '1 connected account'];
    limits.innerHTML = items.map((t) => '<li>' + esc(t) + '</li>').join('');
    renderProfileCard(me);
    renderBilling(me);
  } catch (e) { /* nav still works; cards degrade individually */ }
}

// ---- investor profile --------------------------------------------------------

const OB_HORIZONS = { days: 'acts within days', weeks_months: 'acts over weeks to months',
  years: 'acts over years', decade_plus: 'thinks in decades' };
const OB_EXPERIENCE = { new: 'just starting out', lt_1y: 'under a year in',
  '1_5y': '1\\u20135 years in', '5_10y': '5\\u201310 years in', '10y_plus': '10+ years in' };
const OB_GOALS = { grow_long_term: 'long-term growth', income: 'income',
  preserve_capital: 'capital preservation', short_term_gains: 'short-term gains',
  retirement: 'retirement', big_purchase: 'a big purchase' };

function renderProfileCard(me) {
  const el = document.getElementById('profile-overview');
  const p = me.profile || {};
  document.getElementById('profile-chip').textContent =
    p.completed ? (p.archetype_label || '') : 'Default';
  if (!p.completed) {
    el.innerHTML = '<p class="muted-note" style="margin-top:0.5rem;">Not set up ' +
      'yet \\u2014 Cirvia is using a balanced long-term default. Personalize so ' +
      'your digest, news, and risk analysis fit how you invest.</p>';
    return;
  }
  const bits = ['risk comfort ' + p.risk_tolerance + '/10'];
  if (p.horizon && OB_HORIZONS[p.horizon]) bits.push(OB_HORIZONS[p.horizon]);
  if (p.experience && OB_EXPERIENCE[p.experience]) bits.push(OB_EXPERIENCE[p.experience]);
  const goals = (p.goals || []).map((g) => OB_GOALS[g]).filter(Boolean);
  if (goals.length) bits.push('investing for ' + goals.join(', '));
  el.innerHTML = '<p class="muted-note" style="margin-top:0.5rem;">' +
    esc(bits.join(' \\u00b7 ')) + '. Your digest, news, and risk analysis are ' +
    'framed around this.</p>';
}

// ---- billing (Stripe checkout + customer portal) ---------------------------

function renderBilling(me) {
  const actions = document.getElementById('billing-actions');
  const note = document.getElementById('plan-note');
  const billing = me.billing || {};
  const trial = me.trial || {};
  actions.innerHTML = '';
  note.style.display = 'none';
  if (!billing.enabled) {
    // Deployment has no Stripe keys (e.g. local dev) — keep the old copy.
    if (me.plan !== 'pro') note.style.display = 'block';
    return;
  }
  if (me.plan !== 'pro') {
    const upgradeBtns =
      '<button class="btn" id="upgrade-btn">Upgrade to Pro \\u2014 $20/mo CAD</button>' +
      (billing.annual_available
        ? '<button class="link-btn" id="upgrade-annual-btn" ' +
          'style="margin-left:0.75rem;">or $160/yr \\u2014 4 months free</button>'
        : '');
    if (trial.decision_pending) {
      actions.innerHTML =
        '<p class="muted-note" style="margin-bottom:0.75rem;"><strong ' +
        'style="color:var(--ink);">Your Pro trial has ended and your digests ' +
        'are paused.</strong> Keep the full Pro experience, or continue on ' +
        'Free with a weekly digest (we\u2019ll switch you to Free automatically ' +
        'in about a week if you do nothing).</p>' + upgradeBtns +
        '<div style="margin-top:0.6rem;"><button class="link-btn" ' +
        'id="choose-free-btn">Continue with Free</button></div>';
    } else if (trial.active) {
      actions.innerHTML = upgradeBtns +
        '<p class="muted-note" style="margin-top:0.75rem;">Pro trial ends ' +
        esc(new Date(trial.ends_at).toLocaleDateString()) +
        ' \\u2014 after that, digests pause until you choose Pro or Free.</p>';
    } else {
      actions.innerHTML = upgradeBtns;
    }
    document.getElementById('upgrade-btn')
      .addEventListener('click', () => startCheckout('monthly'));
    const annual = document.getElementById('upgrade-annual-btn');
    if (annual) annual.addEventListener('click', () => startCheckout('annual'));
    const chooseFree = document.getElementById('choose-free-btn');
    if (chooseFree) chooseFree.addEventListener('click', chooseFreePlan);
  } else if (me.is_owner) {
    // The owner is Pro by decree, not by subscription — nothing to manage.
  } else if (billing.has_billing_account) {
    let html = '<button class="btn ghost" id="portal-btn">Manage billing</button>';
    if (billing.cancel_at_period_end && billing.current_period_end) {
      html = '<p class="muted-note" style="margin-bottom:0.75rem;">Pro until ' +
        esc(new Date(billing.current_period_end).toLocaleDateString()) +
        ' \\u2014 renewing is one click away in Manage billing.</p>' + html;
    }
    actions.innerHTML = html;
    document.getElementById('portal-btn').addEventListener('click', openPortal);
  }
}

async function startCheckout(interval) {
  setBox('billing-error', null);
  try {
    const resp = await api('/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({ interval }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Could not start checkout');
    window.location.href = data.url;
  } catch (e) {
    setBox('billing-error', e.message);
  }
}

async function openPortal() {
  setBox('billing-error', null);
  try {
    const resp = await api('/billing/portal', { method: 'POST' });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Could not open the billing portal');
    window.location.href = data.url;
  } catch (e) {
    setBox('billing-error', e.message);
  }
}

async function chooseFreePlan() {
  setBox('billing-error', null);
  try {
    const resp = await api('/billing/choose-free', { method: 'POST' });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || 'Could not update your plan');
    }
    setBox('billing-notice', 'You\\u2019re on the Free plan \\u2014 your weekly ' +
      'digest resumes Monday. Upgrade any time.');
    await loadAccount();
  } catch (e) {
    setBox('billing-error', e.message);
  }
}

async function handleBillingReturn() {
  const params = new URLSearchParams(window.location.search);
  const state = params.get('billing');
  if (!state) return;
  // Keep reloads from re-triggering the notice/polling.
  window.history.replaceState({}, '', '/app/settings');
  const card = document.getElementById('plan-card');
  if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  if (state === 'canceled') {
    setBox('billing-notice', 'Checkout canceled \\u2014 you were not charged.');
    return;
  }
  if (state !== 'success') return;
  // The plan flips asynchronously via the Stripe webhook; poll briefly.
  setBox('billing-notice', 'Payment received \\u2014 finalizing your upgrade\\u2026');
  for (let i = 0; i < 15; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    try {
      const me = await (await api('/me')).json();
      if (me.plan === 'pro') {
        setBox('billing-notice', 'Welcome to Pro! Daily digests, macro alerts, ' +
          'and unlimited chat are now on.');
        await loadAccount();
        return;
      }
    } catch (e) { /* keep polling */ }
  }
  setBox('billing-notice', 'Payment received \\u2014 your plan will update within ' +
    'a minute. Refresh this page if it doesn\\u2019t.');
}

// ---- change password --------------------------------------------------------

document.getElementById('pw-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  setBox('pw-error', null); setBox('pw-notice', null);
  const pw = document.getElementById('new-password').value;
  const confirm = document.getElementById('confirm-password').value;
  if (pw !== confirm) { setBox('pw-error', 'Passwords do not match.'); return; }
  const btn = document.getElementById('pw-btn');
  btn.disabled = true;
  try {
    // Supabase may refuse without a recent sign-in; its message says so.
    const { error } = await sb.auth.updateUser({ password: pw });
    if (error) throw error;
    document.getElementById('pw-form').reset();
    setBox('pw-notice', 'Password updated.');
  } catch (e) {
    setBox('pw-error', e.message || 'Could not update the password. Try signing in again first.');
  } finally {
    btn.disabled = false;
  }
});

// ---- brokerage connection ---------------------------------------------------

async function loadConnection() {
  const summary = document.getElementById('conn-summary');
  const chip = document.getElementById('conn-chip');
  const actions = document.getElementById('conn-actions');
  document.getElementById('disconnect-confirm').style.display = 'none';
  document.getElementById('disconnect-btn').style.display = 'inline-block';
  try {
    const s = await (await api('/portfolio/status')).json();
    if (s.connected) {
      chip.innerHTML = '<span class="chip-ok">\\u2713 connected</span>';
      const synced = s.last_sync_at
        ? 'Last synced ' + new Date(s.last_sync_at).toLocaleString() + '.'
        : 'Not synced yet.';
      summary.innerHTML = '<p class="muted-note" style="margin-top:0.5rem;">' +
        'Brokerage linked read-only through SnapTrade. ' + esc(synced) + '</p>';
      actions.style.display = 'block';
    } else if (s.registered) {
      chip.innerHTML = '<span class="chip-warn">not connected</span>';
      summary.innerHTML = '<p class="muted-note" style="margin-top:0.5rem;">' +
        'Registered with SnapTrade but no brokerage is linked. ' +
        '<a href="/app/onboarding">Finish connecting</a> or disconnect to clear it.</p>';
      actions.style.display = 'block';
    } else {
      chip.innerHTML = '<span class="chip-warn">not connected</span>';
      summary.innerHTML = '<p class="muted-note" style="margin-top:0.5rem;">' +
        'No brokerage linked. <a href="/app/onboarding">Connect your brokerage</a> ' +
        'to sync your holdings.</p>';
      actions.style.display = 'none';
    }
  } catch (e) {
    summary.innerHTML = '<p class="muted-note">Could not load connection status.</p>';
  }
}

document.getElementById('disconnect-btn').addEventListener('click', () => {
  setBox('conn-error', null); setBox('conn-notice', null);
  document.getElementById('disconnect-btn').style.display = 'none';
  const confirmBox = document.getElementById('disconnect-confirm');
  confirmBox.style.display = 'block';
  riseIn(confirmBox);
});

document.getElementById('disconnect-no').addEventListener('click', () => {
  document.getElementById('disconnect-confirm').style.display = 'none';
  document.getElementById('disconnect-btn').style.display = 'inline-block';
});

document.getElementById('disconnect-yes').addEventListener('click', async () => {
  const btn = document.getElementById('disconnect-yes');
  btn.disabled = true;
  setBox('conn-error', null);
  try {
    const resp = await api('/connection', { method: 'DELETE' });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Could not disconnect');
    setBox('conn-notice', data.remote_deleted
      ? 'Disconnected. Your SnapTrade link was deleted and holdings stop syncing. ' +
        'Reconnect anytime from onboarding.'
      : 'Disconnected on Cirvia and holdings stop syncing. We could not confirm ' +
        'deletion on SnapTrade\\u2019s side; contact support if you want it purged there too.');
    await loadConnection();
  } catch (e) {
    setBox('conn-error', e.message);
    document.getElementById('disconnect-confirm').style.display = 'none';
    document.getElementById('disconnect-btn').style.display = 'inline-block';
  } finally {
    btn.disabled = false;
  }
});

// ---- delete account ---------------------------------------------------------

document.getElementById('delete-btn').addEventListener('click', () => {
  setBox('delete-error', null);
  document.getElementById('delete-btn').style.display = 'none';
  const confirmBox = document.getElementById('delete-confirm');
  confirmBox.style.display = 'block';
  riseIn(confirmBox);
  document.getElementById('delete-input').focus();
});

document.getElementById('delete-no').addEventListener('click', () => {
  document.getElementById('delete-confirm').style.display = 'none';
  document.getElementById('delete-btn').style.display = 'inline-block';
  document.getElementById('delete-input').value = '';
  document.getElementById('delete-yes').disabled = true;
});

document.getElementById('delete-input').addEventListener('input', (ev) => {
  document.getElementById('delete-yes').disabled = ev.target.value !== 'DELETE';
});

document.getElementById('delete-yes').addEventListener('click', async () => {
  const btn = document.getElementById('delete-yes');
  btn.disabled = true;
  setBox('delete-error', null);
  try {
    const resp = await api('/me', { method: 'DELETE' });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Could not delete the account');
    await sb.auth.signOut();
    window.location.href = '/';
  } catch (e) {
    setBox('delete-error', e.message);
    btn.disabled = false;
  }
});

function esc(s) {
  // Quotes must be escaped too: values land inside HTML attributes.
  const d = document.createElement('div'); d.textContent = s ?? '';
  return d.innerHTML.replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

async function loadDeliveryOverview() {
  const el = document.getElementById('delivery-overview');
  try {
    const info = await (await api('/me/notifications')).json();
    const names = { sms: 'Text message', email: 'Email', discord: 'Discord' };
    const active = (info.channels || []).find(
      (c) => c.channel === info.preferred_channel);
    if (active && active.verified && !active.opted_out) {
      el.innerHTML = '<p class="muted-note" style="margin-top:0.5rem;">' +
        '<strong style="color:var(--ink);">' +
        esc(names[active.channel] || active.channel) + '</strong> · ' +
        esc(active.destination_masked) +
        ' <span class="chip-ok">\\u2713 verified</span></p>';
    } else {
      el.innerHTML = '<p class="muted-note" style="margin-top:0.5rem;">' +
        '<span class="chip-warn">Not set up</span>. Your digest only appears ' +
        'in the app until you add text, email, or Discord delivery.</p>';
    }
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load delivery settings.</p>';
  }
}

loadAccount().then(handleBillingReturn);
loadConnection();
loadDeliveryOverview();
"""


def login_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Sign in — Cirvia",
        _LOGIN_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_LOGIN_JS,
        chrome=False,
    )


def reset_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Set a new password — Cirvia",
        _RESET_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_RESET_JS,
        chrome=False,
    )


def onboarding_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Get set up — Cirvia",
        _ONBOARDING_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_DELIVERY_JS + _ONBOARDING_JS,
        wrap_class="app-wrap ob-wrap",
    )


def dashboard_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Dashboard — Cirvia",
        _DASHBOARD_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_DASHBOARD_JS,
        wrap_class="app-wrap dash-wrap",
    )


# --------------------------------------------------------------------------
# /app/risk — the visual "Risk Lab" (Pro): portfolio-level quant analytics
# --------------------------------------------------------------------------

_RISK_BODY = """
<section class="risk-head">
  <h1>Risk Lab</h1>
  <p class="risk-sub">What your portfolio's last two years of daily moves say about how it could behave next.</p>
</section>
<div id="risk-loading" class="muted-note">Computing portfolio risk&hellip;</div>
<div id="risk-gate" class="dash-card gate-card" style="display:none;">
  <h2>A Pro feature</h2>
  <p>Portfolio risk analytics — how much you could lose, what's driving it, and a thousand simulated years ahead — are part of Cirvia&nbsp;Pro.</p>
  <a class="btn" href="/app/settings?billing=upgrade">Upgrade to Pro</a>
</div>
<div id="risk-empty" class="muted-note" style="display:none;"></div>
<div id="risk-content" style="display:none;">

  <p class="risk-verdict" id="risk-verdict"></p>
  <div class="tile-row" id="risk-stats"></div>

  <div class="dash-card risk-card">
    <h2>Where the risk sits</h2>
    <p class="risk-card-sub">Each holding's share of the portfolio's risk, against the share
    of your money it holds. When the colored bar runs past the gray one, that holding is
    riskier than its size suggests.</p>
    <p class="risk-takeaway" id="bars-takeaway"></p>
    <div id="risk-bars" class="svg-box"></div>
  </div>

  <div class="dash-card risk-card">
    <h2>Do your holdings move together?</h2>
    <p class="risk-card-sub">Two holdings that always rise and fall together protect you less
    than two that don't. Brighter purple means a pair moves as one; green means they tend to
    move opposite ways.</p>
    <p class="risk-takeaway" id="corr-takeaway"></p>
    <div id="risk-heatmap" class="svg-box"></div>
    <div class="corr-scale" aria-hidden="true">
      <span>moves opposite</span><span class="corr-grad"></span><span>moves as one</span>
    </div>
  </div>

  <div class="dash-card risk-card">
    <h2>One year, a thousand ways</h2>
    <p class="risk-card-sub" id="mc-sub"></p>
    <p class="risk-takeaway" id="mc-takeaway"></p>
    <div id="risk-fan" class="svg-box"></div>
  </div>

  <div id="risk-notes" class="muted-note"></div>
  <p class="disclaimer">Statistical estimates from ~2 years of daily prices. They describe how
  your current mix has behaved, not what will happen. Not financial advice.</p>
</div>
<div id="risk-tip" class="risk-tip" role="status"></div>
"""

_RISK_JS = r"""
const fmtCad = (n) => '$' + Math.round(n).toLocaleString('en-CA');
const pct1 = (n) => (n >= 0 ? '+' : '') + n.toFixed(1) + '%';
const esc = (s) => { const d = document.createElement('div'); d.textContent = s ?? '';
  return d.innerHTML.replaceAll('"', '&quot;').replaceAll("'", '&#39;'); };

// --- shared hover tooltip -----------------------------------------------------

const tip = document.getElementById('risk-tip');
function tipShow(html, ev) {
  tip.innerHTML = html;
  tip.style.display = 'block';
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + w > innerWidth - 8) x = ev.clientX - w - pad;
  if (y + h > innerHeight - 8) y = ev.clientY - h - pad;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function tipHide() { tip.style.display = 'none'; }
function bindTips(root) {
  root.querySelectorAll('[data-tip]').forEach((el) => {
    el.addEventListener('pointermove', (ev) => tipShow(el.dataset.tip, ev));
    el.addEventListener('pointerleave', tipHide);
  });
}

// --- verdict + stat tiles -----------------------------------------------------

function tile(label, value, sub) {
  return '<div class="risk-tile"><span class="t-label">' + label + '</span>' +
    '<span class="t-value">' + value + '</span>' +
    '<span class="t-sub">' + sub + '</span></div>';
}

// The investor profile (from /me) only reorders what leads — every number is
// identical for every user; income-minded users see downside first, traders
// see swings and market sensitivity first.
function riskArchetype(prof) {
  return prof && prof.completed ? prof.archetype : 'long_term_growth';
}

function renderVerdict(s, mc, prof) {
  const swing = 'Your <strong>' + fmtCad(s.portfolio_value_cad) + '</strong> portfolio has been swinging about <strong>&plusmn;' +
    s.annualized_volatility_pct.toFixed(0) + '%</strong> a year.';
  const beta = s.portfolio_beta !== null
    ? 'When the market drops 1%, it has tended to drop about <strong>' +
      s.portfolio_beta.toFixed(1) + '%</strong>.'
    : null;
  const badDay = 'On its worst 1-in-20 days this portfolio loses <strong>' +
    fmtCad(s.var95_1d_cad) + '</strong> or more.';
  const arch = riskArchetype(prof);
  const parts = arch === 'income_preservation'
    ? [badDay, swing, beta]
    : arch === 'day_trader'
      ? [swing, beta, badDay]
      : [swing, beta, badDay];
  document.getElementById('risk-verdict').innerHTML =
    parts.filter(Boolean).join(' ');
}

function renderStats(s, prof) {
  const dollarsPerPct = s.portfolio_value_cad / 100;
  const cards = {
    swing: tile('Typical yearly swing', '&plusmn;' + s.annualized_volatility_pct.toFixed(0) + '%',
      'about ' + fmtCad(s.annualized_volatility_pct * dollarsPerPct) +
      ' up or down in an ordinary year'),
    badday: tile('A bad day', '&minus;' + fmtCad(s.var95_1d_cad),
      'your worst 1-in-20 days lose at least this (' + s.var95_1d_pct.toFixed(1) +
      '%); the average of those days is ' + s.cvar95_1d_pct.toFixed(1) + '%'),
    bets: tile('Really independent bets', '~' + s.effective_number_of_bets.toFixed(0),
      'you hold ' + s.holdings_analyzed + ' names, but overlap makes them act like ' +
      s.effective_number_of_bets.toFixed(0)),
    divers: tile('Diversification is working', '&minus;' + s.diversification_benefit_pct.toFixed(0) + ' pts',
      'mixing holdings cancels volatility: ' + s.weighted_avg_volatility_pct.toFixed(0) +
      '% if they moved alone, ' + s.annualized_volatility_pct.toFixed(0) + '% together'),
    beta: null,
    sharpe: null,
  };
  if (s.portfolio_beta !== null) {
    cards.beta = tile('Moves with the market', s.portfolio_beta.toFixed(2) + '×',
      'a 1% market move has meant about ' + s.portfolio_beta.toFixed(1) + '% for you, both directions');
  }
  if (s.sharpe_ratio !== null) {
    cards.sharpe = tile('Return earned per unit of risk', s.sharpe_ratio.toFixed(2),
      s.sharpe_ratio >= 1 ? 'above 1 means the swings have been paying for themselves so far'
        : 'below 1 means the returns have been small for the swings endured');
  }
  const ORDER = {
    day_trader: ['swing', 'beta', 'badday', 'sharpe', 'bets', 'divers'],
    swing_trader: ['swing', 'badday', 'beta', 'sharpe', 'bets', 'divers'],
    long_term_growth: ['swing', 'badday', 'bets', 'divers', 'beta', 'sharpe'],
    income_preservation: ['badday', 'divers', 'swing', 'bets', 'beta', 'sharpe'],
  };
  const order = ORDER[riskArchetype(prof)] || ORDER.long_term_growth;
  document.getElementById('risk-stats').innerHTML =
    order.map((k) => cards[k]).filter(Boolean).join('');
}

// --- where the risk sits (paired bars) ------------------------------------------

function roundRight(x, y, w, h) {
  // Bar with a 4px rounded data-end, square at the baseline.
  const r = Math.min(4, w);
  return 'M' + x + ' ' + y + ' h' + Math.max(0, w - r) +
    ' a' + r + ' ' + r + ' 0 0 1 ' + r + ' ' + r +
    ' v' + (h - 2 * r) + ' a' + r + ' ' + r + ' 0 0 1 ' + (-r) + ' ' + r +
    ' h' + (-Math.max(0, w - r)) + ' Z';
}

function renderBars(holdings, s) {
  const el = document.getElementById('risk-bars');
  const top = holdings[0];
  if (top) {
    document.getElementById('bars-takeaway').innerHTML =
      '<strong>' + esc(top.ticker) + '</strong> alone drives ' +
      top.risk_contribution_pct.toFixed(0) + '% of your risk with ' +
      top.weight_pct.toFixed(0) + '% of your money.';
  }
  const maxv = Math.max(1, ...holdings.map(h => Math.max(h.weight_pct, h.risk_contribution_pct)));
  const rowH = 42, pad = 6, labelW = 84, barW = 430, valW = 150;
  const W = labelW + barW + valW, H = holdings.length * rowH + pad * 2;
  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H +
    '" style="min-width:560px;width:100%;height:auto;" role="img" aria-label="Each holding’s risk contribution versus its capital weight">';
  holdings.forEach((h, i) => {
    const y = pad + i * rowH;
    const wLen = Math.max(1.5, (h.weight_pct / maxv) * barW);
    const rLen = Math.max(1.5, (h.risk_contribution_pct / maxv) * barW);
    const t = esc(h.ticker);
    const tipHtml = '<strong>' + t + '</strong><br>' + h.risk_contribution_pct.toFixed(1) +
      '% of portfolio risk<br>' + h.weight_pct.toFixed(1) + '% of capital' +
      '<br><span class=&quot;tip-sub&quot;>own volatility ' + h.annualized_vol_pct.toFixed(0) + '%/yr</span>';
    svg += '<g class="bar-row" data-tip="' + tipHtml + '">';
    svg += '<text x="0" y="' + (y + 20) + '" class="svg-lbl">' + t + '</text>';
    svg += '<path d="' + roundRight(labelW, y + 4, rLen, 12) + '" class="bar-risk"></path>';
    svg += '<path d="' + roundRight(labelW, y + 20, wLen, 12) + '" class="bar-weight"></path>';
    svg += '<text x="' + (labelW + Math.max(wLen, rLen) + 8) + '" y="' + (y + 21) + '" class="svg-val">' +
      h.risk_contribution_pct.toFixed(0) + '% risk &middot; ' + h.weight_pct.toFixed(0) + '% money</text>';
    svg += '<rect x="0" y="' + y + '" width="' + W + '" height="' + rowH + '" class="bar-hit"></rect>';
    svg += '</g>';
  });
  svg += '</svg>';
  el.innerHTML = svg +
    '<div class="legend"><span><i class="sw bar-risk"></i>Share of risk</span>' +
    '<span><i class="sw bar-weight"></i>Share of money</span></div>';
  bindTips(el);
}

// --- correlation heatmap --------------------------------------------------------

function corrColor(c) {
  // Diverging on the card surface: green (moves opposite) <- near-white -> violet
  // (moves as one). Cells darken and saturate with |c|; hue only carries the sign.
  const a = Math.abs(c);
  const l = 95 - 43 * a;
  const ch = 0.005 + (c >= 0 ? 0.165 : 0.115) * a;
  const h = c >= 0 ? 295 : 155;
  return 'oklch(' + l.toFixed(1) + '% ' + ch.toFixed(3) + ' ' + h + ')';
}

function renderHeatmap(corr) {
  const el = document.getElementById('risk-heatmap');
  const n = corr.tickers.length;
  // Strongest off-diagonal pairs drive the takeaway sentence.
  const pairs = [];
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    pairs.push([corr.tickers[i], corr.tickers[j], corr.matrix[i][j]]);
  }
  pairs.sort((a, b) => Math.abs(b[2]) - Math.abs(a[2]));
  if (pairs.length) {
    const topPairs = pairs.slice(0, 2).map((p) =>
      '<strong>' + esc(p[0]) + '</strong> and <strong>' + esc(p[1]) + '</strong> (' +
      p[2].toFixed(2) + ')').join(', then ');
    document.getElementById('corr-takeaway').innerHTML =
      'Most joined at the hip: ' + topPairs + '. 1.00 means always together, 0 means unrelated.';
  }
  const cell = 26, gap = 2, lblL = 66, lblT = 56;
  const W = lblL + n * cell + 40, H = lblT + n * cell + 6;
  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H +
    '" style="height:auto;" role="img" aria-label="Correlation between each pair of holdings">';
  corr.tickers.forEach((t, j) => {
    const cx = lblL + j * cell + cell / 2;
    svg += '<text x="' + cx + '" y="' + (lblT - 8) + '" class="svg-val heat-col" transform="rotate(-45 ' +
      cx + ' ' + (lblT - 8) + ')">' + esc(t) + '</text>';
    svg += '<text x="' + (lblL - 8) + '" y="' + (lblT + j * cell + cell / 2 + 4) + '" class="svg-val heat-row">' + esc(t) + '</text>';
  });
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const c = corr.matrix[i][j];
      const x = lblL + j * cell, y = lblT + i * cell;
      if (i === j) {
        svg += '<rect x="' + x + '" y="' + y + '" width="' + (cell - gap) + '" height="' + (cell - gap) +
          '" rx="3" fill="var(--surface-2)"></rect>';
        continue;
      }
      const a = esc(corr.tickers[i]), b = esc(corr.tickers[j]);
      const phrase = c >= 0.7 ? 'move as one' : c >= 0.4 ? 'often move together'
        : c >= 0.15 ? 'loosely related' : c > -0.15 ? 'mostly unrelated' : 'tend to move opposite';
      svg += '<rect x="' + x + '" y="' + y + '" width="' + (cell - gap) + '" height="' + (cell - gap) +
        '" rx="3" fill="' + corrColor(c) + '" data-tip="<strong>' + a + ' &middot; ' + b +
        '</strong><br>' + c.toFixed(2) + ' &mdash; ' + phrase + '"></rect>';
    }
  }
  svg += '</svg>';
  el.innerHTML = svg;
  bindTips(el);
}

// --- one year, a thousand ways (Monte Carlo fan) ---------------------------------

function renderFan(mc, s) {
  const el = document.getElementById('risk-fan');
  const value = s.portfolio_value_cad;
  const b = mc.bands_pct, p5 = b.p5, p95 = b.p95, p25 = b.p25, p75 = b.p75, p50 = b.p50;
  const m = p5.length, W = 680, H = 300, padL = 52, padR = 132, padT = 14, padB = 28;
  const lo = Math.min(...p5), hi = Math.max(...p95);
  const span = Math.max(1e-6, hi - lo);
  const x = (i) => padL + (i / (m - 1)) * (W - padL - padR);
  const y = (v) => padT + (1 - (v - lo) / span) * (H - padT - padB);
  const line = (arr) => arr.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join(' ');
  const band = (top, bot) => 'M' + top.map((v, i) => x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join(' L') +
    ' L' + bot.map((v, i) => x(i).toFixed(1) + ' ' + y(v).toFixed(1)).reverse().join(' L') + ' Z';
  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H +
    '" style="min-width:560px;width:100%;height:auto;" role="img" aria-label="Simulated one-year outcomes">';
  // Clean percent gridlines.
  const step = span > 120 ? 50 : span > 60 ? 25 : 10;
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
    if (v === 0) continue;
    svg += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + y(v) + '" y2="' + y(v) + '" class="grid-line"></line>';
    svg += '<text x="' + (padL - 8) + '" y="' + (y(v) + 4) + '" text-anchor="end" class="svg-tick">' + pct1(v) + '</text>';
  }
  if (lo < 0 && hi > 0) {
    svg += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + y(0) + '" y2="' + y(0) + '" class="fan-zero"></line>';
    svg += '<text x="' + (padL - 8) + '" y="' + (y(0) + 4) + '" text-anchor="end" class="svg-tick">today</text>';
  }
  svg += '<path d="' + band(p95, p5) + '" class="fan-outer"></path>';
  svg += '<path d="' + band(p75, p25) + '" class="fan-inner"></path>';
  svg += '<path d="' + line(p50) + '" class="fan-median"></path>';
  // Month ticks (the last one anchors end so it can't run under the end labels).
  [[0, 'now', 'middle'], [0.25, '3 mo', 'middle'], [0.5, '6 mo', 'middle'],
   [0.75, '9 mo', 'middle'], [1, '1 yr', 'end']].forEach(([f, lbl, anchor]) => {
    svg += '<text x="' + (padL + f * (W - padL - padR)) + '" y="' + (H - 8) +
      '" text-anchor="' + anchor + '" class="svg-tick">' + lbl + '</text>';
  });
  // Direct end labels: the outcomes people should take away, in dollars.
  // Two-line blocks, collision-resolved so converging bands can't overlap them.
  const endDefs = [[p95, 'a great year'], [p50, 'the middle path'], [p5, 'a brutal year']]
    .map(([arr, name]) => ({ v: arr[arr.length - 1], name, y: y(arr[arr.length - 1]) }))
    .sort((a, b) => a.y - b.y);
  const blockH = 32, minY = padT + 10, maxY = H - padB - 10;
  endDefs.forEach((d, i) => { if (i) d.y = Math.max(d.y, endDefs[i - 1].y + blockH); });
  for (let i = endDefs.length - 1; i >= 0; i--) {
    const cap = i === endDefs.length - 1 ? maxY : endDefs[i + 1].y - blockH;
    endDefs[i].y = Math.min(endDefs[i].y, cap);
    if (i === 0) endDefs[i].y = Math.max(endDefs[i].y, minY);
  }
  endDefs.forEach((d) => {
    svg += '<text x="' + (W - padR + 10) + '" y="' + (d.y + 4) + '" class="fan-endlbl">' +
      fmtCad(value * (1 + d.v / 100)) + '</text>' +
      '<text x="' + (W - padR + 10) + '" y="' + (d.y + 17) + '" class="fan-endsub">' +
      d.name + ' (' + pct1(d.v) + ')</text>';
  });
  // Invisible hover columns: a readout per month position.
  const months = 12;
  for (let k = 0; k <= months; k++) {
    const i = Math.round((k / months) * (m - 1));
    const tipHtml = '<strong>' + (k === 0 ? 'Today' : k + ' month' + (k > 1 ? 's' : '') + ' out') +
      '</strong><br>middle path ' + fmtCad(value * (1 + p50[i] / 100)) +
      '<br><span class=&quot;tip-sub&quot;>90% of simulations between ' +
      fmtCad(value * (1 + p5[i] / 100)) + ' and ' + fmtCad(value * (1 + p95[i] / 100)) + '</span>';
    const cx = x(i), half = (W - padL - padR) / months / 2;
    svg += '<rect x="' + (cx - half) + '" y="0" width="' + (2 * half) + '" height="' + H +
      '" class="bar-hit" data-tip="' + tipHtml + '"></rect>';
  }
  svg += '</svg>';
  el.innerHTML = svg;
  bindTips(el);
  document.getElementById('mc-sub').textContent =
    'We replayed the next 12 months ' + mc.simulations.toLocaleString() +
    ' times, using only how your holdings have moved and co-moved for two years (no growth assumed). ' +
    'The shaded range holds 90% of those futures; the line is the middle one.';
  document.getElementById('mc-takeaway').innerHTML =
    Math.round(mc.probability_of_loss_pct) + '% of the simulated years ended below today’s ' +
    fmtCad(value) + '. The middle 90% landed between <strong>' +
    fmtCad(value * (1 + p5[p5.length - 1] / 100)) + '</strong> and <strong>' +
    fmtCad(value * (1 + p95[p95.length - 1] / 100)) + '</strong>.';
}

async function loadRisk() {
  let resp, prof = null;
  try {
    const [r, meResp] = await Promise.all([
      api('/portfolio/risk-analytics'),
      api('/me').catch(() => null),  // profile is advisory: ordering only
    ]);
    resp = r;
    if (meResp && meResp.ok) prof = (await meResp.json()).profile || null;
  }
  catch (e) { return; }
  document.getElementById('risk-loading').style.display = 'none';
  if (resp.status === 402) { document.getElementById('risk-gate').style.display = 'block'; return; }
  if (!resp.ok) { const el = document.getElementById('risk-empty'); el.style.display = 'block'; el.textContent = 'Risk analytics are unavailable right now.'; return; }
  const data = await resp.json();
  if (!data.available) { const el = document.getElementById('risk-empty'); el.style.display = 'block'; el.textContent = data.note || 'Not enough data to analyze.'; return; }
  document.getElementById('risk-content').style.display = 'block';
  renderVerdict(data.summary, data.monte_carlo, prof);
  renderStats(data.summary, prof);
  renderBars(data.holdings, data.summary);
  renderHeatmap(data.correlation);
  renderFan(data.monte_carlo, data.summary);
  if (data.notes && data.notes.length) document.getElementById('risk-notes').textContent = data.notes.join(' ');
  document.querySelectorAll('.risk-card, .risk-tile').forEach((s) => riseIn(s));
}

requireSession().then((ok) => { if (ok) loadRisk(); });
"""

_RISK_CSS = """
/* Chart data colors. Risk/identity is the brand violet; the capital-weight
   reference bar is a deliberate neutral (low chroma at 65% L keeps >3:1 against
   the white card per WCAG 1.4.11; per-row value labels carry the exact values). */
.risk-wrap { max-width: 880px; }
.risk-head h1 { margin-bottom: 0.3rem; }
.risk-head .risk-sub { color: var(--ink-2); margin-bottom: 1.4rem; max-width: 60ch; }
.risk-verdict { font-size: 1.15rem; line-height: 1.5; color: var(--ink);
  max-width: 62ch; margin: 0 0 1.1rem; text-wrap: pretty; }
.risk-verdict strong { color: var(--accent-text); font-weight: 650; }
/* stat tiles: label / value / plain-language sub */
.tile-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 0.75rem; margin-bottom: 1rem; }
.risk-tile { background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-m); padding: 0.85rem 1rem 0.9rem; }
.risk-tile .t-label { display: block; font-size: 0.82rem; font-weight: 600;
  color: var(--ink-3); }
.risk-tile .t-value { display: block; font-size: 1.45rem; font-weight: 650;
  color: var(--ink); margin: 0.1rem 0 0.15rem; letter-spacing: -0.01em; }
.risk-tile .t-sub { display: block; font-size: 0.82rem; line-height: 1.45;
  color: var(--ink-2); }
.risk-card { margin-bottom: 1rem; }
.risk-card h2 { font-size: 1.1rem; margin-bottom: 0.3rem; }
.risk-card-sub { color: var(--ink-2); font-size: 0.9rem; line-height: 1.5;
  max-width: 68ch; margin: 0 0 0.35rem; }
.risk-takeaway { color: var(--ink); font-size: 0.92rem; line-height: 1.5;
  max-width: 68ch; margin: 0 0 0.4rem; }
.risk-takeaway strong { color: var(--accent-text); font-weight: 650; }
.svg-box { overflow-x: auto; margin-top: 0.5rem; }
.svg-box svg { display: block; }
.svg-lbl { fill: var(--ink-2); font-size: 12px; font-weight: 600; }
.svg-val { fill: var(--ink-3); font-size: 11px; font-variant-numeric: tabular-nums; }
.svg-tick { fill: var(--ink-3); font-size: 11px; font-variant-numeric: tabular-nums; }
.heat-col { text-anchor: start; }
.heat-row { text-anchor: end; }
.bar-weight { fill: oklch(65% 0.02 300); }
.bar-risk { fill: oklch(55% 0.17 295); }
.bar-hit { fill: transparent; }
.bar-row:hover .bar-risk { fill: oklch(47% 0.17 295); }
.legend { display: flex; gap: 1.1rem; font-size: 0.8rem; color: var(--ink-3);
  margin-top: 0.5rem; }
.legend .sw { display: inline-block; width: 11px; height: 11px; border-radius: 3px;
  margin-right: 5px; vertical-align: -1px; }
.corr-scale { display: flex; align-items: center; gap: 0.6rem; margin-top: 0.55rem;
  font-size: 0.78rem; color: var(--ink-3); }
.corr-grad { flex: 0 1 220px; height: 8px; border-radius: 4px;
  background: linear-gradient(90deg, oklch(55% 0.12 155), oklch(96% 0.005 300) 50%, oklch(52% 0.17 295)); }
.grid-line { stroke: var(--line); stroke-width: 1; }
.fan-outer { fill: oklch(52% 0.17 295); opacity: 0.14; }
.fan-inner { fill: oklch(52% 0.17 295); opacity: 0.30; }
.fan-median { stroke: var(--accent-text); stroke-width: 2; fill: none;
  stroke-linejoin: round; stroke-linecap: round; }
.fan-zero { stroke: var(--line-strong); stroke-width: 1; }
.fan-endlbl { fill: var(--ink-2); font-size: 11.5px; font-weight: 600;
  font-variant-numeric: tabular-nums; }
.fan-endsub { fill: var(--ink-3); font-size: 10.5px; font-variant-numeric: tabular-nums; }
/* shared hover tooltip */
.risk-tip { position: fixed; z-index: 40; display: none; pointer-events: none;
  background: var(--surface-3); border: 1px solid var(--line-strong);
  border-radius: var(--r-s); padding: 0.4rem 0.6rem; font-size: 0.8rem;
  color: var(--ink); max-width: 260px; line-height: 1.45;
  box-shadow: 0 8px 24px oklch(35% 0.05 300 / 0.18); }
.risk-tip .tip-sub { color: var(--ink-3); }
.gate-card { text-align: center; }
.gate-card .btn { margin-top: 0.6rem; }
.disclaimer { font-size: 0.78rem; color: var(--ink-3); margin-top: 1rem;
  max-width: 68ch; }
@media (max-width: 640px) { .risk-verdict { font-size: 1.02rem; } }
"""


def risk_lab_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Risk Lab — Cirvia",
        f"<style>{_RISK_CSS}</style>{_RISK_BODY}",
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_RISK_JS,
        wrap_class="app-wrap risk-wrap",
    )


# --------------------------------------------------------------------------
# /app/picks — daily Best Stocks dashboard (Pro)
# --------------------------------------------------------------------------

_PICKS_BODY = """
<section class="picks-head">
  <h1>Top Picks</h1>
  <p class="picks-sub">Every market morning, a quantitative screen ranks ~560 US and Canadian
  large caps, and analyst agents research the strongest candidates. Every number is computed
  from source data and machine-verified; every claim is adversarially checked.</p>
</section>
<div id="picks-loading" class="muted-note">Loading today's analysis&hellip;</div>
<div id="picks-gate" class="dash-card gate-card" style="display:none;">
  <h2>A Pro feature</h2>
  <p>The daily Top Picks dashboard — ranked candidates with verified evidence, what's moving
  and why, and a public track record — is part of Cirvia&nbsp;Pro.</p>
  <a class="btn" href="/app/settings?billing=upgrade">Upgrade to Pro</a>
</div>
<div id="picks-empty" class="muted-note" style="display:none;"></div>
<div id="picks-content" style="display:none;">
  <p class="picks-meta" id="picks-meta"></p>
  <p class="warn-banner" id="picks-stale" style="display:none;"></p>

  <div class="dash-card picks-card" id="picks-overview-card" style="display:none;">
    <h2 id="picks-headline"></h2>
    <div id="picks-overview"></div>
  </div>

  <div class="dash-card picks-card" id="movers-card" style="display:none;">
    <h2>What's moving</h2>
    <p class="picks-card-sub">Statistically unusual daily moves across the universe, with the
    catalyst when the news actually explains it &mdash; never a guessed reason.</p>
    <div id="picks-movers"></div>
  </div>

  <h2 class="picks-section-h" id="picks-list-h">Today's ranked candidates</h2>
  <div id="picks-list"></div>

  <div class="dash-card picks-card" id="track-card" style="display:none;">
    <h2>Track record</h2>
    <p class="picks-card-sub" id="track-sub"></p>
    <div id="track-body"></div>
  </div>

  <details class="picks-method">
    <summary>How this is built</summary>
    <p>An evening job stores adjusted prices and fundamentals for the S&amp;P&nbsp;500 and
    TSX&nbsp;60. Pre-market, a factor model scores every eligible name against its sector on
    value, quality, growth, momentum, analyst upside, and risk &mdash; pure math, no AI.
    Only the top-ranked names go to analyst agents, which must ground every figure in the
    computed fact sheet. A verifier then re-checks the numbers deterministically and an
    adversarial critic re-checks the claims with its own data pulls; picks with challenged
    claims are demoted and flagged. Confidence is a computed score (rank strength, data
    coverage, verification results), not the model's opinion.</p>
  </details>
  <p class="disclaimer" id="picks-disclaimer"></p>
</div>
"""

_PICKS_JS = r"""
const esc = (s) => { const d = document.createElement('div'); d.textContent = s ?? '';
  return d.innerHTML.replaceAll('"', '&quot;').replaceAll("'", '&#39;'); };
const pctFmt = (n) => (n >= 0 ? '+' : '') + Number(n).toFixed(2) + '%';

function confMeter(c) {
  if (c === null || c === undefined) return '';
  const pct = Math.round(c * 100);
  const band = c >= 0.7 ? 'high' : c >= 0.45 ? 'mid' : 'low';
  return '<span class="conf" title="Computed confidence: rank strength, data coverage, and verification results">' +
    '<span class="conf-track"><span class="conf-fill conf-' + band + '" style="width:' + pct + '%"></span></span>' +
    '<span class="conf-num">' + pct + '</span></span>';
}

function evidenceTable(ev) {
  if (!ev || !ev.length) return '';
  const rows = ev.map((e) =>
    '<tr><td>' + esc(e.metric.replaceAll('_', ' ')) + '</td>' +
    '<td>' + (e.value ?? '—') + '</td>' +
    '<td>' + (e.sector_median ?? '—') + '</td></tr>').join('');
  return '<table class="ev-table"><thead><tr><th>metric</th><th>this stock</th>' +
    '<th>sector median</th></tr></thead><tbody>' + rows + '</tbody></table>';
}

function verifyBadge(v, demoted) {
  if (!v || !v.critic_ran) return '<span class="vbadge v-un">unverified</span>';
  if (demoted) return '<span class="vbadge v-bad">' + v.challenged + ' claims challenged</span>';
  if (v.checked === 0) return '<span class="vbadge v-un">not spot-checked</span>';
  const label = v.verified + '/' + v.checked + ' claims verified' +
    (v.challenged ? ', ' + v.challenged + ' challenged' : '');
  return '<span class="vbadge ' + (v.challenged ? 'v-mixed' : 'v-ok') + '">' + label + '</span>';
}

function riskList(risks) {
  if (!risks || !risks.length) return '';
  return '<ul class="pick-risks">' + risks.map((r) =>
    '<li><span class="sev sev-' + esc(r.severity || 'medium') + '"></span>' + esc(r.text) + '</li>'
  ).join('') + '</ul>';
}

function pickCard(p, i) {
  const quantOnly = p.analysis !== 'ok';
  let body = '';
  if (quantOnly) {
    body = '<p class="pick-thesis muted-note">Quantitative scores only — the analyst stage was ' +
      'unavailable for this name.</p>';
  } else {
    body = '<p class="pick-thesis">' + esc(p.thesis) + '</p>' +
      (p.why_now ? '<p class="pick-whynow"><strong>Why now:</strong> ' + esc(p.why_now) + '</p>' : '') +
      evidenceTable(p.valuation_evidence) +
      riskList(p.risks);
  }
  const factors = p.factors || {};
  const chips = Object.entries(factors).filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => '<span class="fchip' + (v >= 0 ? ' fpos' : ' fneg') + '">' +
      esc(k.replaceAll('_', ' ')) + ' ' + (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '</span>').join('');
  return '<div class="dash-card pick-card' + (p.demoted ? ' pick-demoted' : '') + '">' +
    '<div class="pick-top">' +
      '<span class="pick-rank">#' + (i + 1) + '</span>' +
      '<span class="pick-id"><span class="pick-ticker">' + esc(p.ticker) + '</span>' +
        '<span class="pick-name">' + esc(p.name || '') + (p.sector ? ' · ' + esc(p.sector) : '') + '</span></span>' +
      confMeter(p.confidence) +
    '</div>' +
    (p.demoted ? '<p class="demote-note">The verifier challenged parts of this analysis — ranked down and shown for transparency.</p>' : '') +
    body +
    '<div class="pick-foot">' + chips + verifyBadge(p.verification, p.demoted) + '</div>' +
  '</div>';
}

function renderMovers(movers) {
  if (!movers || !movers.length) return;
  document.getElementById('movers-card').style.display = 'block';
  document.getElementById('picks-movers').innerHTML = movers.map((m) =>
    '<div class="mover-row">' +
      '<span class="mover-move ' + (m.direction === 'up' ? 'gain' : 'loss') + '">' +
        pctFmt(m.day_return_pct ?? 0) + '</span>' +
      '<span class="mover-id"><strong>' + esc(m.ticker) + '</strong>' +
        (m.name ? ' <span class="mover-name">' + esc(m.name) + '</span>' : '') + '</span>' +
      '<span class="mover-why' + (m.news_grounded ? '' : ' mover-nocat') + '">' + esc(m.why) + '</span>' +
    '</div>').join('');
}

async function loadTrackRecord() {
  let resp;
  try { resp = await api('/stocks/picks/track-record'); } catch (e) { return; }
  if (!resp.ok) return;
  const data = await resp.json();
  if (!data.available || !data.summary || !data.summary.measured) return;
  const s = data.summary;
  document.getElementById('track-card').style.display = 'block';
  document.getElementById('track-sub').textContent =
    'Every pick is logged at its price on pick day and measured against the S&P 500 — ' +
    'no cherry-picking, the record is what it is.';
  let html = '<p class="track-line">' + s.measured + ' picks measured · average ' +
    pctFmt(s.avg_return_pct) + ' since pick' +
    (s.hit_rate_pct !== null ? ' · ' + s.hit_rate_pct + '% beat the index over the same span' : '') + '</p>';
  document.getElementById('track-body').innerHTML = html;
}

async function loadPicks() {
  let resp;
  try { resp = await api('/stocks/picks'); }
  catch (e) { return; }
  document.getElementById('picks-loading').style.display = 'none';
  if (resp.status === 402) { document.getElementById('picks-gate').style.display = 'block'; return; }
  if (!resp.ok) { const el = document.getElementById('picks-empty'); el.style.display = 'block';
    el.textContent = 'Picks are unavailable right now.'; return; }
  const data = await resp.json();
  if (!data.available) { const el = document.getElementById('picks-empty'); el.style.display = 'block';
    el.textContent = data.note || 'No analysis yet.'; return; }
  document.getElementById('picks-content').style.display = 'block';

  const uni = data.universe || {};
  document.getElementById('picks-meta').textContent =
    'Analysis for ' + data.as_of + ' · prices through ' + (data.data_as_of || data.as_of) +
    ' · ' + (uni.size || '—') + ' names screened, ' +
    ((data.coverage || {}).ranked ?? '—') + ' ranked';
  if (data.stale) { const st = document.getElementById('picks-stale');
    st.style.display = 'block'; st.textContent = data.stale_note; }

  if (data.overview) {
    document.getElementById('picks-overview-card').style.display = 'block';
    document.getElementById('picks-headline').textContent = data.headline || 'Today';
    document.getElementById('picks-overview').innerHTML =
      data.overview.split('\n').filter(Boolean).map((p) => '<p>' + esc(p) + '</p>').join('');
  }
  renderMovers(data.movers);
  const picks = data.picks || [];
  document.getElementById('picks-list').innerHTML = picks.map(pickCard).join('');
  document.getElementById('picks-disclaimer').textContent = data.disclaimer || '';
  loadTrackRecord();
  document.querySelectorAll('.pick-card, .picks-card').forEach((el) => riseIn(el));
}

requireSession().then((ok) => { if (ok) loadPicks(); });
"""

_PICKS_CSS = """
.picks-wrap { max-width: 880px; }
.picks-head h1 { margin-bottom: 0.3rem; }
.picks-head .picks-sub { color: var(--ink-2); margin-bottom: 1.1rem; max-width: 66ch; }
.picks-meta { color: var(--ink-3); font-size: 0.85rem; margin: 0 0 1rem;
  font-variant-numeric: tabular-nums; }
.picks-card { margin-bottom: 1rem; }
.picks-card h2 { font-size: 1.1rem; margin-bottom: 0.3rem; }
.picks-card-sub { color: var(--ink-2); font-size: 0.9rem; line-height: 1.5;
  max-width: 68ch; margin: 0 0 0.6rem; }
#picks-overview p { color: var(--ink); line-height: 1.55; max-width: 68ch;
  margin: 0.4rem 0 0; }
.picks-section-h { font-size: 1.1rem; margin: 1.3rem 0 0.7rem; }
/* movers */
.mover-row { display: flex; align-items: baseline; gap: 0.7rem; padding: 0.45rem 0;
  border-top: 1px solid var(--line); }
.mover-row:first-child { border-top: 0; }
.mover-move { flex: 0 0 4.2rem; text-align: right; font-weight: 650;
  font-variant-numeric: tabular-nums; }
.mover-move.gain { color: var(--gain); } .mover-move.loss { color: var(--loss); }
.mover-id { flex: 0 0 11rem; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.mover-name { color: var(--ink-3); font-size: 0.85rem; }
.mover-why { color: var(--ink-2); font-size: 0.88rem; line-height: 1.45; }
.mover-nocat { color: var(--ink-3); font-style: italic; }
/* pick cards */
.pick-card { margin-bottom: 0.9rem; }
.pick-demoted { opacity: 0.82; }
.pick-top { display: flex; align-items: center; gap: 0.75rem; }
.pick-rank { flex: none; font-size: 0.95rem; font-weight: 650; color: var(--accent-text);
  font-variant-numeric: tabular-nums; }
.pick-id { flex: 1 1 auto; min-width: 0; }
.pick-ticker { font-weight: 650; font-size: 1.05rem; margin-right: 0.5rem; }
.pick-name { color: var(--ink-3); font-size: 0.86rem; }
.conf { flex: none; display: inline-flex; align-items: center; gap: 0.45rem; }
.conf-track { width: 74px; height: 7px; border-radius: 4px; background: var(--surface-3);
  overflow: hidden; display: inline-block; }
.conf-fill { display: block; height: 100%; border-radius: 4px; }
.conf-high { background: oklch(55% 0.12 155); }
.conf-mid { background: oklch(55% 0.17 295); }
.conf-low { background: oklch(70% 0.02 300); }
.conf-num { font-size: 0.8rem; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.demote-note { color: var(--warn); font-size: 0.85rem; margin: 0.5rem 0 0; }
.pick-thesis { color: var(--ink); line-height: 1.55; margin: 0.65rem 0 0; max-width: 70ch; }
.pick-whynow { color: var(--ink-2); font-size: 0.92rem; line-height: 1.5;
  margin: 0.45rem 0 0; max-width: 70ch; }
.pick-whynow strong { color: var(--ink); }
.ev-table { margin-top: 0.7rem; border-collapse: collapse; font-size: 0.85rem;
  font-variant-numeric: tabular-nums; }
.ev-table th { text-align: left; color: var(--ink-3); font-weight: 600;
  padding: 0.25rem 1.1rem 0.25rem 0; border-bottom: 1px solid var(--line); }
.ev-table td { padding: 0.3rem 1.1rem 0.3rem 0; border-bottom: 1px solid var(--line);
  color: var(--ink-2); }
.ev-table td:first-child { color: var(--ink); }
.pick-risks { margin: 0.7rem 0 0; padding: 0; list-style: none; }
.pick-risks li { display: flex; gap: 0.5rem; align-items: baseline; color: var(--ink-2);
  font-size: 0.9rem; line-height: 1.5; margin-top: 0.25rem; max-width: 70ch; }
.sev { flex: none; width: 8px; height: 8px; border-radius: 50%; display: inline-block;
  transform: translateY(-1px); }
.sev-low { background: var(--ink-3); }
.sev-medium { background: var(--warn); }
.sev-high { background: var(--loss); }
.pick-foot { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center;
  margin-top: 0.85rem; }
.fchip { font-size: 0.74rem; color: var(--ink-3); border: 1px solid var(--line);
  border-radius: 999px; padding: 0.12rem 0.55rem; font-variant-numeric: tabular-nums; }
.fchip.fpos { color: var(--ink-2); }
.vbadge { margin-left: auto; font-size: 0.78rem; border-radius: 999px;
  padding: 0.16rem 0.6rem; border: 1px solid var(--line-strong); }
.v-ok { color: var(--gain); }
.v-mixed { color: var(--warn); }
.v-bad { color: var(--loss); }
.v-un { color: var(--ink-3); }
.track-line { color: var(--ink); font-size: 0.95rem; font-variant-numeric: tabular-nums; }
.picks-method { margin: 1.2rem 0 0; color: var(--ink-2); font-size: 0.9rem;
  max-width: 70ch; }
.picks-method summary { cursor: pointer; color: var(--ink-3); font-weight: 600;
  font-size: 0.86rem; }
.picks-method p { margin-top: 0.5rem; line-height: 1.55; }
.gate-card { text-align: center; }
.gate-card .btn { margin-top: 0.6rem; }
.disclaimer { font-size: 0.78rem; color: var(--ink-3); margin-top: 1rem; max-width: 68ch; }
@media (max-width: 640px) {
  .mover-id { flex-basis: 6.5rem; }
  .mover-row { flex-wrap: wrap; }
  .mover-why { flex-basis: 100%; }
}
"""


def picks_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Top Picks — Cirvia",
        f"<style>{_PICKS_CSS}</style>{_PICKS_BODY}",
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_PICKS_JS,
        wrap_class="app-wrap picks-wrap",
    )


# --------------------------------------------------------------------------
# /app/deep-dives — deep-dive report history + full report view
# --------------------------------------------------------------------------

_DEEP_DIVES_BODY = """\
<div class="dash-card">
  <h3>Deep Dive reports <span class="tag">Pro</span></h3>
  <p class="muted-note" style="margin-top:0.5rem;">Every deep dive you run is
  kept here. Pick a report on the left to read the full findings — each claim
  carries the verifier's verdict.</p>
  <div class="dd-layout">
    <div class="dd-list" id="dd-list"></div>
    <div id="dd-detail"><p class="muted-note">Loading…</p></div>
  </div>
</div>
"""

_DEEP_DIVES_JS = """\
const DDP_SPECIALISTS = {
  fundamentals: 'Fundamentals', technical: 'Technical',
  risk: 'Risk', news_macro: 'News & macro',
};
let ddpReports = [];

function ddpBadge(verification) {
  const b = document.createElement('span');
  b.className = 'dd-badge ' + (verification === 'verified' ? 'verified'
    : verification === 'challenged' ? 'challenged' : '');
  b.textContent = verification === 'verified' ? '✓ verified'
    : verification === 'challenged' ? '⚠ challenged' : 'unverified';
  return b;
}

function ddpNote(box, text) {
  box.innerHTML = '';
  const p = document.createElement('p');
  p.className = 'muted-note';
  p.textContent = text;
  box.appendChild(p);
}

function ddpRenderReport(r) {
  const box = document.getElementById('dd-detail');
  const report = r.report || {};
  box.innerHTML = '';

  const meta = document.createElement('p');
  meta.className = 'muted-note';
  const when = r.completed_at || r.created_at;
  meta.textContent = (r.status === 'partial' ? 'Partial report · ' : '') +
    (when ? new Date(when).toLocaleString() : '');
  box.appendChild(meta);

  if (report.headline) {
    const h = document.createElement('h4'); h.textContent = report.headline;
    box.appendChild(h);
  }
  for (const para of String(report.overview || r.summary || '').split('\\n\\n')) {
    if (!para.trim()) continue;
    const p = document.createElement('p'); p.textContent = para.trim();
    box.appendChild(p);
  }
  for (const section of report.sections || []) {
    const h = document.createElement('h4');
    h.textContent = section.title || DDP_SPECIALISTS[section.specialist] || section.specialist;
    box.appendChild(h);
    for (const f of section.findings || []) {
      const div = document.createElement('div'); div.className = 'dd-finding';
      const claim = document.createElement('div');
      const strong = document.createElement('strong'); strong.textContent = f.claim || '';
      claim.appendChild(strong);
      claim.appendChild(ddpBadge(f.verification));
      div.appendChild(claim);
      const ev = document.createElement('div'); ev.className = 'ev';
      ev.textContent = (f.evidence || '') +
        (f.verification === 'challenged' && f.verification_note ? ' — verifier: ' + f.verification_note : '');
      div.appendChild(ev);
      box.appendChild(div);
    }
  }
  const lists = [['Risks', report.risks], ['Opportunities', report.opportunities]];
  for (const [title, items] of lists) {
    if (!items || !items.length) continue;
    const h = document.createElement('h4'); h.textContent = title;
    box.appendChild(h);
    const ul = document.createElement('ul');
    for (const item of items) {
      const li = document.createElement('li');
      li.textContent = item.text + (item.severity ? ' (' + item.severity + ')' : '');
      ul.appendChild(li);
    }
    box.appendChild(ul);
  }
  const foot = document.createElement('p'); foot.className = 'muted-note';
  const vs = report.verification_summary || {};
  let footText = '';
  if (vs.checked) footText += vs.checked + ' claims checked, ' + vs.verified + ' verified, ' + vs.challenged + ' challenged. ';
  if ((report.failed_specialists || []).length) {
    footText += 'No findings from: ' + report.failed_specialists.join(', ') + '. ';
  }
  foot.textContent = footText + (report.disclaimer || 'Informational only — not investment advice.');
  box.appendChild(foot);
}

async function ddpSelect(reportId) {
  for (const el of document.querySelectorAll('.dd-list-item')) {
    el.classList.toggle('active', el.dataset.reportId === reportId);
  }
  history.replaceState(null, '', '/app/deep-dives?report=' + encodeURIComponent(reportId));
  const box = document.getElementById('dd-detail');
  const cached = ddpReports.find((r) => r.report_id === reportId);
  if (cached && cached.status === 'running') {
    ddpNote(box, 'This deep dive is still running — watch it live on the dashboard.');
    return;
  }
  if (cached && cached.status === 'error') {
    ddpNote(box, 'This deep dive failed before producing a report.');
    return;
  }
  try {
    const r = await (await api('/deep-dive/' + reportId)).json();
    ddpRenderReport(r);
  } catch (e) {
    ddpNote(box, 'Could not load this report.');
  }
}

function ddpRenderList() {
  const list = document.getElementById('dd-list');
  list.innerHTML = '';
  for (const r of ddpReports) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'dd-list-item';
    btn.dataset.reportId = r.report_id;
    const when = document.createElement('span');
    when.className = 'when';
    const ts = r.completed_at || r.created_at;
    when.textContent = (ts ? new Date(ts).toLocaleDateString() : '?') +
      (r.status === 'partial' ? ' · partial' : r.status === 'running' ? ' · running'
        : r.status === 'error' ? ' · failed' : '');
    btn.appendChild(when);
    const head = document.createElement('span');
    head.className = 'head';
    head.textContent = ((r.report || {}).headline) || r.summary || '';
    btn.appendChild(head);
    btn.addEventListener('click', () => ddpSelect(r.report_id));
    list.appendChild(btn);
  }
  staggerIn(list.querySelectorAll('.dd-list-item'));
}

async function initDeepDivesPage() {
  const box = document.getElementById('dd-detail');
  try {
    const data = await (await api('/deep-dive?limit=25')).json();
    ddpReports = data.reports || [];
  } catch (e) {
    ddpNote(box, 'Could not load your reports.');
    return;
  }
  if (!ddpReports.length) {
    ddpNote(box, 'No deep dives yet. Run one from the dashboard — it takes a few minutes.');
    return;
  }
  ddpRenderList();
  const wanted = new URLSearchParams(window.location.search).get('report');
  const target = ddpReports.find((r) => r.report_id === wanted) || ddpReports[0];
  ddpSelect(target.report_id);
}

initDeepDivesPage();
"""


def deep_dives_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Deep Dives — Cirvia",
        _DEEP_DIVES_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_DEEP_DIVES_JS,
        wrap_class="app-wrap dash-wrap",
    )


def settings_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Settings — Cirvia",
        _SETTINGS_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_SETTINGS_JS,
        wrap_class="app-wrap settings-wrap",
    )


# --------------------------------------------------------------------------
# /app/settings/delivery — digest channel + schedule management
# --------------------------------------------------------------------------

_DELIVERY_SETTINGS_BODY = """
<div class="topbar">
  <h1 style="font-size:1.5rem;">Delivery</h1>
  <span class="who" id="who"></span>
</div>
<p class="muted-note" style="margin:-0.5rem 0 1rem;">
  <a href="/app/settings">&larr; Back to settings</a></p>

<div class="dash-card">
  <h3>Channel <button class="link-btn" id="delivery-change-btn"
    style="display:none;">Change</button></h3>
  <div id="delivery-summary"><div aria-hidden="true">
    <div class="skl"></div><div class="skl short"></div>
  </div></div>
  <div id="delivery-editor" style="display:none;">
""" + _DELIVERY_PICKER_HTML + """
  </div>
</div>

<div class="dash-card">
  <h3>Schedule <button class="link-btn" id="schedule-edit-btn">Edit</button></h3>
  <p id="schedule-row" style="display:none;"><span id="schedule-text"></span></p>
  <div id="schedule-editor" style="display:none;">
    <label for="dash-tz">Timezone</label>
    <select id="dash-tz"></select>
    <label for="dash-send-time">Send time</label>
    <input type="time" id="dash-send-time">
    <button class="btn" id="save-schedule-btn" style="margin-top:0.9rem;">Save schedule</button>
    <div class="error-box" id="schedule-error"></div>
  </div>
</div>
"""

_DELIVERY_SETTINGS_JS = """
requireSession();

let meProfile = null;
const CHANNEL_NAMES = { sms: 'Text message', email: 'Email', discord: 'Discord' };

function esc(s) {
  // Quotes must be escaped too: values land inside HTML attributes.
  const d = document.createElement('div'); d.textContent = s ?? '';
  return d.innerHTML.replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

async function loadDelivery() {
  const summary = document.getElementById('delivery-summary');
  const changeBtn = document.getElementById('delivery-change-btn');
  document.getElementById('delivery-editor').style.display = 'none';
  let active = null;
  try {
    const info = await (await api('/me/notifications')).json();
    active = (info.channels || []).find(
      (c) => c.channel === info.preferred_channel);
    if (active && active.verified && !active.opted_out) {
      summary.innerHTML =
        '<p style="margin-top:0.75rem;">' +
        '<strong>' + esc(CHANNEL_NAMES[active.channel] || active.channel) + '</strong>' +
        ' · ' + esc(active.destination_masked) +
        ' <span class="chip-ok">\\u2713 verified</span></p>' +
        '<p class="muted-note">Your digest and alerts are delivered here.</p>';
    } else if (active && active.opted_out) {
      summary.innerHTML =
        '<p class="muted-note"><span class="chip-warn">Delivery paused</span>. You ' +
        'unsubscribed from ' + esc(CHANNEL_NAMES[active.channel] || active.channel) +
        '. Set up a channel to resume delivery.</p>';
    } else {
      summary.innerHTML =
        '<p class="muted-note"><span class="chip-warn">Not set up</span>. Your digest ' +
        'only appears in the app. Add a channel to get it by text, email, or Discord.</p>';
    }
    changeBtn.style.display = 'inline';
    changeBtn.textContent = active && active.verified ? 'Change' : 'Set up';
  } catch (e) {
    summary.innerHTML = '<p class="muted-note">Could not load delivery settings.</p>';
  }
  return active;
}

async function openEditor() {
  const editor = document.getElementById('delivery-editor');
  editor.style.display = 'block';
  riseIn(editor);
  await initDeliveryPicker(() => loadDelivery());
}

document.getElementById('delivery-change-btn').addEventListener('click', async () => {
  const editor = document.getElementById('delivery-editor');
  if (editor.style.display !== 'none') { editor.style.display = 'none'; return; }
  await openEditor();
});

function renderSchedule() {
  if (!meProfile) return;
  document.getElementById('schedule-text').textContent =
    'Digest at ' + (meProfile.digest_send_time || '09:00') +
    ' · ' + (meProfile.timezone || 'America/Toronto');
  document.getElementById('schedule-row').style.display = 'block';
}

document.getElementById('schedule-edit-btn').addEventListener('click', () => {
  const editor = document.getElementById('schedule-editor');
  if (editor.style.display !== 'none') { editor.style.display = 'none'; return; }
  fillTzSelect(document.getElementById('dash-tz'), meProfile && meProfile.timezone);
  document.getElementById('dash-send-time').value =
    (meProfile && meProfile.digest_send_time) || '09:00';
  editor.style.display = 'block';
  riseIn(editor);
});

document.getElementById('save-schedule-btn').addEventListener('click', async () => {
  const btn = document.getElementById('save-schedule-btn');
  const errBox = document.getElementById('schedule-error');
  errBox.style.display = 'none';
  btn.disabled = true;
  try {
    const resp = await api('/me', {
      method: 'PATCH',
      body: JSON.stringify({
        timezone: document.getElementById('dash-tz').value,
        digest_send_time: document.getElementById('dash-send-time').value,
      }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Could not save schedule');
    }
    meProfile = await resp.json();
    document.getElementById('schedule-editor').style.display = 'none';
    renderSchedule();
  } catch (e) {
    errBox.textContent = e.message;
    errBox.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
});

async function init() {
  // Back from the Discord OAuth connect flow: connected needs no action
  // (the summary below shows the verified channel); on failure reopen the
  // picker with an explanation. Strip the param so refresh doesn't repeat it.
  const discordStatus = new URLSearchParams(window.location.search).get('discord');
  if (discordStatus) history.replaceState(null, '', window.location.pathname);
  try {
    meProfile = await (await api('/me')).json();
    document.getElementById('who').textContent =
      (meProfile.email || '') + ' \\u00b7 ' + (meProfile.plan === 'pro' ? 'Pro' : 'Free');
  } catch (e) { /* who line is cosmetic */ }
  renderSchedule();
  const active = await loadDelivery();
  if (discordStatus && discordStatus !== 'connected') {
    await openEditor();
    dpError(discordStatus === 'cancelled'
      ? 'Discord connection was cancelled. Try again, or paste a webhook URL instead.'
      : 'Discord connection failed. Try again, or paste a webhook URL instead.');
    return;
  }
  // Arriving without a working channel (e.g. from the dashboard nudge):
  // open the picker right away instead of making the user click Set up.
  if (!(active && active.verified && !active.opted_out)) await openEditor();
}
init();
"""


def delivery_settings_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Delivery — Cirvia",
        _DELIVERY_SETTINGS_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_DELIVERY_JS + _DELIVERY_SETTINGS_JS,
        wrap_class="app-wrap settings-wrap",
    )


NOT_CONFIGURED_HTML = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Cirvia</title>
{ICON_LINKS}{_FONT_LINKS}<style>{_CSS}</style></head><body>
<main class="wrap" style="text-align:center;padding-top:5rem;">
<h1>App not available yet</h1>
<p class="lead" style="margin:1rem auto;">Sign-in isn't configured on this deployment.
Contact <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> for early access.</p>
</main></body></html>"""
