import { interpolate } from "remotion";
import { ease } from "./theme";

// ---------------------------------------------------------------------------
// Voiceover cues — one mp3 per CirviaAd scene, scene-local start frame.
//
// `voStart` is a *target*, not a guarantee: real TTS output duration isn't
// fully predictable from word count. `scripts/generate-voiceover.ts` measures
// the actual rendered mp3 durations and prints a fit table; `durFrames` below
// should be updated to match those measured values (see that script's output)
// before the final render — until then these are estimates from the
// narration script (see plan / README), enough to preview timing in Studio.
// ---------------------------------------------------------------------------

export type VoCue = {
  scene: 1 | 2 | 3 | 4 | 5 | 6 | 7;
  file: string;
  voStart: number;
  /** estimated/measured duration in frames @ 30fps — refine after generation */
  durFrames: number;
};

// Measured from the actual generated mp3s (ffprobe, 30fps) — see
// ad/README.md for how these were produced. voStart=24 on Scene6 (not 12)
// is deliberate: Scene5's VO tail overruns its own scene by ~21f, so
// Scene6's line is pushed a few frames later to avoid the two voices
// overlapping across the cut.
export const VO_CUES: VoCue[] = [
  { scene: 1, file: "audio/scene1-vo.mp3", voStart: 18, durFrames: 86 },
  { scene: 2, file: "audio/scene2-vo.mp3", voStart: 58, durFrames: 90 },
  { scene: 3, file: "audio/scene3-vo.mp3", voStart: 16, durFrames: 185 },
  { scene: 4, file: "audio/scene4-vo.mp3", voStart: 84, durFrames: 168 },
  { scene: 5, file: "audio/scene5-vo.mp3", voStart: 100, durFrames: 161 },
  { scene: 6, file: "audio/scene6-vo.mp3", voStart: 24, durFrames: 161 },
  { scene: 7, file: "audio/scene7-vo.mp3", voStart: 22, durFrames: 155 },
];

// Cumulative scene-start offsets in the CirviaAd (MASTER) timeline —
// mirrors ad/src/Root.tsx's MASTER array (180, 240, 240, 240, 240, 180, 180).
const SCENE_OFFSETS: Record<VoCue["scene"], number> = {
  1: 0,
  2: 180,
  3: 420,
  4: 660,
  5: 900,
  6: 1140,
  7: 1320,
};

export const MUSIC_BED_FILE = "audio/music-bed.mp3";
export const MUSIC_BASE_VOLUME = 0.32;
export const MUSIC_DUCKED_VOLUME = 0.12;

const DUCK_TRANSITION_FRAMES = 15;

/** Each VO cue's [start, end) in the composition's global frame numbering. */
const duckWindows = VO_CUES.map((cue) => {
  const start = SCENE_OFFSETS[cue.scene] + cue.voStart;
  return { start, end: start + cue.durFrames };
});

/**
 * Music-bed volume envelope for the whole CirviaAd composition: ducks under
 * every VO passage with an eased in/out, full volume elsewhere.
 */
export const duckedMusicVolume = (frame: number): number => {
  let vol = MUSIC_BASE_VOLUME;
  for (const { start, end } of duckWindows) {
    if (frame < start - DUCK_TRANSITION_FRAMES || frame > end + DUCK_TRANSITION_FRAMES) {
      continue;
    }
    const duckIn = ease(frame, start - DUCK_TRANSITION_FRAMES, DUCK_TRANSITION_FRAMES);
    const duckOut = 1 - ease(frame, end, DUCK_TRANSITION_FRAMES);
    const t = Math.min(duckIn, duckOut);
    const windowVol = interpolate(t, [0, 1], [MUSIC_BASE_VOLUME, MUSIC_DUCKED_VOLUME]);
    vol = Math.min(vol, windowVol);
  }
  return vol;
};
