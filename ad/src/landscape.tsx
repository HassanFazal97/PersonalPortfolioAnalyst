import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, EASE, FONT, ease } from "./theme";

// ---------------------------------------------------------------------------
// CirviaWalkthrough (landscape) primitives — a real browser-chrome frame
// around a real screenshot, with continuous slow pan/zoom (never a static
// hold) and a text column that's actually populated with content instead
// of sitting on empty background. See ad/README.md for the full rationale.
// ---------------------------------------------------------------------------

/** A browser-window frame: dot cluster + URL pill, real screenshot inside,
 * cropped to whatever aspect the layout gives it. */
export const BrowserChrome: React.FC<{ url: string; children: React.ReactNode }> = ({
  url,
  children,
}) => (
  <div
    style={{
      width: "100%",
      height: "100%",
      borderRadius: 16,
      overflow: "hidden",
      background: C.surface1,
      border: `1px solid ${C.line}`,
      boxShadow: "0 60px 140px rgba(0,0,0,0.55)",
      display: "flex",
      flexDirection: "column",
    }}
  >
    <div
      style={{
        height: 44,
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "0 16px",
        borderBottom: `1px solid ${C.line}`,
        background: C.surface1,
      }}
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{ width: 9, height: 9, borderRadius: 99, background: C.line }}
        />
      ))}
      <div
        style={{
          marginLeft: 10,
          fontSize: 13,
          fontWeight: 500,
          color: C.ink3,
          background: C.bg,
          border: `1px solid ${C.line}`,
          borderRadius: 7,
          padding: "4px 12px",
        }}
      >
        {url}
      </div>
    </div>
    <div style={{ position: "relative", flex: 1, overflow: "hidden", background: "#f6f1fb" }}>
      {children}
    </div>
  </div>
);

/** Slow, continuous pan+zoom across a real screenshot — the "never static"
 * requirement. Scales in gently and drifts downward over the full beat
 * duration so there's always motion, never a frozen frame. */
export const KenBurnsImage: React.FC<{ file: string; dur: number; fromTop?: boolean }> = ({
  file,
  dur,
  fromTop = true,
}) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [0, dur], [0, 1], { extrapolateRight: "clamp" });
  const scale = interpolate(t, [0, 1], [1.08, 1.22]);
  const panY = interpolate(t, [0, 1], [0, fromTop ? -6 : 6]);
  return (
    <Img
      src={staticFile(file)}
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        transform: `scale(${scale}) translateY(${panY}%)`,
        transformOrigin: "top center",
      }}
    />
  );
};

/** Eyebrow + title + description text column. */
export const TextColumn: React.FC<{
  frame: number;
  eyebrow: string;
  title: string;
  description: string;
  index: number;
  total: number;
}> = ({ frame, eyebrow, title, description, index, total }) => {
  const t = ease(frame, 8, 22);
  return (
    <div
      style={{
        opacity: t,
        transform: `translateY(${(1 - t) * 22}px)`,
        display: "flex",
        flexDirection: "column",
        gap: 18,
      }}
    >
      <div
        style={{
          display: "inline-flex",
          alignSelf: "flex-start",
          alignItems: "center",
          gap: 8,
          fontSize: 14,
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: C.accentText,
          border: `1px solid ${C.line}`,
          borderRadius: 999,
          padding: "6px 14px",
        }}
      >
        {eyebrow}
      </div>
      <div
        style={{
          fontFamily: FONT,
          fontWeight: 800,
          fontSize: 46,
          lineHeight: 1.12,
          letterSpacing: "-0.02em",
          color: C.ink,
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: 20, lineHeight: 1.55, color: C.ink2, maxWidth: 440 }}>
        {description}
      </div>
      <div style={{ height: 8 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 28, height: 2, background: C.accent }} />
        <div style={{ fontSize: 13, color: C.ink3, fontVariantNumeric: "tabular-nums" }}>
          {String(index).padStart(2, "0")} / {String(total).padStart(2, "0")}
        </div>
      </div>
    </div>
  );
};

/**
 * Full split-screen beat: text column on one side, a browser-chrome
 * screenshot (with continuous Ken Burns motion) filling the other,
 * bleeding to that edge of the frame. Alternates sides by `index` so eight
 * beats in a row don't feel like the same template repeating.
 */
export const SplitScene: React.FC<{
  dur: number;
  url: string;
  file: string;
  eyebrow: string;
  title: string;
  description: string;
  index: number;
  total: number;
}> = ({ dur, url, file, eyebrow, title, description, index, total }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const textOnLeft = index % 2 === 1;
  const visualT = ease(frame, 4, 26);
  const visualX = interpolate(visualT, [0, 1], [textOnLeft ? 60 : -60, 0]);

  const textCol = (
    <div
      style={{
        width: width * 0.36,
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        padding: "0 64px",
      }}
    >
      <TextColumn
        frame={frame}
        eyebrow={eyebrow}
        title={title}
        description={description}
        index={index}
        total={total}
      />
    </div>
  );

  const visualCol = (
    <div
      style={{
        flex: 1,
        position: "relative",
        opacity: visualT,
        transform: `translateX(${visualX}px)`,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: -height * 0.06,
          bottom: -height * 0.06,
          left: textOnLeft ? 0 : 48,
          right: textOnLeft ? 48 : 0,
        }}
      >
        <BrowserChrome url={url}>
          <KenBurnsImage file={file} dur={dur} fromTop={index % 2 === 0} />
        </BrowserChrome>
      </div>
    </div>
  );

  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <AbsoluteFill
        style={{
          backgroundImage: `radial-gradient(50% 55% at ${textOnLeft ? 85 : 15}% 50%, rgba(104,62,182,0.22), transparent 70%)`,
        }}
      />
      <AbsoluteFill style={{ flexDirection: "row", display: "flex" }}>
        {textOnLeft ? (
          <>
            {textCol}
            {visualCol}
          </>
        ) : (
          <>
            {visualCol}
            {textCol}
          </>
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
