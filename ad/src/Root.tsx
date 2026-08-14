import React from "react";
import { Audio, Composition, Series, staticFile } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { DemoChat, DemoConnect, DemoHook, DemoPricing, DemoStock } from "./demo";
import { Scene1, Scene2, Scene3, Scene4, Scene5, Scene6, Scene7 } from "./scenes";
import { MUSIC_BED_FILE, duckedMusicVolume } from "./audio";
import {
  BeatChat,
  BeatConnect,
  BeatDigest,
  BeatFrozenEntry,
  BeatMacroAlert,
  BeatPricing,
  BeatReadOnly,
  BeatScreener,
  BeatStatAvgReturn,
  BeatStatBeatRate,
  BeatVerified,
  ColdOpen,
  MotionEndCard,
} from "./motionScenes";
import {
  SceneChat,
  SceneDigest,
  SceneEndCard,
  SceneHero,
  ScenePricing,
  SceneReadOnly,
  SceneScreener,
  SceneTrackRecord,
} from "./landscapeScenes";

const FPS = 30;

const Scene7WithUrl: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene7 dur={dur} showUrl />
);

// Product demo, 16:9 — hook → connect → dashboard → macro alert → chat →
// channel fan-out → stock deep-dive → pricing/trial → end card
const DEMO: Array<[React.FC<{ dur: number }>, number]> = [
  [DemoHook, 180],
  [DemoConnect, 300],
  [Scene2, 240],
  [Scene3, 240],
  [DemoChat, 330],
  [Scene5, 240],
  [DemoStock, 240],
  [DemoPricing, 240],
  [Scene7WithUrl, 210],
];

// 16:9 master, 50s
const MASTER: Array<[React.FC<{ dur: number }>, number]> = [
  [Scene1, 180],
  [Scene2, 240],
  [Scene3, 240],
  [Scene4, 240],
  [Scene5, 240],
  [Scene6, 180],
  [Scene7, 180],
];

// Cutdowns reuse the cold open, the channel fan-out, and the end card
const VERTICAL: Array<[React.FC<{ dur: number }>, number]> = [
  [Scene1, 180],
  [Scene5, 240],
  [Scene7, 180],
];

const SQUARE: Array<[React.FC<{ dur: number }>, number]> = [
  [Scene1, 150],
  [Scene5, 150],
  [Scene7, 150],
];

// CirviaMotion — full feature walkthrough (v3), using real screenshots
// from the live site instead of recreated UI mockups (see
// src/motionScenes.tsx for what changed and why across all three
// rebuilds). 1180f @ 30fps = 39.3s.
const MOTION: Array<[React.FC<{ dur: number }>, number]> = [
  [ColdOpen, 50],
  [BeatConnect, 80],
  [BeatDigest, 100],
  [BeatMacroAlert, 100],
  [BeatChat, 100],
  [BeatScreener, 110],
  [BeatVerified, 100],
  [BeatFrozenEntry, 70],
  [BeatStatBeatRate, 75],
  [BeatStatAvgReturn, 65],
  [BeatReadOnly, 85],
  [BeatPricing, 115],
  [MotionEndCard, 130],
];

// CirviaWalkthrough — landscape (1920x1080) feature walkthrough, replacing
// CirviaMotion (vertical, phone-frame) entirely per feedback that it needed
// to (a) be landscape, (b) drop the phone-screen gimmick, (c) crossfade
// smoothly between beats instead of hard-cutting, and (d) never sit on
// empty background — see src/landscapeScenes.tsx for the real-screenshot
// rationale. TRANSITION_FRAMES of crossfade is carved out of, not added to,
// the total runtime (TransitionSeries overlaps adjacent sequences).
const TRANSITION_FRAMES = 18;

const WALKTHROUGH: Array<[React.FC<{ dur: number }>, number]> = [
  [SceneHero, 150],
  [SceneDigest, 140],
  [SceneChat, 140],
  [SceneScreener, 145],
  [SceneTrackRecord, 155],
  [SceneReadOnly, 130],
  [ScenePricing, 150],
  [SceneEndCard, 140],
];

const WalkthroughComposition: React.FC = () => (
  <TransitionSeries>
    {WALKTHROUGH.map(([Scene, dur], i) => (
      <React.Fragment key={i}>
        <TransitionSeries.Sequence durationInFrames={dur}>
          <Scene dur={dur} />
        </TransitionSeries.Sequence>
        {i < WALKTHROUGH.length - 1 && (
          <TransitionSeries.Transition
            presentation={fade()}
            timing={linearTiming({ durationInFrames: TRANSITION_FRAMES })}
          />
        )}
      </React.Fragment>
    ))}
  </TransitionSeries>
);

const Sequence: React.FC<{ scenes: Array<[React.FC<{ dur: number }>, number]> }> = ({
  scenes,
}) => (
  <Series>
    {scenes.map(([Scene, dur], i) => (
      <Series.Sequence key={i} durationInFrames={dur}>
        <Scene dur={dur} />
      </Series.Sequence>
    ))}
  </Series>
);

const total = (scenes: Array<[React.FC<{ dur: number }>, number]>) =>
  scenes.reduce((sum, [, d]) => sum + d, 0);

const walkthroughTotal = total(WALKTHROUGH) - (WALKTHROUGH.length - 1) * TRANSITION_FRAMES;

// CirviaAd only: continuous music bed spans the whole composition as a
// sibling of <Sequence>, not nested per-scene (per-scene VO lives inside
// each Scene component itself — see src/scenes.tsx's SceneVO).
const CirviaAdComposition: React.FC = () => (
  <>
    <Audio src={staticFile(MUSIC_BED_FILE)} volume={duckedMusicVolume} />
    <Sequence scenes={MASTER} />
  </>
);

export const Root: React.FC = () => (
  <>
    <Composition
      id="CirviaDemo"
      component={() => <Sequence scenes={DEMO} />}
      durationInFrames={total(DEMO)}
      fps={FPS}
      width={1920}
      height={1080}
    />
    <Composition
      id="CirviaAd"
      component={CirviaAdComposition}
      durationInFrames={total(MASTER)}
      fps={FPS}
      width={1920}
      height={1080}
    />
    <Composition
      id="CirviaAdVertical"
      component={() => <Sequence scenes={VERTICAL} />}
      durationInFrames={total(VERTICAL)}
      fps={FPS}
      width={1080}
      height={1920}
    />
    <Composition
      id="CirviaAdSquare"
      component={() => <Sequence scenes={SQUARE} />}
      durationInFrames={total(SQUARE)}
      fps={FPS}
      width={1080}
      height={1080}
    />
    <Composition
      id="CirviaMotion"
      component={() => <Sequence scenes={MOTION} />}
      durationInFrames={total(MOTION)}
      fps={FPS}
      width={1080}
      height={1920}
    />
    <Composition
      id="CirviaWalkthrough"
      component={WalkthroughComposition}
      durationInFrames={walkthroughTotal}
      fps={FPS}
      width={1920}
      height={1080}
    />
  </>
);
