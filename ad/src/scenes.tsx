import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  BrowserFrame,
  Caption,
  DigestCard,
  Logo,
  MaskedHeadline,
  PillButton,
  SceneFade,
  Screen,
  TypingDots,
  panelStyle,
} from "./components";
import { AppDashboard, NotificationPopup } from "./dashboard";
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
// Scene 1 — cold open: 7:45 AM, lock-screen notification, headline
// ---------------------------------------------------------------------------

export const Scene1: React.FC<SceneProps> = ({ dur }) => {
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
          7:45 AM
        </div>
        <Center>
          <div
            style={{
              ...panelStyle,
              width: Math.min(620, width * 0.84),
              padding: "20px 24px",
              marginBottom: 64,
              opacity: ease(frame, 14, 20),
              transform: `translateY(${(1 - ease(frame, 14, 20)) * -28}px)`,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 15,
                fontWeight: 600,
                color: C.ink3,
                marginBottom: 8,
              }}
            >
              <span
                style={{
                  width: 26,
                  height: 26,
                  borderRadius: 7,
                  background: C.accent,
                  color: "#fff",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 15,
                  fontWeight: 800,
                }}
              >
                C
              </span>
              CIRVIA
              <span style={{ marginLeft: "auto", fontWeight: 500 }}>now</span>
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, color: C.ink }}>
              Morning digest
            </div>
            <div style={{ fontSize: 18, color: C.ink2, marginTop: 3, lineHeight: 1.45 }}>
              VFV +0.8 · NVDA +2.1 · ENB −1.2. One thing to watch today.
            </div>
          </div>
          <MaskedHeadline
            frame={frame}
            at={52}
            size={hSize}
            lines={["Know what matters", "before the market opens."]}
          />
        </Center>
      </Screen>
    </SceneFade>
  );
};

// ---------------------------------------------------------------------------
// Scene 2 — the real dashboard: holdings table builds, totals tick up
// ---------------------------------------------------------------------------

export const Scene2: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  const drift = 1 + ease(frame, 0, dur) * 0.015;
  return (
    <SceneFade frame={frame} duration={dur}>
      <Screen>
        <Center>
          <div style={{ ...rise(frame, 6, 22, 20), transform: `scale(${drift})` }}>
            <BrowserFrame width={1300} height={790}>
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  display: "flex",
                  justifyContent: "center",
                  paddingTop: 26,
                  backgroundImage:
                    "radial-gradient(55% 45% at 50% 112%, rgba(104,62,182,0.22), transparent 70%)",
                }}
              >
                <div style={{ transform: "scale(0.95)", transformOrigin: "top center" }}>
                  <AppDashboard frame={frame} rowsAt={26} tickAt={40} />
                </div>
              </div>
            </BrowserFrame>
          </div>
          <Caption frame={frame} at={70}>
            A brief for <span style={{ color: C.ink, fontWeight: 700 }}>your</span> holdings.
            Not the whole market.
          </Caption>
        </Center>
      </Screen>
    </SceneFade>
  );
};

// ---------------------------------------------------------------------------
// Scene 3 — macro alert ripples into the two holdings it touches
// ---------------------------------------------------------------------------

export const Scene3: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  return (
    <SceneFade frame={frame} duration={dur}>
      <Screen>
        <Center>
          <BrowserFrame width={1300} height={790}>
            <div
              style={{
                position: "absolute",
                inset: 0,
                display: "flex",
                justifyContent: "center",
                paddingTop: 26,
                backgroundImage:
                  "radial-gradient(55% 45% at 50% 112%, rgba(104,62,182,0.22), transparent 70%)",
              }}
            >
              <div style={{ transform: "scale(0.9)", transformOrigin: "top center" }}>
                <AppDashboard frame={frame} highlightAt={52} alertAt={80} />
              </div>
            </div>
          </BrowserFrame>
          <Caption frame={frame} at={118}>
            Alerts only when world events touch what you own.
          </Caption>
        </Center>
        {/* OS notification over everything */}
        <div style={{ position: "absolute", top: 44, right: 56 }}>
          <NotificationPopup
            frame={frame}
            at={12}
            title="Macro alert"
            body="OPEC+ signals higher August output. Crude down 3%; touches ENB and SU."
          />
        </div>
      </Screen>
    </SceneFade>
  );
};

// ---------------------------------------------------------------------------
// Scene 4 — chat: question types on, dots, grounded answer
// ---------------------------------------------------------------------------

export const Scene4: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  const q = "Why is ENB down today?";
  const typed = q.slice(
    0,
    Math.round(interpolate(frame, [18, 48], [0, q.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })),
  );
  const dotsVisible = frame >= 54 && frame < 92;
  return (
    <SceneFade frame={frame} duration={dur}>
      <Screen>
        <Center>
          <div
            style={{
              ...panelStyle,
              width: 800,
              borderRadius: 18,
              padding: "24px 28px 26px",
              minHeight: 430,
              display: "flex",
              flexDirection: "column",
              ...rise(frame, 4, 20),
            }}
          >
            <div style={{ fontSize: 19, fontWeight: 650, color: C.ink }}>Ask Cirvia</div>
            <div style={{ flex: 1, marginTop: 10 }}>
              {typed.length > 0 ? (
                <div
                  style={{
                    padding: "12px 17px",
                    borderRadius: 12,
                    background: C.surface2,
                    color: C.ink,
                    fontSize: 18,
                    lineHeight: 1.55,
                    marginLeft: 120,
                    marginTop: 12,
                  }}
                >
                  {typed}
                </div>
              ) : null}
              {dotsVisible ? <TypingDots frame={frame} style={{ marginTop: 14 }} /> : null}
              {frame >= 92 ? (
                <div
                  style={{
                    padding: "12px 17px",
                    borderRadius: 12,
                    background: "rgba(104,62,182,0.22)",
                    color: C.ink2,
                    fontSize: 18,
                    lineHeight: 1.55,
                    marginRight: 120,
                    marginTop: 14,
                    ...rise(frame, 92, 16, 10),
                  }}
                >
                  Crude fell 3% after OPEC+ signalled higher output. ENB is your
                  third-largest holding.
                </div>
              ) : null}
            </div>
            {/* real chat input row from the app */}
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
          <Caption frame={frame} at={132}>
            Ask anything. Answers grounded in your actual positions.
          </Caption>
        </Center>
      </Screen>
    </SceneFade>
  );
};

// ---------------------------------------------------------------------------
// Scene 5 — the signature shot: one brief fans out to four channels
// ---------------------------------------------------------------------------

const smsText = "Cirvia, 7:45 AM: VFV +0.8, NVDA +2.1, ENB −1.2. BoC decision lands Thursday.";

const PhoneSMS: React.FC<{ k: number }> = ({ k }) => (
  <div
    style={{
      ...panelStyle,
      width: 300 * k,
      height: 330 * k,
      borderRadius: 28 * k,
      padding: 18 * k,
      overflow: "hidden",
    }}
  >
    <div
      style={{
        textAlign: "center",
        fontSize: 15 * k,
        fontWeight: 600,
        color: C.ink3,
        paddingBottom: 12 * k,
        borderBottom: `1px solid ${C.line}`,
      }}
    >
      Cirvia
    </div>
    <div
      style={{
        marginTop: 16 * k,
        background: C.surface2,
        borderRadius: 14 * k,
        padding: `${12 * k}px ${14 * k}px`,
        fontSize: 15.5 * k,
        lineHeight: 1.5,
        color: C.ink2,
      }}
    >
      {smsText}
    </div>
    <div style={{ fontSize: 12 * k, color: C.ink3, marginTop: 8 * k, marginLeft: 6 * k }}>
      Text message · 7:45 AM
    </div>
  </div>
);

const EmailCard: React.FC<{ k: number }> = ({ k }) => (
  <div style={{ ...panelStyle, width: 470 * k, padding: `${18 * k}px ${22 * k}px` }}>
    <div style={{ fontSize: 13 * k, fontWeight: 600, color: C.ink3, marginBottom: 10 * k }}>
      Inbox
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 12 * k }}>
      <span style={{ width: 9 * k, height: 9 * k, borderRadius: 99, background: C.accentText }} />
      <div>
        <div style={{ fontSize: 17 * k, fontWeight: 700, color: C.ink }}>
          Cirvia
          <span style={{ fontWeight: 500, color: C.ink3, marginLeft: 10 * k, fontSize: 14 * k }}>
            7:45 AM
          </span>
        </div>
        <div style={{ fontSize: 15.5 * k, color: C.ink2, marginTop: 2 * k }}>
          Your morning digest — Jul 6
        </div>
        <div style={{ fontSize: 14 * k, color: C.ink3, marginTop: 2 * k }}>
          VFV +0.8, NVDA +2.1, ENB −1.2. One thing to watch…
        </div>
      </div>
    </div>
  </div>
);

const DiscordCard: React.FC<{ k: number }> = ({ k }) => (
  <div style={{ ...panelStyle, width: 470 * k, padding: `${18 * k}px ${22 * k}px` }}>
    <div style={{ display: "flex", gap: 12 * k }}>
      <span
        style={{
          width: 38 * k,
          height: 38 * k,
          borderRadius: 99,
          background: C.accent,
          color: "#fff",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          fontWeight: 800,
          fontSize: 19 * k,
          flexShrink: 0,
        }}
      >
        C
      </span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 16 * k, fontWeight: 700, color: C.ink }}>
          Cirvia
          <span
            style={{
              background: C.accent,
              color: "#fff",
              fontSize: 10.5 * k,
              fontWeight: 700,
              borderRadius: 4 * k,
              padding: `${1.5 * k}px ${5 * k}px`,
              marginLeft: 8 * k,
              verticalAlign: "middle",
            }}
          >
            BOT
          </span>
          <span style={{ fontWeight: 500, color: C.ink3, marginLeft: 10 * k, fontSize: 13 * k }}>
            Today at 7:45 AM
          </span>
        </div>
        {/* real adapter posts plain webhook content, not an embed */}
        <div style={{ fontSize: 14.5 * k, color: C.ink2, marginTop: 6 * k, lineHeight: 1.55 }}>
          Morning digest — Jul 6
          <br />
          VFV +0.8 · NVDA +2.1 · ENB −1.2. BoC decision lands Thursday.
        </div>
      </div>
    </div>
  </div>
);

const WebMini: React.FC<{ k: number; frame: number }> = ({ k, frame }) => (
  <BrowserFrame width={470 * k} height={280 * k} url="cirvia.app">
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div style={{ transform: `scale(${Math.min(1, k * 1.05)})` }}>
        <DigestCard frame={frame} width={330} s={0.78} showValue={false} rowsAt={0} />
      </div>
    </div>
  </BrowserFrame>
);

export const Scene5: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const portrait = height > width;
  const k = width >= 1600 ? 1 : 0.66;
  const cx = width / 2;
  const cy = height / 2 - (portrait ? 40 : 20);
  const spots = portrait
    ? [
        { x: 0.28, y: 0.29 }, // phone
        { x: 0.72, y: 0.27 }, // email
        { x: 0.28, y: 0.71 }, // web
        { x: 0.72, y: 0.73 }, // discord
      ]
    : [
        { x: 0.16, y: 0.55 }, // phone
        { x: 0.8, y: 0.26 }, // email
        { x: 0.3, y: 0.17 }, // web
        { x: 0.8, y: 0.7 }, // discord
      ];
  const devices = [
    <PhoneSMS key="p" k={k} />,
    <EmailCard key="e" k={k} />,
    <WebMini key="w" k={k} frame={frame} />,
    <DiscordCard key="d" k={k} />,
  ];
  return (
    <SceneFade frame={frame} duration={dur}>
      <Screen>
        {/* center source card */}
        <div
          style={{
            position: "absolute",
            left: cx,
            top: cy,
            transform: `translate(-50%, -50%) scale(${1 - ease(frame, 20, 40) * 0.12})`,
            zIndex: 2,
          }}
        >
          <DigestCard frame={frame} width={340 * Math.max(k, 0.85)} s={0.9} showValue={false} rowsAt={2} />
        </div>
        {/* fan-out devices */}
        {devices.map((node, i) => {
          const t = ease(frame, 22 + i * 12, 34);
          const tx = interpolate(t, [0, 1], [cx, spots[i].x * width]);
          const ty = interpolate(t, [0, 1], [cy, spots[i].y * height]);
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: tx,
                top: ty,
                transform: `translate(-50%, -50%) scale(${0.72 + t * 0.28})`,
                opacity: t,
                zIndex: 1,
              }}
            >
              {node}
            </div>
          );
        })}
        <Caption frame={frame} at={110}>
          Delivered where you already are.{" "}
          <span style={{ color: C.ink, fontWeight: 700 }}>Text, email, Discord, web.</span>
        </Caption>
      </Screen>
    </SceneFade>
  );
};

// ---------------------------------------------------------------------------
// Scene 6 — trust beat, typography only
// ---------------------------------------------------------------------------

const TRUST = [
  "Read-only. Cirvia can never trade.",
  "Your password stays with your bank.",
  "Connected in under 3 minutes.",
];

export const Scene6: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  return (
    <SceneFade frame={frame} duration={dur}>
      <Screen glow={false}>
        <Center>
          <div style={{ display: "flex", flexDirection: "column", gap: 42 }}>
            {TRUST.map((line, i) => (
              <div
                key={line}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 22,
                  ...rise(frame, 16 + i * 26, 20),
                }}
              >
                <span
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 99,
                    border: `1.5px solid ${C.line}`,
                    color: C.accentText,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 21,
                    fontWeight: 700,
                    flexShrink: 0,
                  }}
                >
                  ✓
                </span>
                <span style={{ fontSize: 42, fontWeight: 650, color: C.ink, letterSpacing: "-0.015em" }}>
                  {line}
                </span>
              </div>
            ))}
          </div>
        </Center>
      </Screen>
    </SceneFade>
  );
};

// ---------------------------------------------------------------------------
// Scene 7 — end card: silk glow rises, logo, line, CTA
// ---------------------------------------------------------------------------

export const Scene7: React.FC<SceneProps> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const hSize = Math.min(72, width * 0.058);
  const glowRise = ease(frame, 0, 70);
  const drift = Math.sin(frame / 46) * 14;
  return (
    <SceneFade frame={frame} duration={dur} outDur={2}>
      <Screen glow={false}>
        {/* rising silk glow */}
        <div
          style={{
            position: "absolute",
            left: "50%",
            bottom: -height * 0.42 + glowRise * height * 0.18,
            width: width * 1.15,
            height: height * 0.75,
            transform: `translateX(calc(-50% + ${drift}px))`,
            background:
              "radial-gradient(50% 55% at 50% 42%, rgba(104,62,182,0.75), transparent 70%)",
            filter: "blur(46px)",
            opacity: glowRise,
          }}
        />
        <div
          style={{
            position: "absolute",
            left: "50%",
            bottom: -height * 0.34 + glowRise * height * 0.16,
            width: width * 0.6,
            height: height * 0.4,
            transform: `translateX(calc(-50% - ${drift}px))`,
            background:
              "radial-gradient(50% 55% at 50% 40%, rgba(181,153,255,0.5), transparent 72%)",
            filter: "blur(38px)",
            opacity: glowRise * 0.9,
          }}
        />
        <Center>
          <div style={rise(frame, 14, 22)}>
            <Logo size={Math.min(52, width * 0.045)} />
          </div>
          <div style={{ height: 26 }} />
          <MaskedHeadline
            frame={frame}
            at={30}
            size={hSize}
            lines={["Know your portfolio by 7:45."]}
          />
          <div style={{ height: 44 }} />
          <div style={rise(frame, 56, 22)}>
            <PillButton size={Math.min(26, width * 0.021)}>Get started free</PillButton>
          </div>
        </Center>
        <div
          style={{
            position: "absolute",
            bottom: "4.5%",
            left: 0,
            right: 0,
            textAlign: "center",
            fontSize: 19,
            color: C.ink3,
            ...rise(frame, 80, 20, 8),
          }}
        >
          Not financial advice. Read-only access.
        </div>
      </Screen>
    </SceneFade>
  );
};
