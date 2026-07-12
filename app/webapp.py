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
  background: oklch(13% 0.014 300 / 0.9); backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px); border-bottom: 1px solid var(--line);
}
.app-wrap { max-width: 880px; margin: 0 auto; padding: 2.25rem 1.5rem 4rem; }
.app-wrap h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.015em;
  line-height: 1.25; max-width: none; margin: 0; }
.app-wrap h2 { font-size: 1.25rem; font-weight: 650; letter-spacing: -0.01em; }
.app-wrap h3 { font-size: 1rem; font-weight: 600; margin-bottom: 0; }
/* auth: full-viewport split, brand panel left, form right */
.auth-split { display: grid; grid-template-columns: minmax(400px, 44%) 1fr;
  min-height: 100dvh; }
.auth-brand { display: flex; flex-direction: column; justify-content: space-between;
  gap: 2.5rem; margin: 1rem 0 1rem 1rem; padding: 2.25rem 2.25rem 2rem;
  border: 1px solid var(--line); border-radius: var(--r-l); overflow: hidden;
  background:
    radial-gradient(120% 85% at 50% -25%, oklch(45% 0.16 295 / 0.6), transparent 72%),
    radial-gradient(70% 55% at 8% 30%, oklch(36% 0.12 265 / 0.35), transparent 70%),
    var(--surface-1); }
.auth-brand h2 { font-size: 1.7rem; font-weight: 750; letter-spacing: -0.02em;
  line-height: 1.25; color: var(--ink); max-width: 22ch; text-wrap: balance; }
.auth-brand .brand-sub { color: var(--ink-2); font-size: 0.95rem; margin-top: 0.6rem;
  max-width: 40ch; }
.auth-steps { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 1.75rem;
  max-width: 320px; }
.auth-step { display: flex; align-items: center; gap: 0.7rem; padding: 0.72rem 0.95rem;
  border-radius: var(--r-m); font-size: 0.9rem; font-weight: 600;
  background: oklch(15% 0.015 300 / 0.55); color: var(--ink-3); }
.auth-step .n { width: 22px; height: 22px; border-radius: 50%; flex: none;
  display: grid; place-items: center; font-size: 0.72rem; font-weight: 700;
  background: oklch(28% 0.02 300); color: var(--ink-2); }
.auth-step.active { background: var(--ink); color: oklch(15% 0.015 300); }
.auth-step.active .n { background: oklch(24% 0.02 300); color: #fff; }
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
  .auth-split { grid-template-columns: 1fr; }
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
.error-box { background: oklch(72% 0.14 25 / 0.1); border: 1px solid oklch(72% 0.14 25 / 0.4);
  color: var(--loss); border-radius: var(--r-s); padding: 0.7rem 0.9rem; font-size: 0.9rem;
  margin-top: 1rem; display: none; }
.notice-box { background: oklch(48% 0.18 295 / 0.12); border: 1px solid var(--accent);
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
@media (prefers-reduced-motion: reduce) { .skl { animation: none; opacity: 0.7; } }
/* dashboard: wide two-column shell, main work column + sticky utility rail */
.dash-wrap { max-width: 1400px; padding-top: 1.5rem; }
.dash-wrap .topbar { margin-bottom: 1.1rem; }
.dash-layout { display: grid; grid-template-columns: minmax(0, 1fr) 380px;
  gap: 1rem; align-items: start; }
.dash-main { display: flex; flex-direction: column; gap: 1rem; min-width: 0; }
.dash-rail { position: sticky; top: 4.4rem;
  display: flex; flex-direction: column; gap: 1rem; }
@media (max-width: 1080px) {
  .dash-layout { grid-template-columns: 1fr; }
  .dash-rail { position: static; }
}
.dash-card { background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-l); padding: 1.15rem 1.3rem 1.25rem; }
.dash-rail .chat-log { max-height: min(48vh, 440px); }
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
.pos { color: var(--gain); } .neg { color: var(--loss); }
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
.chat-msg.bot { background: oklch(30% 0.1 295 / 0.35); margin-right: 2rem; }
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
  background: oklch(30% 0.1 295 / 0.35); }
.consent-row { display: flex; gap: 0.6rem; align-items: flex-start; margin-top: 1rem;
  font-size: 0.82rem; color: var(--ink-3); font-weight: 500; cursor: pointer; }
.consent-row input { margin-top: 0.2rem; }
.chip-ok { color: var(--gain); font-size: 0.8rem; font-weight: 600; }
.chip-warn { color: var(--warn); font-size: 0.8rem; font-weight: 600; }
/* broken-connection banner (error-box vocabulary, --warn tinted) */
.warn-banner { display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 0.75rem 1rem; padding: 0.85rem 1.1rem;
  border: 1px solid oklch(80% 0.11 85 / 0.4); background: oklch(80% 0.11 85 / 0.1);
  border-radius: var(--r-m); font-size: 0.9rem; color: var(--ink-2); }
.warn-banner strong { color: var(--warn); font-weight: 650; }
.warn-banner .actions { display: flex; align-items: center; gap: 0.9rem; }
/* setup nudge variant: accent-tinted, for onboarding prompts, not errors */
.warn-banner.setup { border-color: oklch(48% 0.18 295 / 0.45);
  background: oklch(48% 0.18 295 / 0.12); }
.warn-banner.setup strong { color: var(--accent-text); }
/* holdings + news dashboard */
.holdings-row { cursor: pointer; transition: background 0.15s var(--ease); }
.holdings-row:hover { background: var(--surface-2); }
.holdings-row.selected { background: oklch(30% 0.1 295 / 0.35); }
.watchlist-badge { font-size: 0.68rem; font-weight: 650; color: var(--accent-text);
  border: 1px solid var(--accent); border-radius: 999px; padding: 0.1rem 0.45rem;
  margin-left: 0.4rem; vertical-align: middle; }
.filters-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1rem 0 0.75rem;
  align-items: center; }
.filters-row label { margin: 0; font-size: 0.78rem; }
.filters-row select { width: auto; min-width: 7rem; padding: 0.45rem 0.6rem;
  font-size: 0.85rem; }
.news-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 800px) { .news-grid { grid-template-columns: 1fr; } }
.news-feed { max-height: 420px; overflow-y: auto; margin-top: 0.75rem; }
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
  background: oklch(30% 0.1 295 / 0.35); color: var(--ink); }
.refresh-row { display: flex; align-items: center; gap: 0.75rem; }
.updated-at { color: var(--ink-3); font-size: 0.82rem; }
/* settings: single quiet column of cards */
.settings-wrap { max-width: 640px; }
.settings-wrap .dash-card { margin-top: 1rem; }
.plan-limits { margin: 0.75rem 0 0; padding-left: 1.15rem; color: var(--ink-2);
  font-size: 0.92rem; }
.plan-limits li { margin: 0.3rem 0; }
.danger-card { border-color: oklch(72% 0.14 25 / 0.45); }
.danger-card h3 { color: var(--loss); }
"""

_SHELL_JS = """
const SB_URL = window.CIRVIA_CONFIG.supabaseUrl;
const SB_KEY = window.CIRVIA_CONFIG.supabaseAnonKey;
const sb = window.supabase.createClient(SB_URL, SB_KEY);

async function getToken() {
  const { data } = await sb.auth.getSession();
  return data.session ? data.session.access_token : null;
}

async function api(path, opts = {}) {
  const token = await getToken();
  if (!token) { window.location.href = '/app'; throw new Error('not signed in'); }
  const resp = await fetch(path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + token,
      ...(opts.headers || {}),
    },
  });
  if (resp.status === 401) { window.location.href = '/app'; throw new Error('session expired'); }
  return resp;
}

async function requireSession() {
  const token = await getToken();
  if (!token) { window.location.href = '/app'; return false; }
  return true;
}

async function signOut() {
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
) -> str:
    config = json.dumps({"supabaseUrl": supabase_url, "supabaseAnonKey": anon_key})
    if chrome:
        shell = f"""<nav><div class="nav-inner">
<a class="logo" href="/">Cir<span>via</span></a>
<div class="nav-links"><a class="keep" href="/app/dashboard">Dashboard</a>
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
{ICON_LINKS}{_FONT_LINKS}<style>{_CSS}{_APP_CSS}</style>
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
      <h2>Know what matters to your portfolio before the market opens.</h2>
      <p class="brand-sub">Three steps and your first morning digest is on its way.</p>
      <div class="auth-steps">
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

document.getElementById('switch-btn').addEventListener('click', () => {
  mode = mode === 'signin' ? 'signup' : 'signin';
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
  errBox.style.display = 'none'; noticeBox.style.display = 'none';
});

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
  try {
    const resp = await api('/portfolio/status');
    const status = await resp.json();
    window.location.href = status.connected ? '/app/dashboard' : '/app/onboarding';
  } catch (e) {
    window.location.href = '/app/onboarding';
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
      const { data, error } = await sb.auth.signUp({ email, password });
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

// Already signed in? Skip the form.
getToken().then((t) => { if (t) routeAfterAuth(); });

riseIn(document.querySelector('.auth-form'), 0.28);
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
<h1>Set up Cirvia</h1>
<div class="ob-layout">
  <div class="ob-rail" aria-label="Setup progress">
    <div class="ob-step active" id="step-1">
      <span class="n">1</span><span class="t">Connect your brokerage</span>
      <span class="d">Link Wealthsimple through SnapTrade's secure portal.</span>
    </div>
    <div class="ob-step" id="step-2">
      <span class="n">2</span><span class="t">Sync your holdings</span>
      <span class="d">Cirvia pulls your positions, read-only.</span>
    </div>
    <div class="ob-step" id="step-3">
      <span class="n">3</span><span class="t">Choose holdings</span>
      <span class="d">Pick which positions get news on Free.</span>
    </div>
    <div class="ob-step" id="step-4">
      <span class="n">4</span><span class="t">Digest preferences</span>
      <span class="d">Pick when your morning brief arrives.</span>
    </div>
    <div class="ob-step" id="step-5">
      <span class="n">5</span><span class="t">Delivery</span>
      <span class="d">Get it by text, email, or Discord.</span>
    </div>
  </div>
  <div class="ob-content">

  <div class="step-panel" id="panel-connect">
    <h2>Connect your brokerage</h2>
    <p>Link Wealthsimple through SnapTrade's secure portal. Read-only: Cirvia can
    never trade or move money, and your brokerage password is never shared with us.</p>
    <div class="status-line" id="connect-status" style="display:none;">
      <span class="spinner"></span><span id="connect-status-text">Waiting for connection…</span>
    </div>
    <button class="btn full" id="connect-btn">Connect Wealthsimple</button>
    <button class="btn ghost full" id="connected-btn" style="display:none;">I've finished connecting</button>
    <div class="error-box" id="connect-error"></div>
    <p class="muted-note">A new tab will open. Come back here when you're done.</p>
  </div>

  <div class="step-panel" id="panel-sync" style="display:none;">
    <h2>Syncing your holdings</h2>
    <div class="status-line" id="sync-status-line"><span class="spinner"></span>
    <span id="sync-status-text">Pulling your positions…</span></div>
    <div class="error-box" id="sync-error"></div>
    <button class="btn full" id="sync-retry-btn" style="display:none;">Try again</button>
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
    <input type="time" id="send-time" value="07:45">
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

const PANELS = ['panel-connect','panel-sync','panel-watchlist','panel-prefs','panel-delivery'];
const STEP_IDS = ['step-1','step-2','step-3','step-4','step-5'];

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
  for (let n = 1; n <= 5; n++) {
    const step = document.getElementById('step-' + n);
    step.classList.toggle('active', n === current);
    step.classList.toggle('done', n < current);
    const marker = step.querySelector('.n');
    marker.textContent = n < current ? '\\u2713' : String(n);
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
    setTimeout(afterSync, 900);
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
    initDeliveryPicker(() => { window.location.href = '/app/dashboard'; });
  } catch (e) {
    showError('prefs-error', e.message);
  } finally {
    btn.disabled = false;
  }
});

// Back from the Discord OAuth connect flow (delivery is the last step):
// success means the channel is already verified server-side, so onboarding
// is done; failure reopens the delivery picker to try again.
const dcStatus = new URLSearchParams(window.location.search).get('discord');
if (dcStatus === 'connected') {
  window.location.replace('/app/dashboard');
} else if (dcStatus) {
  showPanel('panel-delivery');
  initDeliveryPicker(() => { window.location.href = '/app/dashboard'; })
    .then(() => dpError(dcStatus === 'cancelled'
      ? 'Discord connection was cancelled. Try again, or paste a webhook URL instead.'
      : 'Discord connection failed. Try again, or paste a webhook URL instead.'));
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
<div class="dash-layout">
<div class="dash-main">
  <div class="warn-banner setup" id="delivery-banner" style="display:none;">
    <span><strong>Get your digest delivered.</strong> Add text, email, or Discord
    and your morning brief reaches you before the market opens.</span>
    <span class="actions">
      <a class="btn" href="/app/settings/delivery">Set up delivery</a>
      <button class="link-btn" id="delivery-banner-dismiss">Dismiss</button>
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
  <div class="dash-card">
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
        </select>
      </label>
    </div>
    <div class="news-grid">
      <div class="dash-card" style="padding:0;border:none;background:transparent;">
        <h3>General news</h3>
        <div class="news-feed" id="general-news"><div aria-hidden="true">
          <div class="skl"></div><div class="skl short"></div>
        </div></div>
      </div>
      <div class="dash-card" style="padding:0;border:none;background:transparent;">
        <h3>Holding news <span class="tag" id="holding-news-label">Select a holding</span></h3>
        <div class="news-feed" id="holding-news">
          <p class="muted-note">Click a row in your holdings table to see news Cirvia has surfaced for that ticker.</p>
        </div>
      </div>
    </div>
  </div>

  <div class="dash-card">
    <h3>Holdings
      <span class="refresh-row">
        <span class="updated-at" id="holdings-updated"></span>
        <button class="link-btn" id="refresh-holdings-btn">Refresh</button>
        <span class="tag" id="totals"></span>
      </span>
    </h3>
    <div id="holdings"><div aria-hidden="true">
      <div class="skl"></div><div class="skl"></div><div class="skl short"></div>
    </div></div>
  </div>
</div>

<aside class="dash-rail">
  <div class="dash-card">
    <h3>Ask Cirvia</h3>
    <div class="chat-log" id="chat-log"></div>
    <div class="chat-row">
      <input id="chat-input" placeholder="Any news on my holdings today?" maxlength="500">
      <button class="btn" id="chat-btn">Send</button>
    </div>
    <p class="muted-note">Informational only. Cirvia never gives buy or sell advice.</p>
  </div>

  <div class="dash-card" id="watchlist-card" style="display:none;">
    <h3>Digest watchlist <span class="tag" id="watchlist-limit-tag"></span></h3>
    <p class="muted-note" style="margin-top:0.5rem;">Free plan: choose which holdings get news in your digest.</p>
    <div class="watchlist-grid" id="dash-watchlist-grid"></div>
    <button class="btn" id="save-watchlist-btn" style="margin-top:0.75rem;">Save watchlist</button>
    <div class="error-box" id="watchlist-save-error"></div>
  </div>

</aside>
</div>
"""

_DASHBOARD_JS = """
requireSession();

let meProfile = null;
let selectedTicker = null;
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

function filterSince() {
  const p = document.getElementById('filter-period').value;
  if (p === 'all') return null;
  const d = new Date();
  d.setDate(d.getDate() - parseInt(p, 10));
  return d.toISOString().slice(0, 10);
}

function newsQuery(extra) {
  const params = new URLSearchParams();
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

function renderNewsItems(el, items, emptyMsg) {
  if (!items || items.length === 0) {
    el.innerHTML = '<p class="muted-note">' + esc(emptyMsg) + '</p>';
    return;
  }
  el.innerHTML = items.map((item) => {
    const meta = [];
    if (item.kind) meta.push(item.kind);
    if (item.severity) meta.push(item.severity);
    if (item.category) meta.push(item.category);
    if (item.source) meta.push(item.source);
    if (item.created_at) meta.push(new Date(item.created_at).toLocaleDateString());
    // News URLs come from external providers; only ever link http(s).
    const low = (item.url ?? '').toLowerCase();
    const urlOk = low.startsWith('http://') || low.startsWith('https://');
    const link = urlOk
      ? ' <a href="' + esc(item.url) + '" target="_blank" rel="noopener">Read</a>' : '';
    return '<div class="news-item">' +
      '<div class="head">' + esc(item.headline) + link + '</div>' +
      (item.body ? '<div class="body">' + esc(item.body) + '</div>' : '') +
      '<div class="meta">' + esc(meta.join(' · ')) + '</div></div>';
  }).join('');
  staggerIn(el.querySelectorAll('.news-item'));
}

async function loadGeneralNews() {
  const el = document.getElementById('general-news');
  try {
    const qs = newsQuery({ kind: 'digest,alert' });
    const data = await (await api('/news?' + qs)).json();
    renderNewsItems(el, data.items,
      'No general news yet. Digests and macro alerts appear here once Cirvia sends them.');
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load general news.</p>';
  }
}

async function loadHoldingNews() {
  const el = document.getElementById('holding-news');
  const label = document.getElementById('holding-news-label');
  if (!selectedTicker) {
    label.textContent = 'Select a holding';
    el.innerHTML = '<p class="muted-note">Click a row in your holdings table to see news ' +
      'Cirvia has surfaced for that ticker.</p>';
    return;
  }
  label.textContent = selectedTicker;
  try {
    const qs = newsQuery({ ticker: selectedTicker, kind: 'holding,alert' });
    const data = await (await api('/news?' + qs)).json();
    renderNewsItems(el, data.items,
      'No news stored for ' + selectedTicker + ' yet. Your next digest may surface articles here.');
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load holding news.</p>';
  }
}

function reloadNewsFeeds() {
  loadGeneralNews();
  loadHoldingNews();
}

async function loadMe() {
  try {
    meProfile = await (await api('/me')).json();
    document.getElementById('who').textContent =
      (meProfile.email || '') + ' · ' + (meProfile.plan === 'pro' ? 'Pro' : 'Free');
    if (meProfile.digest_tickers_editable) {
      document.getElementById('watchlist-card').style.display = 'block';
      document.getElementById('watchlist-limit-tag').textContent =
        'up to ' + (meProfile.digest_tickers_limit || 3);
    }
  } catch (e) {}
}

async function loadHoldings() {
  const el = document.getElementById('holdings');
  try {
    const pf = await (await api('/portfolio')).json();
    document.getElementById('holdings-updated').textContent =
      'Updated ' + new Date().toLocaleTimeString();
    if (!pf.positions || pf.positions.length === 0) {
      el.innerHTML = '<p class="muted-note">No holdings yet. ' +
        '<a href="/app/onboarding">Connect your brokerage</a> to sync your portfolio.</p>';
      return;
    }
    portfolioTickers = [...new Set(pf.positions.map((p) => p.ticker))];
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
    let rows = '';
    for (const p of pf.positions) {
      const sel = p.ticker === selectedTicker ? ' selected' : '';
      const badge = watchlist.has(p.ticker) ? '<span class="watchlist-badge">watchlist</span>' : '';
      rows += `<tr class="holdings-row${sel}" data-ticker="${esc(p.ticker)}">` +
        `<td><strong>${esc(p.ticker)}</strong>${badge}</td>` +
        `<td>${p.quantity}</td><td>${fmtMoney(p.market_value)}</td>` +
        pctCell(p.day_change_pct) + pctCell(p.unrealized_pnl_pct) + '</tr>';
    }
    el.innerHTML = '<table><thead><tr><th>Ticker</th><th>Qty</th><th>Value</th>' +
      '<th>Day</th><th>Total</th></tr></thead><tbody>' + rows + '</tbody></table>';
    el.querySelectorAll('.holdings-row').forEach((row) => {
      row.addEventListener('click', () => {
        selectedTicker = row.dataset.ticker;
        el.querySelectorAll('.holdings-row').forEach((r) =>
          r.classList.toggle('selected', r.dataset.ticker === selectedTicker));
        loadHoldingNews();
      });
    });
    if (!selectedTicker && portfolioTickers.length) {
      selectedTicker = portfolioTickers[0];
      const first = el.querySelector('.holdings-row');
      if (first) first.classList.add('selected');
      loadHoldingNews();
    }
    staggerIn(el.querySelectorAll('tbody tr'));
    buildDashWatchlist();
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load holdings.</p>';
  }
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
    const resp = await api('/chat', { method: 'POST', body: JSON.stringify({ message }) });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      pending.textContent = data.detail || 'Something went wrong.';
    } else {
      pending.textContent = data.answer || '(no answer)';
    }
  } catch (e) {
    pending.textContent = 'Network error. Try again.';
  } finally {
    sendBtn.disabled = false; input.focus();
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

loadChatHistory();

// --- delivery-setup nudge ----------------------------------------------------
// Shown when no verified, non-opted-out channel is active: the digest only
// lands on this dashboard until the user adds text/email/Discord delivery.
// Managed on /app/settings/delivery; this banner just points there.
const DELIVERY_BANNER_KEY = 'cirvia-delivery-banner-dismissed';

async function checkDeliverySetup() {
  if (sessionStorage.getItem(DELIVERY_BANNER_KEY)) return;
  // One nudge at a time: a broken connection is the more urgent problem.
  const connBanner = document.getElementById('connection-banner');
  if (connBanner && connBanner.style.display !== 'none') return;
  try {
    const info = await (await api('/me/notifications')).json();
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

async function checkConnection() {
  if (sessionStorage.getItem(BANNER_DISMISS_KEY)) return;
  try {
    const s = await (await api('/portfolio/status')).json();
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

loadMe().then(() => {
  loadHoldings();
  reloadNewsFeeds();
  checkConnection().then(checkDeliverySetup);
});
"""


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
  <h3>Plan <span class="tag" id="plan-chip"></span></h3>
  <ul class="plan-limits" id="plan-limits"></ul>
  <p class="muted-note" id="plan-note" style="display:none;">Pro billing is coming
  soon. Until then every account stays on the Free plan.</p>
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
    const plan = me.plan === 'pro' ? 'Pro' : 'Free';
    document.getElementById('who').textContent = (me.email || '') + ' \\u00b7 ' + plan;
    document.getElementById('account-email').textContent = me.email || 'unknown';
    document.getElementById('plan-chip').textContent = plan;
    const limits = document.getElementById('plan-limits');
    const items = me.plan === 'pro'
      ? ['Daily weekday digest across all your holdings',
         'Macro alerts when the world moves',
         'Unlimited chat questions',
         'Unlimited connected accounts']
      : ['Weekly digest (Mondays) on up to ' + (me.digest_tickers_limit || 3) +
           ' holdings',
         '5 chat questions per day',
         '1 connected account'];
    limits.innerHTML = items.map((t) => '<li>' + esc(t) + '</li>').join('');
    if (me.plan !== 'pro') {
      document.getElementById('plan-note').style.display = 'block';
    }
  } catch (e) { /* nav still works; cards degrade individually */ }
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
        'Wealthsimple, linked read-only through SnapTrade. ' + esc(synced) + '</p>';
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

loadAccount();
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
    'Digest at ' + (meProfile.digest_send_time || '07:45') +
    ' · ' + (meProfile.timezone || 'America/Toronto');
  document.getElementById('schedule-row').style.display = 'block';
}

document.getElementById('schedule-edit-btn').addEventListener('click', () => {
  const editor = document.getElementById('schedule-editor');
  if (editor.style.display !== 'none') { editor.style.display = 'none'; return; }
  fillTzSelect(document.getElementById('dash-tz'), meProfile && meProfile.timezone);
  document.getElementById('dash-send-time').value =
    (meProfile && meProfile.digest_send_time) || '07:45';
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
