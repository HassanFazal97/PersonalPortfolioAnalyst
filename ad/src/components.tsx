import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import { C, DIGEST_ROWS, EASE, FONT, ease, rise } from "./theme";

/** Page background: near-black violet with the site's soft top aurora tint. */
export const Screen: React.FC<{
  children: React.ReactNode;
  glow?: boolean;
}> = ({ children, glow = true }) => (
  <AbsoluteFill
    style={{
      backgroundColor: C.bg,
      fontFamily: FONT,
      color: C.ink2,
      backgroundImage: glow
        ? `radial-gradient(60% 40% at 50% -10%, rgba(104,62,182,0.28), transparent 70%)`
        : undefined,
    }}
  >
    {children}
  </AbsoluteFill>
);

/** Bottom-centered caption line. */
export const Caption: React.FC<{
  frame: number;
  at: number;
  children: React.ReactNode;
  size?: number;
}> = ({ frame, at, children, size = 34 }) => (
  <div
    style={{
      position: "absolute",
      bottom: "7%",
      left: 0,
      right: 0,
      textAlign: "center",
      fontSize: size,
      fontWeight: 500,
      color: C.ink2,
      ...rise(frame, at),
    }}
  >
    {children}
  </div>
);

/** Headline lines rising out of overflow-hidden masks, staggered. */
export const MaskedHeadline: React.FC<{
  frame: number;
  at: number;
  lines: string[];
  size: number;
  stagger?: number;
  color?: string;
}> = ({ frame, at, lines, size, stagger = 10, color = C.ink }) => (
  <div style={{ textAlign: "center" }}>
    {lines.map((line, i) => {
      const t = ease(frame, at + i * stagger, 24);
      return (
        <div key={line} style={{ overflow: "hidden" }}>
          <div
            style={{
              fontSize: size,
              fontWeight: 800,
              letterSpacing: "-0.03em",
              lineHeight: 1.12,
              color,
              transform: `translateY(${(1 - t) * 108}%)`,
            }}
          >
            {line}
          </div>
        </div>
      );
    })}
  </div>
);

export const panelStyle: React.CSSProperties = {
  background: C.surface1,
  border: `1px solid ${C.line}`,
  borderRadius: 12,
  boxShadow: "0 30px 70px rgba(0,0,0,0.5)",
};

const RowChg: React.FC<{ gain: boolean; children: React.ReactNode; size: number }> = ({
  gain,
  children,
  size,
}) => (
  <span
    style={{
      color: gain ? C.gain : C.loss,
      fontWeight: 600,
      fontSize: size,
      fontVariantNumeric: "tabular-nums",
      marginLeft: "auto",
    }}
  >
    {children}
  </span>
);

/**
 * The morning digest card. `s` scales the whole card; rows stagger in from
 * `rowsAt`; the dollar value ticks up between `tickAt` and `tickAt+40`.
 */
export const DigestCard: React.FC<{
  frame: number;
  width: number;
  s?: number;
  appearAt?: number;
  rowsAt?: number;
  tickAt?: number;
  showValue?: boolean;
}> = ({ frame, width, s = 1, appearAt = 0, rowsAt = 8, tickAt = 14, showValue = true }) => {
  const value = Math.round(
    interpolate(ease(frame, tickAt, 40), [0, 1], [47734, 48214]),
  ).toLocaleString("en-CA");
  return (
    <div
      style={{
        ...panelStyle,
        width,
        padding: 22 * s,
        fontSize: 17 * s,
        ...rise(frame, appearAt),
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10 * s,
          paddingBottom: 12 * s,
          borderBottom: `1px solid ${C.line}`,
          color: C.ink3,
          fontWeight: 600,
          fontSize: 15 * s,
        }}
      >
        <span
          style={{
            width: 8 * s,
            height: 8 * s,
            borderRadius: 99,
            background: C.accentText,
          }}
        />
        Morning digest
        <span style={{ marginLeft: "auto", fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>
          7:45 AM
        </span>
      </div>
      {showValue ? (
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 12 * s,
            padding: `${14 * s}px 0 ${6 * s}px`,
          }}
        >
          <span
            style={{
              fontSize: 27 * s,
              fontWeight: 800,
              color: C.ink,
              fontVariantNumeric: "tabular-nums",
              letterSpacing: "-0.01em",
            }}
          >
            ${value}
          </span>
          <span style={{ color: C.gain, fontWeight: 600, fontSize: 15 * s }}>
            +1.2% today
          </span>
        </div>
      ) : (
        <div style={{ height: 8 * s }} />
      )}
      {DIGEST_ROWS.map((r, i) => (
        <div
          key={r.t}
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 12 * s,
            padding: `${10 * s}px 0`,
            borderBottom: i < DIGEST_ROWS.length - 1 ? `1px solid ${C.line}` : "none",
            ...rise(frame, rowsAt + i * 5, 14, 10),
          }}
        >
          <span style={{ fontWeight: 700, color: C.ink, width: 62 * s }}>{r.t}</span>
          <span style={{ color: C.ink3, fontSize: 15 * s }}>{r.n}</span>
          <RowChg gain={r.gain} size={15 * s}>
            {r.c}
          </RowChg>
        </div>
      ))}
    </div>
  );
};

/** Minimal browser chrome around content. */
export const BrowserFrame: React.FC<{
  width: number;
  height: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
  url?: string;
}> = ({ width, height, children, style, url = "cirvia.app/dashboard" }) => (
  <div style={{ ...panelStyle, width, height, overflow: "hidden", ...style }}>
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "14px 18px",
        borderBottom: `1px solid ${C.line}`,
      }}
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{ width: 11, height: 11, borderRadius: 99, background: C.line }}
        />
      ))}
      <span
        style={{
          margin: "0 auto",
          background: C.surface2,
          borderRadius: 8,
          padding: "5px 22px",
          fontSize: 14,
          color: C.ink3,
        }}
      >
        {url}
      </span>
      <span style={{ width: 55 }} />
    </div>
    <div style={{ position: "relative", height: height - 54 }}>{children}</div>
  </div>
);

export const ChatBubble: React.FC<{
  user?: boolean;
  children: React.ReactNode;
  style?: React.CSSProperties;
  size?: number;
}> = ({ user, children, style, size = 19 }) => (
  <div
    style={{
      padding: "13px 18px",
      borderRadius: 12,
      fontSize: size,
      lineHeight: 1.5,
      maxWidth: "88%",
      width: "fit-content",
      background: user ? C.surface2 : "rgba(104,62,182,0.22)",
      color: user ? C.ink : C.ink2,
      marginLeft: user ? "auto" : 0,
      ...style,
    }}
  >
    {children}
  </div>
);

/** Three-dot typing indicator; dots pulse on a 24-frame cycle. */
export const TypingDots: React.FC<{ frame: number; style?: React.CSSProperties }> = ({
  frame,
  style,
}) => (
  <div
    style={{
      display: "inline-flex",
      gap: 7,
      padding: "17px 18px",
      borderRadius: 12,
      background: "rgba(104,62,182,0.22)",
      ...style,
    }}
  >
    {[0, 1, 2].map((i) => {
      const p = ((frame - i * 5) % 24) / 24;
      const lift = Math.sin(Math.max(0, Math.min(1, p)) * Math.PI);
      return (
        <span
          key={i}
          style={{
            width: 8,
            height: 8,
            borderRadius: 99,
            background: C.ink3,
            opacity: 0.4 + 0.6 * lift,
            transform: `translateY(${-4 * lift}px)`,
          }}
        />
      );
    })}
  </div>
);

export const Logo: React.FC<{ size?: number }> = ({ size = 44 }) => (
  <span style={{ fontSize: size, fontWeight: 800, letterSpacing: "-0.03em", color: C.ink }}>
    Cir<span style={{ color: C.accentText }}>via</span>
  </span>
);

export const PillButton: React.FC<{ children: React.ReactNode; size?: number }> = ({
  children,
  size = 24,
}) => (
  <span
    style={{
      display: "inline-block",
      background: C.accent,
      color: "#fff",
      fontWeight: 600,
      fontSize: size,
      borderRadius: 999,
      padding: `${size * 0.62}px ${size * 1.5}px`,
    }}
  >
    {children}
  </span>
);

/** Fades a scene in/out at its edges so cuts stay calm. */
export const SceneFade: React.FC<{
  frame: number;
  duration: number;
  children: React.ReactNode;
  inDur?: number;
  outDur?: number;
}> = ({ frame, duration, children, inDur = 8, outDur = 10 }) => {
  const opacity =
    interpolate(frame, [0, inDur], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }) *
    interpolate(frame, [duration - outDur, duration - 1], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: EASE,
    });
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};
