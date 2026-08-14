// Conforms raw generated/downloaded B-roll clips (whatever fps/codec/
// resolution Higgsfield or ElevenLabs handed back) to a consistent
// 1920x1080 h.264 mp4 @ 30fps, and drops them at the exact paths
// src/broll.ts expects. Requires ffmpeg/ffprobe on PATH (`brew install
// ffmpeg`).
//
// Usage: npm run broll:conform -- <raw-shot-a> <raw-shot-b> <raw-shot-c>
// (any argument can be omitted/skipped with "-" if that shot isn't ready yet)

import { execFile } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(__dirname, "..", "public", "video");

// minSeconds: pad/loop the source (via ffmpeg -stream_loop) so the output
// file is always at least as long as the scene it backs — Remotion's
// OffthreadVideo doesn't loop on its own, so this is where "seamless loop"
// actually gets guaranteed, not at render time. Scene1/Scene7 are 6s (180f
// @30fps); a couple seconds of handle avoids a hard stop right at the cut.
const TARGETS = [
  { arg: 0, out: "shot-a-coldopen.mp4", minSeconds: 8 },
  { arg: 1, out: "shot-b-transition.mp4", minSeconds: undefined },
  { arg: 2, out: "shot-c-endcard-loop.mp4", minSeconds: 8 },
];

async function conform(rawPath: string, outName: string, minSeconds: number | undefined) {
  const outPath = path.join(OUT_DIR, outName);
  console.log(`Conforming ${rawPath} -> public/video/${outName}`);
  const args = [
    "-y",
    ...(minSeconds ? ["-stream_loop", "-1"] : []),
    "-i",
    rawPath,
    "-vf",
    "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30",
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-an", // strip any source audio — B-roll is always muted in Remotion anyway
    ...(minSeconds ? ["-t", String(minSeconds)] : []),
    outPath,
  ];
  await run("ffmpeg", args);
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.error(
      "Usage: npm run broll:conform -- <raw-shot-a> <raw-shot-b> <raw-shot-c> (use \"-\" to skip one)",
    );
    process.exit(1);
  }
  for (const { arg, out, minSeconds } of TARGETS) {
    const rawPath = args[arg];
    if (!rawPath || rawPath === "-") {
      console.log(`Skipping ${out} (no source given)`);
      continue;
    }
    await conform(rawPath, out, minSeconds);
  }
  console.log("Done. Re-run `npm run studio` to preview with the conformed clips.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
