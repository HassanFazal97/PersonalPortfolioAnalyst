import React from "react";
import { Composition, Series } from "remotion";
import { Scene1, Scene2, Scene3, Scene4, Scene5, Scene6, Scene7 } from "./scenes";

const FPS = 30;

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

export const Root: React.FC = () => (
  <>
    <Composition
      id="CirviaAd"
      component={() => <Sequence scenes={MASTER} />}
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
  </>
);
