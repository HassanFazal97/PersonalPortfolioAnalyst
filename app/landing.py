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
  --bg: #0b0f14; --surface: #141b24; --surface-2: #1a232f;
  --text: #e8eef5; --muted: #8fa3b8; --accent: #5b9fd4; --accent-dim: #3d6f96;
  --line: #243040; --radius: 14px; --maxw: 760px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  background: radial-gradient(1200px 600px at 50% -200px, #12202e 0%, var(--bg) 60%) no-repeat, var(--bg);
  color: var(--text); line-height: 1.65; min-height: 100vh; -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap { max-width: var(--maxw); margin: 0 auto; padding: 2.5rem 1.5rem 4rem; }
/* nav */
nav {
  position: sticky; top: 0; z-index: 10;
  backdrop-filter: blur(10px); background: rgba(11, 15, 20, 0.72);
  border-bottom: 1px solid var(--line);
}
.nav-inner {
  max-width: 960px; margin: 0 auto; padding: 0.9rem 1.5rem;
  display: flex; align-items: center; justify-content: space-between; gap: 1rem;
}
.logo { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.03em; color: var(--text); }
.logo span { color: var(--accent); }
.nav-links { display: flex; align-items: center; gap: 1.25rem; font-size: 0.925rem; }
.nav-links a { color: var(--muted); }
.nav-links a:hover, .nav-links a.active { color: var(--text); text-decoration: none; }
.btn {
  display: inline-block; font-weight: 600; font-size: 0.9rem;
  padding: 0.6rem 1.1rem; border-radius: 999px; border: 1px solid transparent;
  background: var(--accent); color: #08131d; transition: background 0.15s;
}
.btn:hover { background: #78b2e0; text-decoration: none; }
.btn.ghost { background: transparent; border-color: var(--line); color: var(--text); }
.btn.ghost:hover { border-color: var(--accent-dim); background: var(--surface); }
/* hero */
.hero { padding: 3rem 0 1rem; }
.badge {
  display: inline-block; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em;
  text-transform: uppercase; padding: 0.3rem 0.7rem; border-radius: 999px;
  background: rgba(91, 159, 212, 0.14); color: var(--accent); margin-bottom: 1.25rem;
}
h1 { font-size: clamp(2rem, 6vw, 2.75rem); font-weight: 680; letter-spacing: -0.035em; line-height: 1.12; }
.lead { font-size: 1.15rem; color: var(--muted); max-width: 34em; margin-top: 1.1rem; }
.cta-row { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 1.75rem; }
/* sections */
section { margin: 3.25rem 0; }
.eyebrow { font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); margin-bottom: 0.6rem; }
h2 { font-size: 1.5rem; font-weight: 660; letter-spacing: -0.02em; }
h3 { font-size: 1.05rem; font-weight: 640; margin-bottom: 0.35rem; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1.5rem; }
@media (max-width: 560px) { .grid { grid-template-columns: 1fr; } }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 1.4rem 1.5rem; }
.card p { color: var(--muted); font-size: 0.95rem; }
.steps { counter-reset: step; margin-top: 1.5rem; }
.step { display: flex; gap: 1rem; padding: 1rem 0; border-bottom: 1px solid var(--line); }
.step:last-child { border-bottom: none; }
.step .num {
  counter-increment: step; flex: 0 0 auto; width: 2rem; height: 2rem; border-radius: 999px;
  background: var(--surface-2); border: 1px solid var(--line); color: var(--accent);
  display: grid; place-items: center; font-weight: 700; font-size: 0.9rem;
}
.step .num::before { content: counter(step); }
.step p { color: var(--muted); font-size: 0.95rem; }
.checklist { list-style: none; }
.checklist li { position: relative; padding: 0.4rem 0 0.4rem 1.6rem; color: var(--muted); }
.checklist li::before { content: "✓"; position: absolute; left: 0; color: var(--accent); font-weight: 700; }
.cta-band {
  background: linear-gradient(135deg, #16283a, #101922); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 2rem; text-align: center;
}
.cta-band h2 { margin-bottom: 0.5rem; }
.cta-band p { color: var(--muted); margin-bottom: 1.25rem; }
/* legal / prose */
.prose { max-width: 680px; }
.prose h1 { font-size: clamp(1.75rem, 5vw, 2.25rem); margin-bottom: 0.4rem; }
.prose .updated { color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }
.prose h2 { font-size: 1.2rem; margin: 2rem 0 0.6rem; }
.prose p, .prose li { color: #c6d2df; font-size: 0.975rem; }
.prose ul { margin: 0.5rem 0 0.5rem 1.25rem; }
.prose li { margin: 0.3rem 0; }
.callout {
  background: var(--surface); border: 1px solid var(--line); border-left: 3px solid var(--accent);
  border-radius: 10px; padding: 1rem 1.25rem; margin: 1.5rem 0; color: var(--muted); font-size: 0.95rem;
}
.contact-card {
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 1.75rem; text-align: center; margin: 1.75rem 0;
}
.contact-card .email { font-size: 1.35rem; font-weight: 640; margin: 0.5rem 0 1.25rem; }
/* footer */
footer { border-top: 1px solid var(--line); background: rgba(0,0,0,0.2); }
.foot-inner {
  max-width: 960px; margin: 0 auto; padding: 2.5rem 1.5rem;
  display: flex; flex-wrap: wrap; gap: 2rem; justify-content: space-between;
}
.foot-col h4 { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-bottom: 0.75rem; }
.foot-col a { display: block; color: var(--text); font-size: 0.925rem; padding: 0.2rem 0; }
.foot-col a:hover { color: var(--accent); text-decoration: none; }
.foot-bottom { max-width: 960px; margin: 0 auto; padding: 0 1.5rem 2.5rem; color: var(--muted); font-size: 0.85rem; }
.foot-bottom .disc { border-top: 1px solid var(--line); padding-top: 1.25rem; }
/* pricing */
.card.featured { border-color: var(--accent-dim); box-shadow: 0 0 0 1px var(--accent-dim); }
.price { font-size: 2.25rem; font-weight: 700; letter-spacing: -0.02em; color: var(--text); margin: 0.25rem 0 0.1rem; }
.price .per { font-size: 1rem; font-weight: 500; color: var(--muted); }
.price-note { color: var(--muted); font-size: 0.9rem; margin-bottom: 1rem; }
.plan-tag { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--accent); }
.card .btn { margin-top: 1.1rem; }
"""

_NAV_LINKS = (
    ("home", "/", "Home"),
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
        f'<a class="btn" href="mailto:{CONTACT_EMAIL}?subject=Cirvia%20early%20access">Request access</a>'
        "</div></div></nav>"
    )


_FOOTER = (
    "<footer><div class=\"foot-inner\">"
    '<div class="foot-col"><div class="logo">Cir<span>via</span></div>'
    '<p style="color:var(--muted);font-size:0.9rem;margin-top:0.5rem;max-width:16em;">'
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
        "<style>" + _CSS + "</style>\n</head>\n<body>\n"
        + _nav(active)
        + '<main class="wrap">\n' + body + "\n</main>\n"
        + _FOOTER
        + "\n</body>\n</html>"
    )


# --------------------------------------------------------------------------
# Home
# --------------------------------------------------------------------------

_HOME_BODY = f"""
<section class="hero">
  <span class="badge">Early access</span>
  <h1>Your portfolio, explained — before you open your brokerage app.</h1>
  <p class="lead">Cirvia is an AI analyst that actually knows your holdings. Connect
  Wealthsimple with read-only access and get a weekday morning digest, macro alerts
  when the world moves, and answers about your real positions on demand.</p>
  <div class="cta-row">
    <a class="btn" href="mailto:{CONTACT_EMAIL}?subject=Cirvia%20early%20access">Request early access</a>
    <a class="btn ghost" href="#how">See how it works</a>
  </div>
</section>

<section id="features">
  <div class="eyebrow">What you get</div>
  <h2>Signal, not noise — mapped to what you own.</h2>
  <div class="grid">
    <div class="card"><h3>Daily digest</h3><p>A weekday morning brief tailored to your
    tickers: overnight moves, what changed, and what to watch — in plain language.</p></div>
    <div class="card"><h3>Macro alerts</h3><p>Fed decisions, energy shocks, geopolitics
    and regulation — surfaced only when they plausibly touch your holdings.</p></div>
    <div class="card"><h3>On-demand answers</h3><p>Ask anything about your book — news,
    performance, drawdowns, context — grounded in your actual positions.</p></div>
    <div class="card"><h3>Automatic sync</h3><p>Your TFSA, RRSP, and taxable accounts stay
    up to date through a secure, read-only brokerage connection.</p></div>
  </div>
</section>

<section id="how">
  <div class="eyebrow">How it works</div>
  <h2>Three steps. No brokerage password ever leaves your bank.</h2>
  <div class="steps">
    <div class="step"><div class="num"></div><div><h3>Connect Wealthsimple</h3>
    <p>Link your account through SnapTrade's secure Connection Portal. Cirvia never sees
    or stores your brokerage login.</p></div></div>
    <div class="step"><div class="num"></div><div><h3>We read your holdings</h3>
    <p>Read-only access syncs your positions and balances. Cirvia can never place a trade
    or move money.</p></div></div>
    <div class="step"><div class="num"></div><div><h3>Get informed, daily</h3>
    <p>Receive your morning digest and macro alerts, and ask questions whenever you like.</p></div></div>
  </div>
</section>

<section id="security">
  <div class="eyebrow">Trust &amp; security</div>
  <h2>Built read-only, private by design.</h2>
  <ul class="checklist">
    <li>Read-only brokerage access — Cirvia informs, it never trades or advises buy/sell.</li>
    <li>Your brokerage credentials are never seen or stored by us.</li>
    <li>Per-user data is isolated at the database level; one user can never see another's.</li>
    <li>Broker connection secrets are encrypted at rest.</li>
  </ul>
</section>

<section id="faq">
  <div class="eyebrow">FAQ</div>
  <h2>Questions</h2>
  <div class="grid">
    <div class="card"><h3>Can Cirvia trade for me?</h3><p>No. Access is strictly read-only.
    Cirvia cannot place orders or move funds under any circumstances.</p></div>
    <div class="card"><h3>Is this financial advice?</h3><p>No. Cirvia is informational only —
    it explains and contextualizes, it does not tell you to buy or sell.</p></div>
    <div class="card"><h3>Which brokerages work?</h3><p>Wealthsimple today, via SnapTrade.
    More brokerages that SnapTrade supports may be added over time.</p></div>
    <div class="card"><h3>How is my data protected?</h3><p>Brokerage credentials stay with
    your bank; connection secrets are encrypted; and every account is isolated by row-level
    security. See our <a href="/privacy">Privacy Policy</a>.</p></div>
  </div>
</section>

<section>
  <div class="cta-band">
    <h2>Be first in line.</h2>
    <p>Cirvia is in early access. Tell us you're interested and we'll reach out.</p>
    <a class="btn" href="mailto:{CONTACT_EMAIL}?subject=Cirvia%20early%20access">Request early access</a>
  </div>
</section>
"""

# --------------------------------------------------------------------------
# Contact
# --------------------------------------------------------------------------

_CONTACT_BODY = f"""
<section class="hero" style="padding-bottom:0;">
  <h1>Get in touch</h1>
  <p class="lead">Questions, early-access requests, privacy inquiries, or partnerships —
  we'd love to hear from you.</p>
</section>

<div class="contact-card">
  <div class="eyebrow">Email us</div>
  <div class="email"><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></div>
  <a class="btn" href="mailto:{CONTACT_EMAIL}">Send an email</a>
</div>

<section>
  <h2>What we can help with</h2>
  <div class="grid">
    <div class="card"><h3>Early access</h3><p>Want to try Cirvia? Email us and we'll add
    you to the list.</p></div>
    <div class="card"><h3>Support</h3><p>Trouble connecting your account or a question about
    your digest? We're here.</p></div>
    <div class="card"><h3>Privacy &amp; data</h3><p>Request access to, correction of, or
    deletion of your data. See our <a href="/privacy">Privacy Policy</a>.</p></div>
    <div class="card"><h3>Partnerships &amp; press</h3><p>Working on something related?
    Reach out — we read everything.</p></div>
  </div>
  <p style="color:var(--muted);margin-top:1.5rem;font-size:0.95rem;">We aim to respond within
  two business days.</p>
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
  <span class="badge">Pricing</span>
  <h1>Simple pricing. Start free, go Pro when you're ready.</h1>
  <p class="lead">Read-only, informational, and built for individual investors.
  No brokerage password ever leaves your bank — on any plan.</p>
</section>

<section>
  <div class="grid">
    <div class="card">
      <div class="plan-tag">Free</div>
      <div class="price">$0<span class="per"> /mo</span></div>
      <p class="price-note">For getting started and kicking the tires.</p>
      <ul class="checklist">
        <li>1 connected account</li>
        <li>Weekly digest on up to 3 holdings</li>
        <li>5 chat questions per day</li>
        <li>No macro alerts</li>
      </ul>
      <a class="btn ghost" href="mailto:{CONTACT_EMAIL}?subject=Cirvia%20early%20access">Start free</a>
    </div>
    <div class="card featured">
      <div class="plan-tag">Pro</div>
      <div class="price">$12<span class="per"> /mo</span></div>
      <p class="price-note">or $120/yr — two months free.</p>
      <ul class="checklist">
        <li>Unlimited connected accounts</li>
        <li>Daily weekday digest across all holdings</li>
        <li>Macro alerts when the world moves</li>
        <li>Unlimited chat</li>
      </ul>
      <a class="btn" href="mailto:{CONTACT_EMAIL}?subject=Cirvia%20early%20access">Go Pro</a>
    </div>
  </div>
</section>

<section id="pricing-faq">
  <div class="eyebrow">Billing FAQ</div>
  <h2>Questions about plans</h2>
  <div class="grid">
    <div class="card"><h3>Can I cancel anytime?</h3><p>Yes. Cancel whenever you like —
    your Pro features stay active until the end of the current billing period.</p></div>
    <div class="card"><h3>Is there a yearly option?</h3><p>Yes. Pro is $12/mo or $120/yr,
    which works out to two months free versus paying monthly.</p></div>
    <div class="card"><h3>What happens on the Free plan?</h3><p>You keep one connected
    account, a weekly digest on up to three holdings, and five chat questions a day —
    free, indefinitely.</p></div>
    <div class="card"><h3>Do you offer refunds?</h3><p>Reach out and we'll make it right.
    Email us at <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>.</p></div>
  </div>
</section>

<section>
  <div class="cta-band">
    <h2>Ready when you are.</h2>
    <p>Cirvia is in early access. Tell us you're interested and we'll get you set up.</p>
    <a class="btn" href="mailto:{CONTACT_EMAIL}?subject=Cirvia%20early%20access">Go Pro</a>
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
