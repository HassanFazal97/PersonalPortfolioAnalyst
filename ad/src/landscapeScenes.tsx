import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { SplitScene } from "./landscape";
import { Broll } from "./kinetic";
import { Logo, PillButton } from "./components";
import { C, FONT, rise } from "./theme";

// ---------------------------------------------------------------------------
// CirviaWalkthrough — landscape (1920x1080) rebuild, replacing the vertical
// phone-notification cut entirely. Every beat but the end card is a real,
// full-page screenshot of the live site (captured 2026-08-13, same
// Playwright method as the vertical cut's assets — see ad/README.md),
// shown in a browser-chrome frame with continuous Ken Burns motion, next to
// a populated text column — not a caption sitting on empty background.
// Beats crossfade into each other (see Root.tsx's TransitionSeries) instead
// of hard-cutting, for the "smooth flowing" the vertical cut lacked.
// ---------------------------------------------------------------------------

const TOTAL = 8;

type SceneProps = { dur: number };

export const SceneHero: React.FC<SceneProps> = ({ dur }) => (
  <SplitScene
    dur={dur}
    url="cirvia.ca"
    file="ui-land/land-hero.png"
    eyebrow="Cirvia"
    title="The AI analyst that shows its work."
    description="Real holdings, briefed every morning. Every number computed, every claim verified, with a public track record to prove it."
    index={1}
    total={TOTAL}
  />
);

export const SceneDigest: React.FC<SceneProps> = ({ dur }) => (
  <SplitScene
    dur={dur}
    url="cirvia.ca/sample-digest"
    file="ui-land/land-digest.png"
    eyebrow="Morning digest"
    title="Written from your real holdings."
    description="What changed overnight, the one risk worth naming, and what to watch today — every weekday morning."
    index={2}
    total={TOTAL}
  />
);

export const SceneChat: React.FC<SceneProps> = ({ dur }) => (
  <SplitScene
    dur={dur}
    url="cirvia.ca"
    file="ui-land/land-chat.png"
    eyebrow="On-demand answers"
    title="Ask anything about your positions."
    description="Every answer starts from the holdings you actually hold, not a generic market take."
    index={3}
    total={TOTAL}
  />
);

export const SceneScreener: React.FC<SceneProps> = ({ dur }) => (
  <SplitScene
    dur={dur}
    url="cirvia.ca/screener"
    file="ui-land/land-screener.png"
    eyebrow="Valuation screener"
    title="Is this stock cheap or expensive?"
    description="A verdict for all 563 S&P 500 and TSX names, computed against real industry peers today."
    index={4}
    total={TOTAL}
  />
);

export const SceneTrackRecord: React.FC<SceneProps> = ({ dur }) => (
  <SplitScene
    dur={dur}
    url="cirvia.ca/track-record"
    file="ui-land/land-trackrecord.png"
    eyebrow="The proof"
    title="Every pick. Priced honestly."
    description="100 Model Picks measured, 67% beat the S&P 500 over the same span. Misses stay on the board — nothing is ever deleted."
    index={5}
    total={TOTAL}
  />
);

export const SceneReadOnly: React.FC<SceneProps> = ({ dur }) => (
  <SplitScene
    dur={dur}
    url="cirvia.ca"
    file="ui-land/land-readonly.png"
    eyebrow="Read-only by design"
    title="We can never trade for you."
    description="Your brokerage password stays with your bank. Everything is encrypted, and your data is yours alone."
    index={6}
    total={TOTAL}
  />
);

export const ScenePricing: React.FC<SceneProps> = ({ dur }) => (
  <SplitScene
    dur={dur}
    url="cirvia.ca/pricing"
    file="ui-land/land-pricing.png"
    eyebrow="Plans"
    title="Free to start. Pro unlocks the rest."
    description="Top Picks, Deep Dives, Risk Lab, and macro alerts — from $20 a month, with a 7-day Pro trial on every new account."
    index={7}
    total={TOTAL}
  />
);

export const SceneEndCard: React.FC<SceneProps> = () => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Broll file="video/shot-c-endcard-loop.mp4" startFrom={30} scrim={0.15} />
      <AbsoluteFill
        style={{
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
        }}
      >
        <div style={{ ...rise(frame, 6, 18) }}>
          <Logo size={52} />
        </div>
        <div style={{ height: 26 }} />
        <div
          style={{
            ...rise(frame, 18, 18),
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: Math.min(64, width * 0.04),
            color: C.ink,
            textAlign: "center",
          }}
        >
          The AI analyst that shows its work.
        </div>
        <div style={{ height: 36 }} />
        <div style={{ ...rise(frame, 38, 18) }}>
          <PillButton size={24}>Get started free</PillButton>
        </div>
        <div
          style={{
            ...rise(frame, 50, 18),
            marginTop: 26,
            fontSize: 24,
            fontWeight: 600,
            color: C.accentText,
          }}
        >
          cirvia.ca
        </div>
      </AbsoluteFill>
      <div
        style={{
          position: "absolute",
          bottom: "6%",
          left: 0,
          right: 0,
          textAlign: "center",
          fontSize: 16,
          color: C.ink3,
          ...rise(frame, 64, 18),
        }}
      >
        Model Picks. Not financial advice. Past performance is not indicative of future results.
      </div>
    </AbsoluteFill>
  );
};
