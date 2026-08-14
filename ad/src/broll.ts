// ---------------------------------------------------------------------------
// B-roll shot metadata — atmosphere/connective-tissue only. These never
// appear in Scenes 2–5 (the pixel-accurate product mockups); Shot A backs
// Scene1's cold open, Shot B bridges the Scene5→Scene6 cut, Shot C sits
// behind Scene7's existing code-driven glow. See ad/README.md for the
// generation prompts used for each.
// ---------------------------------------------------------------------------

export const SHOT_A_COLDOPEN = "video/shot-a-coldopen.mp4";
export const SHOT_B_TRANSITION = "video/shot-b-transition.mp4";
export const SHOT_C_ENDCARD_LOOP = "video/shot-c-endcard-loop.mp4";

/** Full-bleed background behind Scene1's lock-screen panel + headline. */
export const SHOT_A = {
  file: SHOT_A_COLDOPEN,
  /** dark scrim between the video and foreground text, for legibility */
  scrimColor: "rgba(8,6,12,0.55)",
};

/** Shared transition motif spanning the Scene5→Scene6 cut. Mounted twice —
 * once in Scene5's SceneFade `outDur` window, once in Scene6's `inDur`
 * window — with matching `startFrom` offsets so the motion reads as one
 * continuous move across the hard cut. */
export const SHOT_B = {
  file: SHOT_B_TRANSITION,
  /** frame offset into the source clip to start Scene5's half at */
  outStartFrom: 0,
  /** frame offset into the source clip to start Scene6's half at (picks up
   * where Scene5's slice left off) */
  inStartFrom: 10,
};

/** Looping ambient layer behind Scene7's existing radial-gradient glow. */
export const SHOT_C = {
  file: SHOT_C_ENDCARD_LOOP,
  opacity: 0.5,
  blendMode: "screen" as const,
};
