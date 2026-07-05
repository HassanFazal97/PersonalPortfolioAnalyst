"""Public marketing landing page for Cirvia (``GET /``)."""

from __future__ import annotations

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cirvia — AI portfolio analyst for Canadian investors</title>
  <meta name="description" content="Connect Wealthsimple, get a daily digest, macro alerts, and on-demand answers about your real holdings. Read-only. No trade execution.">
  <style>
    :root {
      --bg: #0b0f14;
      --surface: #141b24;
      --text: #e8eef5;
      --muted: #8fa3b8;
      --accent: #5b9fd4;
      --accent-dim: #3d6f96;
      --line: #243040;
      --radius: 12px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      min-height: 100vh;
    }
    .wrap { max-width: 720px; margin: 0 auto; padding: 3rem 1.5rem 4rem; }
    header { margin-bottom: 2.5rem; }
    .logo {
      font-size: 1.75rem;
      font-weight: 700;
      letter-spacing: -0.03em;
      color: var(--text);
    }
    .logo span { color: var(--accent); }
    h1 {
      font-size: clamp(1.75rem, 5vw, 2.25rem);
      font-weight: 650;
      letter-spacing: -0.03em;
      line-height: 1.2;
      margin: 1.25rem 0 1rem;
    }
    .lead { font-size: 1.125rem; color: var(--muted); max-width: 36em; }
    .card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 1.5rem 1.75rem;
      margin: 2rem 0;
    }
    .card h2 {
      font-size: 0.8125rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
      margin-bottom: 1rem;
    }
    ul { list-style: none; }
    li {
      padding: 0.5rem 0 0.5rem 1.25rem;
      position: relative;
      color: var(--text);
    }
    li::before {
      content: "";
      position: absolute;
      left: 0;
      top: 0.85rem;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--accent);
    }
    .disclaimer {
      font-size: 0.875rem;
      color: var(--muted);
      border-top: 1px solid var(--line);
      padding-top: 1.5rem;
      margin-top: 2rem;
    }
    footer {
      margin-top: 2.5rem;
      font-size: 0.875rem;
      color: var(--muted);
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .badge {
      display: inline-block;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.25rem 0.625rem;
      border-radius: 999px;
      background: rgba(91, 159, 212, 0.15);
      color: var(--accent);
      margin-top: 0.75rem;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="logo">Cir<span>via</span></div>
      <span class="badge">Early access</span>
    </header>

    <h1>Your portfolio, explained — before you open your brokerage app.</h1>
    <p class="lead">
      Cirvia is an AI analyst that knows your real holdings. Connect Wealthsimple
      with read-only access, get a weekday morning digest, macro alerts when the
      world moves, and ask anything about your book on demand.
    </p>

    <div class="card">
      <h2>What you get</h2>
      <ul>
        <li>Automatic sync across TFSA, RRSP, and taxable accounts</li>
        <li>Weekday morning digest tailored to your tickers</li>
        <li>Macro alerts — Fed, energy, geopolitics, regulation — mapped to your holdings</li>
        <li>On-demand chat: news, performance, and context for your actual positions</li>
      </ul>
    </div>

    <div class="card">
      <h2>How it works</h2>
      <ul>
        <li>Link Wealthsimple through SnapTrade&apos;s secure Connection Portal</li>
        <li>We never store your brokerage password and never execute trades</li>
        <li>Read-only access — Cirvia informs; it does not advise buy or sell</li>
      </ul>
    </div>

    <p class="disclaimer">
      <strong>Not financial advice.</strong> Cirvia is for informational purposes only.
      Past performance does not guarantee future results. Investing involves risk,
      including loss of principal.
    </p>

    <footer>
      <p>Built in Canada · <a href="mailto:hello@cirvia.ca">hello@cirvia.ca</a></p>
    </footer>
  </div>
</body>
</html>
"""
