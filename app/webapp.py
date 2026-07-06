"""The signed-in web app: /app (sign in), /app/onboarding, /app/dashboard.

Server-rendered HTML shells (auth-exempt) with client-side supabase-js auth.
The browser signs in with the publishable key, then calls the existing API
with the Supabase JWT — the API remains the security boundary. Config
(SUPABASE_URL + anon key) is injected server-side at render time.
"""

from __future__ import annotations

import json

from app.landing import _CSS, _FONT_LINKS, CONTACT_EMAIL, MOTION_CDN

_APP_CSS = """
/* app register: fixed rem type scale, quieter headings, denser rhythm */
.app-wrap { max-width: 880px; margin: 0 auto; padding: 2.25rem 1.5rem 4rem; }
.app-wrap h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.015em;
  line-height: 1.25; max-width: none; margin: 0; }
.app-wrap h2 { font-size: 1.25rem; font-weight: 650; letter-spacing: -0.01em; }
.app-wrap h3 { font-size: 1rem; font-weight: 600; margin-bottom: 0; }
.auth-card { max-width: 400px; margin: 3.5rem auto; background: var(--surface-1);
  border: 1px solid var(--line); border-radius: var(--r-l); padding: 2rem; }
.auth-card h1 { margin-bottom: 0.35rem; }
.auth-card .sub { color: var(--ink-3); font-size: 0.95rem; margin-bottom: 1.4rem; }
label { display: block; font-size: 0.84rem; font-weight: 600; color: var(--ink-3);
  margin: 0.9rem 0 0.3rem; }
input[type=email], input[type=password], input[type=time], select {
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
/* onboarding stepper */
.stepper { display: flex; gap: 0.5rem; margin: 1.5rem 0 2rem; }
.stepper .s { flex: 1; height: 4px; border-radius: 4px; background: var(--surface-2);
  transition: background 0.25s var(--ease); }
.stepper .s.done { background: var(--accent-hover); }
.step-panel { background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-l); padding: 1.75rem; }
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
/* dashboard */
.dash-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 700px) { .dash-grid { grid-template-columns: 1fr; } }
.dash-card { background: var(--surface-1); border: 1px solid var(--line);
  border-radius: var(--r-l); padding: 1.4rem 1.5rem; }
.dash-card.wide { grid-column: 1 / -1; }
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
    title: str, body: str, *, supabase_url: str, anon_key: str, extra_js: str
) -> str:
    config = json.dumps({"supabaseUrl": supabase_url, "supabaseAnonKey": anon_key})
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="robots" content="noindex">
{_FONT_LINKS}<style>{_CSS}{_APP_CSS}</style>
</head>
<body>
<nav><div class="nav-inner">
<a class="logo" href="/">Cir<span>via</span></a>
<div class="nav-links"><a class="keep" href="/app/dashboard">Dashboard</a>
<button class="link-btn" onclick="signOut()">Sign out</button></div>
</div></nav>
<main class="app-wrap">
{body}
</main>
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
<div class="auth-card">
  <h1 id="auth-title">Sign in to Cirvia</h1>
  <p class="sub" id="auth-sub">Your AI portfolio analyst.</p>
  <form id="auth-form">
    <label for="email">Email</label>
    <input type="email" id="email" autocomplete="email" required>
    <label for="password">Password</label>
    <input type="password" id="password" autocomplete="current-password" minlength="8" required>
    <button class="btn full" id="auth-btn" type="submit">Sign in</button>
  </form>
  <div class="error-box" id="auth-error"></div>
  <div class="notice-box" id="auth-notice"></div>
  <p class="switch-mode">
    <span id="switch-label">New to Cirvia?</span>
    <button class="link-btn" id="switch-btn" type="button">Create an account</button>
  </p>
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
  document.getElementById('auth-title').textContent =
    mode === 'signin' ? 'Sign in to Cirvia' : 'Create your Cirvia account';
  document.getElementById('switch-label').textContent =
    mode === 'signin' ? 'New to Cirvia?' : 'Already have an account?';
  document.getElementById('switch-btn').textContent =
    mode === 'signin' ? 'Create an account' : 'Sign in';
  btn.textContent = mode === 'signin' ? 'Sign in' : 'Create account';
  errBox.style.display = 'none'; noticeBox.style.display = 'none';
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

riseIn(document.querySelector('.auth-card'), 0.28);
"""


# --------------------------------------------------------------------------
# /app/onboarding — connect brokerage -> sync -> preferences
# --------------------------------------------------------------------------

_ONBOARDING_BODY = """
<h1 style="font-size:1.6rem;">Set up Cirvia</h1>
<div class="stepper">
  <div class="s done" id="s1"></div><div class="s" id="s2"></div><div class="s" id="s3"></div>
</div>

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
  <div class="status-line"><span class="spinner"></span>
  <span id="sync-status-text">Pulling your positions…</span></div>
  <div class="error-box" id="sync-error"></div>
</div>

<div class="step-panel" id="panel-prefs" style="display:none;">
  <h2>Digest preferences</h2>
  <p>When should your morning digest arrive?</p>
  <label for="tz">Timezone</label>
  <select id="tz"></select>
  <label for="send-time">Send time</label>
  <input type="time" id="send-time" value="07:45">
  <button class="btn full" id="prefs-btn">Finish setup</button>
  <div class="error-box" id="prefs-error"></div>
</div>
"""

_ONBOARDING_JS = """
requireSession();

const TZS = ['America/Toronto','America/Vancouver','America/Edmonton','America/Winnipeg',
  'America/Halifax','America/St_Johns','America/New_York','America/Chicago',
  'America/Denver','America/Los_Angeles','Europe/London','Europe/Paris'];
const tzSel = document.getElementById('tz');
const guess = Intl.DateTimeFormat().resolvedOptions().timeZone;
const list = TZS.includes(guess) ? TZS : [guess, ...TZS];
for (const z of list) {
  const o = document.createElement('option');
  o.value = z; o.textContent = z; if (z === guess) o.selected = true;
  tzSel.appendChild(o);
}

function showPanel(id) {
  let changed = false;
  for (const p of ['panel-connect','panel-sync','panel-prefs']) {
    const el = document.getElementById(p);
    const show = p === id;
    if (show && el.style.display === 'none') changed = true;
    el.style.display = show ? 'block' : 'none';
  }
  if (changed) riseIn(document.getElementById(id));
  document.getElementById('s2').classList.toggle('done', id !== 'panel-connect');
  document.getElementById('s3').classList.toggle('done', id === 'panel-prefs');
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

async function runSync() {
  showPanel('panel-sync');
  try {
    const resp = await api('/portfolio/sync', { method: 'POST' });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Sync failed');
    }
    const result = await resp.json();
    document.getElementById('sync-status-text').textContent =
      'Synced ' + result.positions_upserted + ' positions across ' +
      result.accounts_synced + ' accounts.';
    setTimeout(() => showPanel('panel-prefs'), 900);
  } catch (e) {
    showError('sync-error', e.message);
  }
}

document.getElementById('connect-btn').addEventListener('click', async () => {
  const btn = document.getElementById('connect-btn');
  btn.disabled = true;
  document.getElementById('connect-error').style.display = 'none';
  try {
    await api('/portfolio/snaptrade/register', { method: 'POST' });
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
    window.location.href = '/app/dashboard';
  } catch (e) {
    showError('prefs-error', e.message);
    btn.disabled = false;
  }
});

// Returning mid-onboarding: if already connected, jump ahead to sync.
api('/portfolio/status').then(async (resp) => {
  const s = await resp.json();
  if (s.connected) await runSync();
}).catch(() => {});
"""


# --------------------------------------------------------------------------
# /app/dashboard
# --------------------------------------------------------------------------

_DASHBOARD_BODY = """
<div class="topbar">
  <h1 style="font-size:1.5rem;">Dashboard</h1>
  <span class="who" id="who"></span>
</div>
<div class="dash-grid">
  <div class="dash-card wide">
    <h3>Holdings <span class="tag" id="totals"></span></h3>
    <div id="holdings"><div aria-hidden="true">
      <div class="skl"></div><div class="skl"></div><div class="skl short"></div>
    </div></div>
  </div>
  <div class="dash-card">
    <h3>Today's digest</h3>
    <div id="digest"><div aria-hidden="true">
      <div class="skl"></div><div class="skl"></div><div class="skl short"></div>
    </div></div>
  </div>
  <div class="dash-card">
    <h3>Recent alerts</h3>
    <div id="alerts"><div aria-hidden="true">
      <div class="skl"></div><div class="skl short"></div>
    </div></div>
  </div>
  <div class="dash-card wide">
    <h3>Ask Cirvia</h3>
    <div class="chat-log" id="chat-log"></div>
    <div class="chat-row">
      <input id="chat-input" placeholder="Any news on my holdings today?" maxlength="500">
      <button class="btn" id="chat-btn">Send</button>
    </div>
    <p class="muted-note">Informational only. Cirvia never gives buy or sell advice.</p>
  </div>
</div>
"""

_DASHBOARD_JS = """
requireSession();

function esc(s) {
  const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML;
}
function fmtMoney(v) {
  return v == null ? '—' : v.toLocaleString('en-CA', { style: 'currency', currency: 'CAD' });
}
function pctCell(v) {
  if (v == null) return '<td>—</td>';
  const cls = v >= 0 ? 'pos' : 'neg';
  return `<td class="${cls}">${v >= 0 ? '+' : ''}${v.toFixed(2)}%</td>`;
}

async function loadMe() {
  try {
    const me = await (await api('/me')).json();
    document.getElementById('who').textContent =
      (me.email || '') + ' · ' + (me.plan === 'pro' ? 'Pro' : 'Free');
  } catch (e) {}
}

async function loadHoldings() {
  const el = document.getElementById('holdings');
  try {
    const pf = await (await api('/portfolio')).json();
    if (!pf.positions || pf.positions.length === 0) {
      el.innerHTML = '<p class="muted-note">No holdings yet. ' +
        '<a href="/app/onboarding">Connect your brokerage</a> to sync your portfolio.</p>';
      return;
    }
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
      rows += `<tr><td><strong>${esc(p.ticker)}</strong></td>` +
        `<td>${p.quantity}</td><td>${fmtMoney(p.market_value)}</td>` +
        pctCell(p.day_change_pct) + pctCell(p.unrealized_pnl_pct) + '</tr>';
    }
    el.innerHTML = '<table><thead><tr><th>Ticker</th><th>Qty</th><th>Value</th>' +
      '<th>Day</th><th>Total</th></tr></thead><tbody>' + rows + '</tbody></table>';
    staggerIn(el.querySelectorAll('tbody tr'));
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load holdings.</p>';
  }
}

async function loadDigest() {
  const el = document.getElementById('digest');
  try {
    const resp = await api('/digest/latest');
    if (resp.status === 404) {
      el.innerHTML = '<p class="muted-note">No digest yet today. Your next one arrives on your schedule.</p>';
      return;
    }
    const d = await resp.json();
    el.innerHTML = '<div class="digest-body">' + esc(d.body) + '</div>';
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load digest.</p>';
  }
}

async function loadAlerts() {
  const el = document.getElementById('alerts');
  try {
    const data = await (await api('/alerts?limit=5')).json();
    if (!data.alerts || data.alerts.length === 0) {
      el.innerHTML = '<p class="muted-note">No alerts yet. Macro alerts appear when world events touch your holdings.</p>';
      return;
    }
    el.innerHTML = data.alerts.map((a) =>
      `<div class="alert-item"><div class="head">${esc(a.headline)}</div>` +
      `<div class="meta"><span class="sev-${esc(a.severity)}">${esc(a.severity)}</span>` +
      ` · ${esc(a.category)}${a.tickers && a.tickers.length ? ' · ' + a.tickers.map(esc).join(', ') : ''}</div></div>`
    ).join('');
    staggerIn(el.querySelectorAll('.alert-item'));
  } catch (e) {
    el.innerHTML = '<p class="muted-note">Could not load alerts.</p>';
  }
}

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

loadMe(); loadHoldings(); loadDigest(); loadAlerts();
"""


def login_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Sign in — Cirvia",
        _LOGIN_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_LOGIN_JS,
    )


def onboarding_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Get set up — Cirvia",
        _ONBOARDING_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_ONBOARDING_JS,
    )


def dashboard_page(supabase_url: str, anon_key: str) -> str:
    return _page(
        "Dashboard — Cirvia",
        _DASHBOARD_BODY,
        supabase_url=supabase_url,
        anon_key=anon_key,
        extra_js=_DASHBOARD_JS,
    )


NOT_CONFIGURED_HTML = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Cirvia</title>
{_FONT_LINKS}<style>{_CSS}</style></head><body>
<main class="wrap" style="text-align:center;padding-top:5rem;">
<h1>App not available yet</h1>
<p class="lead" style="margin:1rem auto;">Sign-in isn't configured on this deployment.
Contact <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> for early access.</p>
</main></body></html>"""
