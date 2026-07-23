import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import {
  BrowserFrame,
  Caption,
  Logo,
  MaskedHeadline,
  SceneFade,
  Screen,
  TypingDots,
  panelStyle,
} from "./components";
import { C, ease, rise } from "./theme";

type SceneProps = { dur: number };

const Center: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill
    style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
    }}
  >
    {children}
  </AbsoluteFill>
);

// ---------------------------------------------------------------------------
// Demo 1 — hook: the problem, then the product name
// ---------------------------------------------------------------------------

export const DemoHook: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const hSize = Math.min(96, width * 0.072);
  return (
    <SceneFade frame={frame} duration={dur}>
      <Screen glow={false}>
        <div
          style={{
            position: "absolute",
            top: 54,
            left: 64,
            fontSize: 26,
            fontWeight: 500,
            color: C.ink3,
            fontVariantNumeric: "tabular-nums",
            ...rise(frame, 4, 16, 8),
          }}
        >
          4:58 AM
        </div>
        <Center>
          <MaskedHeadline
            frame={frame}
            at={10}
            size={hSize}
            lines={["Markets move", "while you sleep."]}
          />
          <div style={{ height: 54 }} />
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 20,
              ...rise(frame, 92, 22),
            }}
          >
            <Logo size={44} />
            <span style={{ fontSize: 32, fontWeight: 500, color: C.ink2 }}>
              reads them for you — by 7:45 AM.
            </span>
          </div>
        </Center>
      </Screen>
    </SceneFade>
  );
};

// ---------------------------------------------------------------------------
// Demo 2 — onboarding: connect a brokerage read-only, holdings sync
// ---------------------------------------------------------------------------

const STEPS = [
  "Connect your brokerage",
  "Sync your holdings",
  "Choose holdings to follow",
  "Digest preferences",
  "Delivery",
];

const BROKERS = ["Wealthsimple", "Questrade", "150+ more via SnapTrade"];

export const DemoConnect: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  // step 1 stays active until the sync panel takes over
  const synced = frame >= 175;
  const pickT = ease(frame, 78, 14); // Wealthsimple tile confirms
  const panel2T = ease(frame, 108, 16); // crossfade to the sync panel
  const barT = ease(frame, 118, 46); // progress bar fill
  return (
    <SceneFade frame={frame} duration={dur}>
      <Screen>
        <Center>
          <div style={rise(frame, 6, 22, 20)}>
            <BrowserFrame width={1300} height={720} url="cirvia.ca/app/onboarding">
              <div style={{ display: "flex", height: "100%" }}>
                {/* progress rail */}
                <div
                  style={{
                    width: 360,
                    borderRight: `1px solid ${C.line}`,
                    padding: "36px 34px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 22,
                  }}
                >
                  {STEPS.map((s, i) => {
                    const active = i === 0 && !synced;
                    const done = i === 0 && synced;
                    const current = i === 1 && synced;
                    return (
                      <div
                        key={s}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 14,
                          ...rise(frame, 14 + i * 5, 14, 8),
                        }}
                      >
                        <span
                          style={{
                            width: 30,
                            height: 30,
                            borderRadius: 99,
                            flexShrink: 0,
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: 14.5,
                            fontWeight: 700,
                            background: active || current ? C.accent : "transparent",
                            border:
                              active || current ? "none" : `1.5px solid ${done ? C.gain : C.line}`,
                            color: active || current ? "#fff" : done ? C.gain : C.ink3,
                          }}
                        >
                          {done ? "✓" : i + 1}
                        </span>
                        <span
                          style={{
                            fontSize: 17.5,
                            fontWeight: active || current ? 650 : 500,
                            color: active || current ? C.ink : C.ink3,
                          }}
                        >
                          {s}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {/* content panel */}
                <div style={{ flex: 1, position: "relative", padding: "44px 52px" }}>
                  {/* panel 1: broker picker */}
                  <div style={{ position: "absolute", inset: "44px 52px", opacity: 1 - panel2T }}>
                    <div
                      style={{
                        fontSize: 30,
                        fontWeight: 750,
                        color: C.ink,
                        letterSpacing: "-0.02em",
                        ...rise(frame, 18, 18),
                      }}
                    >
                      Connect your brokerage
                    </div>
                    <div style={{ fontSize: 17.5, color: C.ink2, marginTop: 10, ...rise(frame, 24, 18) }}>
                      A read-only connection. Cirvia can never place a trade or move money.
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 30 }}>
                      {BROKERS.map((b, i) => {
                        const picked = i === 0;
                        const hl = picked ? pickT : 0;
                        return (
                          <div
                            key={b}
                            style={{
                              ...panelStyle,
                              borderRadius: 12,
                              borderColor: hl > 0.3 ? C.accent : C.line,
                              background: hl > 0.3 ? "rgba(104,62,182,0.12)" : C.surface2,
                              boxShadow: "none",
                              padding: "19px 24px",
                              display: "flex",
                              alignItems: "center",
                              gap: 14,
                              fontSize: 19,
                              fontWeight: 650,
                              color: i === 2 ? C.ink3 : C.ink,
                              ...rise(frame, 34 + i * 8, 16, 10),
                            }}
                          >
                            <span
                              style={{
                                width: 34,
                                height: 34,
                                borderRadius: 8,
                                background: C.surface1,
                                border: `1px solid ${C.line}`,
                                display: "inline-flex",
                                alignItems: "center",
                                justifyContent: "center",
                                fontSize: 16,
                                fontWeight: 800,
                                color: C.ink2,
                              }}
                            >
                              {i === 2 ? "+" : b[0]}
                            </span>
                            {b}
                            {picked && hl > 0.3 ? (
                              <span style={{ marginLeft: "auto", color: C.accentText, fontSize: 16, opacity: hl }}>
                                Connecting…
                              </span>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        marginTop: 28,
                        color: C.ink3,
                        fontSize: 15.5,
                        ...rise(frame, 60, 16, 8),
                      }}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <rect x="4" y="10" width="16" height="11" rx="2.5" fill={C.accentText} />
                        <path
                          d="M8 10V7a4 4 0 0 1 8 0v3"
                          stroke={C.accentText}
                          strokeWidth="2.5"
                          fill="none"
                        />
                      </svg>
                      Your password stays with your bank. We never see it.
                    </div>
                  </div>
                  {/* panel 2: syncing */}
                  <div style={{ position: "absolute", inset: "44px 52px", opacity: panel2T }}>
                    <div style={{ fontSize: 30, fontWeight: 750, color: C.ink, letterSpacing: "-0.02em" }}>
                      {synced ? "Holdings synced" : "Syncing your holdings…"}
                    </div>
                    <div style={{ fontSize: 17.5, color: C.ink2, marginTop: 10 }}>
                      TFSA, RRSP, and taxable accounts stay current automatically.
                    </div>
                    <div
                      style={{
                        marginTop: 38,
                        height: 10,
                        borderRadius: 99,
                        background: C.surface2,
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${barT * 100}%`,
                          height: "100%",
                          borderRadius: 99,
                          background: C.accent,
                        }}
                      />
                    </div>
                    {synced ? (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 14,
                          marginTop: 34,
                          ...rise(frame, 175, 16),
                        }}
                      >
                        <span
                          style={{
                            width: 40,
                            height: 40,
                            borderRadius: 99,
                            border: `1.5px solid ${C.line}`,
                            color: C.gain,
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: 20,
                            fontWeight: 700,
                          }}
                        >
                          ✓
                        </span>
                        <span style={{ fontSize: 21, fontWeight: 650, color: C.ink }}>
                          2 accounts · 5 holdings · $48,214
                        </span>
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            </BrowserFrame>
          </div>
          <Caption frame={frame} at={210}>
            Read-only by design. <span style={{ color: C.ink, fontWeight: 700 }}>Connected in under three minutes.</span>
          </Caption>
        </Center>
      </Screen>
    </SceneFade>
  );
};

// ---------------------------------------------------------------------------
// Demo 3 — chat: two grounded exchanges
// ---------------------------------------------------------------------------

const typeOn = (frame: number, text: string, from: number, to: number) =>
  text.slice(
    0,
    Math.round(
      interpolate(frame, [from, to], [0, text.length], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
    ),
  );

export const DemoChat: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  const q1 = typeOn(frame, "Why is ENB down today?", 16, 44);
  const q2 = typeOn(frame, "Anything to watch this week?", 150, 182);
  const dots1 = frame >= 50 && frame < 84;
  const dots2 = frame >= 188 && frame < 218;
  const bubble = (user: boolean): React.CSSProperties => ({
    padding: "12px 17px",
    borderRadius: 12,
    background: user ? C.surface2 : "rgba(104,62,182,0.22)",
    color: user ? C.ink : C.ink2,
    fontSize: 18,
    lineHeight: 1.55,
    marginLeft: user ? 150 : 0,
    marginRight: user ? 0 : 150,
    marginTop: 13,
  });
  return (
    <SceneFade frame={frame} duration={dur}>
      <Screen>
        <Center>
          <div
            style={{
              ...panelStyle,
              width: 860,
              borderRadius: 18,
              padding: "24px 28px 26px",
              minHeight: 560,
              display: "flex",
              flexDirection: "column",
              ...rise(frame, 4, 20),
            }}
          >
            <div style={{ fontSize: 19, fontWeight: 650, color: C.ink }}>Ask Cirvia</div>
            <div style={{ flex: 1, marginTop: 6 }}>
              {q1.length > 0 ? <div style={bubble(true)}>{q1}</div> : null}
              {dots1 ? <TypingDots frame={frame} style={{ marginTop: 14 }} /> : null}
              {frame >= 84 ? (
                <div style={{ ...bubble(false), ...rise(frame, 84, 16, 10) }}>
                  Crude fell 3% after OPEC+ signalled higher August output. ENB is your
                  third-largest holding — pipelines are volume businesses, so the move is
                  sentiment more than cash flow.
                </div>
              ) : null}
              {q2.length > 0 ? <div style={bubble(true)}>{q2}</div> : null}
              {dots2 ? <TypingDots frame={frame} style={{ marginTop: 14 }} /> : null}
              {frame >= 218 ? (
                <div style={{ ...bubble(false), ...rise(frame, 218, 16, 10) }}>
                  Apple reports earnings Thursday after close, and the Bank of Canada rate
                  decision lands Thursday morning — that one touches T.TO and your ETFs.
                </div>
              ) : null}
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
              <div
                style={{
                  flex: 1,
                  padding: "13px 16px",
                  borderRadius: 8,
                  border: `1px solid ${C.line}`,
                  background: C.surface2,
                  color: C.ink3,
                  fontSize: 16.5,
                }}
              >
                Any news on my holdings today?
              </div>
              <span
                style={{
                  background: C.accent,
                  color: "#fff",
                  fontWeight: 600,
                  fontSize: 16.5,
                  borderRadius: 999,
                  padding: "13px 26px",
                }}
              >
                Send
              </span>
            </div>
            <div style={{ color: C.ink3, fontSize: 14.5, marginTop: 12 }}>
              Informational only. Cirvia never gives buy or sell advice.
            </div>
          </div>
          <Caption frame={frame} at={264}>
            Every answer grounded in{" "}
            <span style={{ color: C.ink, fontWeight: 700 }}>the positions you actually hold.</span>
          </Caption>
        </Center>
      </Screen>
    </SceneFade>
  );
};

// ---------------------------------------------------------------------------
// Demo 4 — stock detail: chart draws on, metric cards rise
// ---------------------------------------------------------------------------

// deterministic intraday-looking path, gently up and to the right
const CHART_PTS = [
  62, 60, 63, 58, 55, 57, 52, 54, 49, 51, 46, 48, 44, 40, 43, 38, 36, 39, 33, 35,
  30, 32, 27, 29, 24, 26, 21, 23, 18, 20,
];

const chartPath = (w: number, h: number) => {
  const step = w / (CHART_PTS.length - 1);
  return CHART_PTS.map(
    (y, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${((y / 70) * h).toFixed(1)}`,
  ).join(" ");
};

const METRICS: Array<[string, Array<[string, string, string?]>]> = [
  [
    "Valuation",
    [
      ["P/E (ttm)", "54.2"],
      ["PEG", "1.1", C.gain],
      ["P/FCF", "48.9"],
    ],
  ],
  [
    "Growth & profitability",
    [
      ["Revenue YoY", "+62%", C.gain],
      ["Gross margin", "75%", C.gain],
      ["EPS YoY", "+71%", C.gain],
    ],
  ],
  [
    "Financial health",
    [
      ["Debt / equity", "0.4", C.gain],
      ["Current ratio", "3.6", C.gain],
      ["Beta", "1.7", C.warn],
    ],
  ],
];

export const DemoStock: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  const draw = ease(frame, 22, 60);
  const cw = 1120;
  const ch = 250;
  // crosshair follows the tip of the drawn line
  const tipI = Math.min(CHART_PTS.length - 1, draw * (CHART_PTS.length - 1));
  const tipX = (tipI / (CHART_PTS.length - 1)) * cw;
  const lo = Math.floor(tipI);
  const frac = tipI - lo;
  const tipYv =
    CHART_PTS[lo] + (CHART_PTS[Math.min(lo + 1, CHART_PTS.length - 1)] - CHART_PTS[lo]) * frac;
  const tipY = (tipYv / 70) * ch;
  return (
    <SceneFade frame={frame} duration={dur}>
      <Screen>
        <Center>
          <div style={rise(frame, 6, 22, 20)}>
            <BrowserFrame width={1300} height={740} url="cirvia.ca/app/stock/NVDA">
              <div style={{ padding: "26px 44px" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
                  <span style={{ fontSize: 27, fontWeight: 750, color: C.ink, letterSpacing: "-0.015em" }}>
                    NVDA
                  </span>
                  <span style={{ fontSize: 17, color: C.ink3 }}>NVIDIA Corporation</span>
                  <span
                    style={{
                      marginLeft: "auto",
                      fontSize: 24,
                      fontWeight: 700,
                      color: C.ink,
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    $172.41{" "}
                    <span style={{ color: C.gain, fontSize: 18, fontWeight: 600 }}>+2.1%</span>
                  </span>
                </div>
                {/* price chart */}
                <div style={{ position: "relative", marginTop: 20 }}>
                  <svg width={cw} height={ch} style={{ display: "block", overflow: "visible" }}>
                    {[0.25, 0.5, 0.75].map((g) => (
                      <line
                        key={g}
                        x1={0}
                        x2={cw}
                        y1={ch * g}
                        y2={ch * g}
                        stroke={C.line}
                        strokeWidth={1}
                      />
                    ))}
                    <path
                      d={`${chartPath(cw, ch)} L${cw},${ch} L0,${ch} Z`}
                      fill="rgba(104,62,182,0.14)"
                      opacity={draw}
                    />
                    <path
                      d={chartPath(cw, ch)}
                      fill="none"
                      stroke={C.accentText}
                      strokeWidth={3}
                      pathLength={1}
                      strokeDasharray={1}
                      strokeDashoffset={1 - draw}
                    />
                    {draw > 0.02 ? (
                      <>
                        <line
                          x1={tipX}
                          x2={tipX}
                          y1={0}
                          y2={ch}
                          stroke={C.ink3}
                          strokeWidth={1}
                          strokeDasharray="4 5"
                          opacity={0.5}
                        />
                        <circle cx={tipX} cy={tipY} r={6} fill={C.accentText} />
                      </>
                    ) : null}
                  </svg>
                </div>
                {/* metric cards */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginTop: 24 }}>
                  {METRICS.map(([title, rows], i) => (
                    <div
                      key={title}
                      style={{
                        background: C.surface1,
                        border: `1px solid ${C.line}`,
                        borderRadius: 14,
                        padding: "18px 22px",
                        ...rise(frame, 66 + i * 10, 18, 12),
                      }}
                    >
                      <div style={{ fontSize: 15.5, fontWeight: 650, color: C.ink, marginBottom: 10 }}>
                        {title}
                      </div>
                      {rows.map(([label, val, col], j) => (
                        <div
                          key={label}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            padding: "7px 0",
                            borderBottom: j < rows.length - 1 ? `1px solid ${C.line}` : "none",
                            fontSize: 15,
                          }}
                        >
                          <span style={{ color: C.ink3 }}>{label}</span>
                          <span
                            style={{
                              color: col ?? C.ink,
                              fontWeight: 650,
                              fontVariantNumeric: "tabular-nums",
                            }}
                          >
                            {val}
                          </span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
                <div
                  style={{
                    marginTop: 18,
                    color: C.ink2,
                    fontSize: 16,
                    ...rise(frame, 104, 16, 8),
                  }}
                >
                  <span style={{ color: C.ink3 }}>Your position</span>{" "}
                  <span style={{ fontWeight: 650, color: C.ink }}>36 shares · $5,832</span>{" "}
                  <span style={{ color: C.gain, fontWeight: 600 }}>+64.2% total</span>
                </div>
              </div>
            </BrowserFrame>
          </div>
          <Caption frame={frame} at={140}>
            Go one click deep on <span style={{ color: C.ink, fontWeight: 700 }}>any holding.</span>
          </Caption>
        </Center>
      </Screen>
    </SceneFade>
  );
};

// ---------------------------------------------------------------------------
// Demo 5 — pricing: the trial is the hook
// ---------------------------------------------------------------------------

const FREE_FEATURES = ["1 connected account", "Weekly digest, 3 holdings", "3 chat questions / week"];
const PRO_FEATURES = [
  "Unlimited connected accounts",
  "Daily digest across all holdings",
  "Macro alerts when the world moves",
  "10 chat questions / day",
];

const PlanCard: React.FC<{
  frame: number;
  at: number;
  name: string;
  price: string;
  sub: string;
  features: string[];
  featured?: boolean;
}> = ({ frame, at, name, price, sub, features, featured }) => (
  <div
    style={{
      ...panelStyle,
      width: 440,
      borderRadius: 18,
      borderColor: featured ? C.accent : C.line,
      padding: "30px 34px",
      position: "relative",
      ...rise(frame, at, 20),
    }}
  >
    {featured ? (
      <span
        style={{
          position: "absolute",
          top: -16,
          left: 34,
          background: C.accent,
          color: "#fff",
          fontSize: 13.5,
          fontWeight: 700,
          borderRadius: 999,
          padding: "6px 16px",
        }}
      >
        7-DAY FREE TRIAL · NO CARD
      </span>
    ) : null}
    <div style={{ fontSize: 19, fontWeight: 650, color: C.ink }}>{name}</div>
    <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 10 }}>
      <span style={{ fontSize: 44, fontWeight: 800, color: C.ink, letterSpacing: "-0.02em" }}>
        {price}
      </span>
      <span style={{ fontSize: 16, color: C.ink3 }}>{sub}</span>
    </div>
    <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 12 }}>
      {features.map((f, i) => (
        <div
          key={f}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            fontSize: 16.5,
            color: C.ink2,
            ...rise(frame, at + 14 + i * 5, 14, 8),
          }}
        >
          <span style={{ color: featured ? C.accentText : C.ink3, fontWeight: 700 }}>✓</span>
          {f}
        </div>
      ))}
    </div>
  </div>
);

export const DemoPricing: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  return (
    <SceneFade frame={frame} duration={dur}>
      <Screen>
        <Center>
          <MaskedHeadline
            frame={frame}
            at={8}
            size={Math.min(64, width * 0.05)}
            lines={["Start with a week of Pro, free."]}
          />
          <div style={{ height: 46 }} />
          <div style={{ display: "flex", gap: 28, alignItems: "stretch" }}>
            <PlanCard
              frame={frame}
              at={34}
              name="Free"
              price="$0"
              sub="/ month, forever"
              features={FREE_FEATURES}
            />
            <PlanCard
              frame={frame}
              at={46}
              name="Pro"
              price="$15"
              sub="/ month USD · or $120/yr"
              features={PRO_FEATURES}
              featured
            />
          </div>
          <Caption frame={frame} at={120}>
            No card required. Nothing auto-charges.{" "}
            <span style={{ color: C.ink, fontWeight: 700 }}>Cancel anytime.</span>
          </Caption>
        </Center>
      </Screen>
    </SceneFade>
  );
};
