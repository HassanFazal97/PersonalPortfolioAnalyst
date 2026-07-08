import { Easing, interpolate } from "remotion";
import { loadFont } from "@remotion/google-fonts/SchibstedGrotesk";

const { fontFamily } = loadFont("normal", {
  weights: ["400", "500", "600", "700", "800"],
});

export const FONT = `${fontFamily}, sans-serif`;

// Brand tokens, hex conversions of the site's OKLCH custom properties
export const C = {
  bg: "#08060c",
  surface1: "#100e15",
  surface2: "#17141d",
  line: "#28252e",
  ink: "#eceaf0",
  ink2: "#bcb8c6",
  ink3: "#948f9f",
  accent: "#683eb6",
  accentHover: "#7c54cd",
  accentText: "#b7a1f5",
  gain: "#65c98c",
  loss: "#f07f77",
  warn: "#deb866",
  silkHi: "#b599ff",
} as const;

// ease-out quint family, same curve as the website (cubic-bezier(0.22,1,0.36,1))
export const EASE = Easing.bezier(0.22, 1, 0.36, 1);

/** 0→1 progress between start and start+dur frames, quint-eased, clamped. */
export const ease = (frame: number, start: number, dur = 18): number =>
  interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE,
  });

/** Fade + small rise, the site's standard reveal. */
export const rise = (
  frame: number,
  start: number,
  dur = 18,
  dist = 14,
): React.CSSProperties => {
  const t = ease(frame, start, dur);
  return { opacity: t, transform: `translateY(${(1 - t) * dist}px)` };
};

export const DIGEST_ROWS = [
  { t: "VFV", n: "S&P 500 ETF", c: "+0.8%", gain: true },
  { t: "NVDA", n: "NVIDIA", c: "+2.1%", gain: true },
  { t: "ENB", n: "Enbridge", c: "−1.2%", gain: false },
] as const;
