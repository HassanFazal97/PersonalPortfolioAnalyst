import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  OffthreadVideo,
  interpolate,
  staticFile,
} from "remotion";
import { C, FONT, ease } from "./theme";

// ---------------------------------------------------------------------------
// Fast-cut kinetic-typography primitives for CirviaMotion. Deliberately NOT
// the slow ease-out-quint rise/mask language in theme.ts/components.tsx —
// this is a punchy, hard-cut edit (snap in, hold, hard cut), Wealthsimple-ad
// pace rather than the "measured, precise" 50s narrative's editorial pace.
// The one exception (BeatMostAppsDont in motionScenes.tsx) borrows the old
// slow `rise` on purpose, as a deliberate pacing joke.
// ---------------------------------------------------------------------------

const PUNCH = Easing.out(Easing.back(1.7));

/** 0->1 fast snap-in with a slight overshoot, for kinetic type. */
export const punch = (frame: number, start: number, dur = 12): number =>
  interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: PUNCH,
  });

export const Center: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill
    style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: "0 72px",
      textAlign: "center",
    }}
  >
    {children}
  </AbsoluteFill>
);

/** Bold full-line kinetic type: fast scale/opacity snap, no slow drift. */
export const PunchLine: React.FC<{
  frame: number;
  at: number;
  children: React.ReactNode;
  size?: number;
  color?: string;
  weight?: number;
}> = ({ frame, at, children, size = 84, color = C.ink, weight = 800 }) => {
  const t = punch(frame, at);
  return (
    <div
      style={{
        fontFamily: FONT,
        fontWeight: weight,
        fontSize: size,
        lineHeight: 1.08,
        letterSpacing: "-0.02em",
        color,
        opacity: t,
        transform: `scale(${interpolate(t, [0, 1], [0.82, 1])})`,
      }}
    >
      {children}
    </div>
  );
};

/** Word-by-word cascade, each word punching in on a fast stagger. */
export const PunchWords: React.FC<{
  frame: number;
  at: number;
  words: string[];
  stagger?: number;
  size?: number;
  color?: string;
}> = ({ frame, at, words, stagger = 7, size = 64, color = C.ink }) => (
  <div
    style={{
      fontFamily: FONT,
      fontWeight: 800,
      fontSize: size,
      lineHeight: 1.18,
      letterSpacing: "-0.02em",
      color,
      display: "flex",
      flexWrap: "wrap",
      justifyContent: "center",
      gap: "0 0.32em",
    }}
  >
    {words.map((w, i) => {
      const t = punch(frame, at + i * stagger);
      return (
        <span
          key={i}
          style={{
            display: "inline-block",
            opacity: t,
            transform: `translateY(${(1 - t) * 16}px) scale(${interpolate(t, [0, 1], [0.85, 1])})`,
          }}
        >
          {w}
        </span>
      );
    })}
  </div>
);

/** Huge stat number, snaps in slightly bigger than its resting scale for punch. */
export const StatNumber: React.FC<{ frame: number; at: number; children: React.ReactNode }> = ({
  frame,
  at,
  children,
}) => {
  const t = punch(frame, at, 14);
  return (
    <div
      style={{
        fontFamily: FONT,
        fontWeight: 800,
        fontSize: 168,
        lineHeight: 1,
        letterSpacing: "-0.03em",
        color: C.accentText,
        opacity: t,
        transform: `scale(${interpolate(t, [0, 1], [1.35, 1])})`,
      }}
    >
      {children}
    </div>
  );
};

/** Small persistent disclaimer line, fades in and stays (compliance: must be
 * visible wherever performance stats are shown). */
export const Disclaimer: React.FC<{ frame: number; at: number; children: React.ReactNode }> = ({
  frame,
  at,
  children,
}) => (
  <div
    style={{
      position: "absolute",
      bottom: "6%",
      left: 0,
      right: 0,
      textAlign: "center",
      fontFamily: FONT,
      fontSize: 20,
      color: C.ink3,
      opacity: interpolate(frame, [at, at + 12], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
    }}
  >
    {children}
  </div>
);

/**
 * Realistic phone silhouette (dark bezel, dynamic-island notch, light
 * lock-screen-style gradient matching the real app's current theme) that
 * real product screenshots slide onto like live notifications. See
 * NotificationSlide below.
 */
export const PhoneFrame: React.FC<{ children: React.ReactNode; width?: number }> = ({
  children,
  width = 420,
}) => {
  const height = width * 2.06;
  return (
    <div
      style={{
        width,
        height,
        borderRadius: width * 0.135,
        background: "#0b0b0f",
        padding: width * 0.03,
        boxShadow: "0 50px 120px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.05) inset",
        position: "relative",
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          borderRadius: width * 0.11,
          background: "linear-gradient(165deg, #ece9f5 0%, #f6f1fb 45%, #efe1f7 100%)",
          overflow: "hidden",
          position: "relative",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: width * 0.04,
            left: "50%",
            transform: "translateX(-50%)",
            width: width * 0.28,
            height: width * 0.075,
            borderRadius: width * 0.05,
            background: "#0b0b0f",
            zIndex: 5,
          }}
        />
        {children}
      </div>
    </div>
  );
};

/**
 * A real cropped product screenshot (see ad/README.md for how these were
 * captured — Playwright against the live site, not recreated mockups)
 * sliding onto the phone screen like an actual notification: punch-in from
 * above, settle, and — if `outAt` is given — drift up and fade as the next
 * one arrives. Deliberately slower than the kinetic-type punch (`dur` 16 vs
 * 9) since a real screenshot needs a beat longer to register as "real."
 */
export const NotificationSlide: React.FC<{
  frame: number;
  inAt: number;
  outAt?: number;
  file: string;
  top: number;
  width: number;
}> = ({ frame, inAt, outAt, file, top, width }) => {
  const inT = punch(frame, inAt, 16);
  const y = interpolate(inT, [0, 1], [-width * 0.9, top]);
  const outT = outAt !== undefined ? ease(frame, outAt, 14) : 0;
  const opacity = inT * (1 - outT);
  const exitY = outT * -30;
  return (
    <div
      style={{
        position: "absolute",
        top: y + exitY,
        left: "50%",
        transform: "translateX(-50%)",
        width,
        opacity,
        zIndex: 10,
        borderRadius: width * 0.075,
        overflow: "hidden",
        boxShadow: "0 24px 60px rgba(20,10,40,0.28)",
      }}
    >
      <Img src={staticFile(file)} style={{ width: "100%", display: "block" }} />
    </div>
  );
};

/**
 * Fills the phone's screen with a real full-page screenshot (the screener
 * table, the pricing card) rather than sliding it in as a small
 * notification — this is "looking at the app screen," not "a notification
 * arrived," so it gets a gentle fade/scale instead of NotificationSlide's
 * punch-in drop.
 */
export const PhoneScreenFill: React.FC<{ frame: number; at: number; file: string }> = ({
  frame,
  at,
  file,
}) => {
  const t = ease(frame, at, 18);
  return (
    <div
      style={{
        // top offset clears PhoneFrame's dynamic-island notch (~width*0.115
        // at the 410px width this composition uses) so real screenshot text
        // never sits under it — a straight inset:0 let a notification's
        // notch overlap live text on the first pass of this beat.
        position: "absolute",
        top: 56,
        left: 0,
        right: 0,
        bottom: 0,
        opacity: t,
        transform: `scale(${interpolate(t, [0, 1], [1.04, 1])})`,
      }}
    >
      <Img
        src={staticFile(file)}
        style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top" }}
      />
    </div>
  );
};

/** Full-bleed B-roll layer: crop-to-cover, adjustable playback rate/crop for
 * reusing the same three source clips across multiple beats without them
 * reading as identical. Always muted (VO/music are the only audio, and
 * there's neither yet in CirviaMotion). */
export const Broll: React.FC<{
  file: string;
  startFrom?: number;
  playbackRate?: number;
  scrim?: number;
  mirror?: boolean;
}> = ({ file, startFrom = 0, playbackRate = 1, scrim = 0.35, mirror = false }) => (
  <AbsoluteFill>
    <OffthreadVideo
      src={staticFile(file)}
      muted
      startFrom={startFrom}
      playbackRate={playbackRate}
      style={{
        width: "100%",
        height: "100%",
        objectFit: "cover",
        transform: mirror ? "scaleX(-1)" : undefined,
      }}
    />
    <AbsoluteFill style={{ background: `rgba(8,6,12,${scrim})` }} />
  </AbsoluteFill>
);
