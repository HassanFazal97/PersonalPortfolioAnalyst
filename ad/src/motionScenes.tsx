import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import {
  Broll,
  Center,
  Disclaimer,
  NotificationSlide,
  PhoneFrame,
  PhoneScreenFill,
  PunchLine,
  StatNumber,
  punch,
} from "./kinetic";
import { Logo, PillButton } from "./components";
import { C, FONT, rise } from "./theme";

// ---------------------------------------------------------------------------
// CirviaMotion v3 — full feature walkthrough, after feedback that v2 (a
// short proof-led hook) needed to instead cover what the app actually does.
// Every screen shown is a real screenshot captured from the live site with
// Playwright on 2026-08-13 (see ad/README.md) — six assets in public/ui/:
// macro alert, chat, morning digest, verified/critic, the valuation
// screener, and the Pro plan's full feature list. No feature is shown with
// a fabricated screenshot: Deep Dives and Risk Lab have no public sample
// page to capture, so they're covered honestly via the real Pro-plan
// checklist screenshot + a caption, not an invented mockup of either.
//
// Stats (100 picks / 67% / +5.39%) pulled from www.cirvia.ca on
// 2026-08-13 — refresh before reusing this cut, the site updates daily.
// ---------------------------------------------------------------------------

type SceneProps = { dur: number };

const TRACK_RECORD = {
  picksMeasured: "100",
  beatSp500: "67%",
  avgReturn: "+5.39%",
};

// ---- Cold open ----
export const ColdOpen: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Center>
        <PunchLine frame={frame} at={4} size={68}>
          The AI analyst that shows its work.
        </PunchLine>
      </Center>
    </AbsoluteFill>
  );
};

// ---- Beat: connect a brokerage (typography only — no screenshot exists
// of the real OAuth connect flow to capture honestly) ----
export const BeatConnect: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Center>
        <PunchLine frame={frame} at={6} size={54}>
          Connect Wealthsimple, Questrade, and more.
        </PunchLine>
        <div style={{ height: 14 }} />
        <PunchLine frame={frame} at={22} size={40} color={C.accentText} weight={650}>
          Read-only, in under three minutes.
        </PunchLine>
      </Center>
    </AbsoluteFill>
  );
};

// ---- Shared layout: phone + one notification, caption below ----
const PhoneBeat: React.FC<{
  frame: number;
  captionAt: number;
  children: React.ReactNode;
  phoneContent: React.ReactNode;
}> = ({ frame, captionAt, children, phoneContent }) => (
  <AbsoluteFill style={{ background: C.bg }}>
    <AbsoluteFill
      style={{
        backgroundImage:
          "radial-gradient(55% 40% at 50% 34%, rgba(104,62,182,0.28), transparent 70%)",
      }}
    />
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-start", paddingTop: 150 }}>
      <PhoneFrame width={410}>{phoneContent}</PhoneFrame>
    </AbsoluteFill>
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "flex-end",
        padding: "0 72px 96px",
      }}
    >
      <div style={{ opacity: punch(frame, captionAt, 14) }}>{children}</div>
    </AbsoluteFill>
  </AbsoluteFill>
);

// ---- Beat: morning digest ----
export const BeatDigest: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <PhoneBeat
      frame={frame}
      captionAt={36}
      phoneContent={
        <NotificationSlide frame={frame} inAt={6} file="ui/ui-digest-card.png" top={64} width={410 * 0.86} />
      }
    >
      <PunchLine frame={frame} at={36} size={44}>
        Written from your real holdings, every weekday morning.
      </PunchLine>
    </PhoneBeat>
  );
};

// ---- Beat: macro alerts ----
export const BeatMacroAlert: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <PhoneBeat
      frame={frame}
      captionAt={36}
      phoneContent={
        <NotificationSlide frame={frame} inAt={6} file="ui/ui-macro-alert.png" top={64} width={410 * 0.86} />
      }
    >
      <PunchLine frame={frame} at={36} size={44}>
        Alerts only when world events touch what you own.
      </PunchLine>
    </PhoneBeat>
  );
};

// ---- Beat: on-demand chat ----
export const BeatChat: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <PhoneBeat
      frame={frame}
      captionAt={34}
      phoneContent={
        <NotificationSlide frame={frame} inAt={6} file="ui/ui-chat-question.png" top={64} width={410 * 0.86} />
      }
    >
      <PunchLine frame={frame} at={34} size={44}>
        Ask anything. Answers grounded in your actual positions.
      </PunchLine>
    </PhoneBeat>
  );
};

// ---- Beat: valuation screener (full-screen real content, not a
// notification) ----
export const BeatScreener: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <PhoneBeat
      frame={frame}
      captionAt={40}
      phoneContent={<PhoneScreenFill frame={frame} at={4} file="ui/ui-screener.png" />}
    >
      <PunchLine frame={frame} at={40} size={40}>
        563 stocks. A cheap-or-expensive verdict for every one, against real
        peers.
      </PunchLine>
    </PhoneBeat>
  );
};

// ---- Beat: verified / adversarial critic ----
export const BeatVerified: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <PhoneBeat
      frame={frame}
      captionAt={38}
      phoneContent={
        <NotificationSlide frame={frame} inAt={6} file="ui/ui-verified.png" top={64} width={410 * 0.86} />
      }
    >
      <PunchLine frame={frame} at={38} size={42}>
        An adversarial critic checks every claim before it ships.
      </PunchLine>
    </PhoneBeat>
  );
};

// ---- Beat: the mechanism (no phone) ----
export const BeatFrozenEntry: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Center>
        <PunchLine frame={frame} at={6} size={56}>
          {TRACK_RECORD.picksMeasured} Model Picks. Frozen entry price. Nothing deleted.
        </PunchLine>
      </Center>
    </AbsoluteFill>
  );
};

// ---- Beat: stat — beat rate ----
export const BeatStatBeatRate: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Center>
        <StatNumber frame={frame} at={6}>
          {TRACK_RECORD.beatSp500}
        </StatNumber>
        <div style={{ height: 18 }} />
        <PunchLine frame={frame} at={20} size={44} color={C.ink2} weight={650}>
          beat the S&amp;P 500, same span
        </PunchLine>
      </Center>
      <Disclaimer frame={frame} at={34}>
        Past performance is not indicative of future results.
      </Disclaimer>
    </AbsoluteFill>
  );
};

// ---- Beat: stat — average return ----
export const BeatStatAvgReturn: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Center>
        <StatNumber frame={frame} at={4}>
          {TRACK_RECORD.avgReturn}
        </StatNumber>
        <div style={{ height: 18 }} />
        <PunchLine frame={frame} at={18} size={44} color={C.ink2} weight={650}>
          average return per pick
        </PunchLine>
      </Center>
      <Disclaimer frame={frame} at={0}>
        Past performance is not indicative of future results.
      </Disclaimer>
    </AbsoluteFill>
  );
};

// ---- Beat: read-only & private (typography, real copy from the site's
// "Built read-only" checklist) ----
export const BeatReadOnly: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  const LINES = ["Read-only.", "We can never trade for you.", "Your brokerage password stays with your bank."];
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Center>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {LINES.map((line, i) => (
            <PunchLine key={line} frame={frame} at={8 + i * 16} size={i === 0 ? 58 : 38} color={i === 0 ? C.ink : C.ink2} weight={i === 0 ? 800 : 600}>
              {line}
            </PunchLine>
          ))}
        </div>
      </Center>
    </AbsoluteFill>
  );
};

// ---- Beat: pricing / everything Pro unlocks (full-screen real content) ----
export const BeatPricing: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  return (
    <PhoneBeat
      frame={frame}
      captionAt={44}
      phoneContent={<PhoneScreenFill frame={frame} at={4} file="ui/ui-pricing.png" />}
    >
      <PunchLine frame={frame} at={44} size={40}>
        Free to start. Pro unlocks the rest, $20 a month.
      </PunchLine>
    </PhoneBeat>
  );
};

// ---- End card ----
export const MotionEndCard: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Broll file="video/shot-c-endcard-loop.mp4" startFrom={30} scrim={0.15} />
      <Center>
        <div style={{ ...rise(frame, 6, 16) }}>
          <Logo size={46} />
        </div>
        <div style={{ height: 20 }} />
        <div
          style={{
            ...rise(frame, 16, 16),
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: Math.min(56, width * 0.072),
            color: C.ink,
            lineHeight: 1.1,
          }}
        >
          The AI analyst that shows its work.
        </div>
        <div style={{ height: 30 }} />
        <div style={{ ...rise(frame, 34, 16) }}>
          <PillButton size={22}>Get started free</PillButton>
        </div>
        <div
          style={{
            ...rise(frame, 46, 16),
            marginTop: 22,
            fontSize: 22,
            fontWeight: 600,
            color: C.accentText,
          }}
        >
          cirvia.ca
        </div>
      </Center>
      <div
        style={{
          position: "absolute",
          bottom: "5%",
          left: 0,
          right: 0,
          textAlign: "center",
          fontSize: 15,
          color: C.ink3,
          lineHeight: 1.5,
          padding: "0 40px",
          ...rise(frame, 60, 16),
        }}
      >
        Model Picks. Not financial advice.
        <br />
        Past performance is not indicative of future results.
      </div>
    </AbsoluteFill>
  );
};
