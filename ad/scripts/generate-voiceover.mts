// Generates the 7 scene VO mp3s from ElevenLabs TTS, measures each file's
// actual duration, and prints a fit table against each scene's frame budget.
//
// Requires ad/.env with ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID set
// (see ad/.env.example). Run with: npm run voiceover:generate
//
// This does NOT auto-update ad/src/audio.ts's VO_CUES.durFrames — after
// reviewing the fit table below, update those values by hand to match what
// was actually measured, and re-run `npm run studio` to confirm the sync.

import "dotenv/config";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseBuffer } from "music-metadata";
import { ELEVENLABS_VOICE_SETTINGS, SCENE_DUR_FRAMES, VO_SCRIPT } from "./lib/voiceover-script.mts";
import { VO_CUES } from "../src/audio.ts";

const FPS = 30;
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(__dirname, "..", "public", "audio");

async function main() {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  const voiceId = process.env.ELEVENLABS_VOICE_ID;
  if (!apiKey || !voiceId) {
    console.error(
      "Missing ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID — copy ad/.env.example to ad/.env and fill both in.",
    );
    process.exit(1);
  }

  await mkdir(OUT_DIR, { recursive: true });

  const rows: { scene: number; measuredSec: number; measuredFrames: number; budgetFrames: number; fits: boolean }[] =
    [];

  for (const line of VO_SCRIPT) {
    const cue = VO_CUES.find((c) => c.scene === line.scene);
    const budgetFrames = SCENE_DUR_FRAMES[line.scene] - (cue?.voStart ?? 0);

    console.log(`Scene ${line.scene}: requesting TTS…`);
    // Confirm this endpoint/model_id/voice_settings shape against ElevenLabs'
    // current docs at execution time — this is the historically stable
    // text-to-speech surface, but model naming shifts over time.
    const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`, {
      method: "POST",
      headers: {
        "xi-api-key": apiKey,
        "Content-Type": "application/json",
        Accept: "audio/mpeg",
      },
      body: JSON.stringify({
        text: line.ssml,
        model_id: "eleven_multilingual_v2",
        voice_settings: ELEVENLABS_VOICE_SETTINGS,
      }),
    });

    if (!res.ok) {
      throw new Error(`Scene ${line.scene} TTS request failed: ${res.status} ${await res.text()}`);
    }

    const buf = Buffer.from(await res.arrayBuffer());
    const outPath = path.join(OUT_DIR, `scene${line.scene}-vo.mp3`);
    await writeFile(outPath, buf);

    const meta = await parseBuffer(buf, "audio/mpeg");
    const measuredSec = meta.format.duration ?? 0;
    const measuredFrames = Math.round(measuredSec * FPS);

    rows.push({
      scene: line.scene,
      measuredSec: Number(measuredSec.toFixed(2)),
      measuredFrames,
      budgetFrames,
      fits: measuredFrames <= budgetFrames,
    });
  }

  console.log("\nscene | measured sec | measured frames | budget frames | fits?");
  let anyOverrun = false;
  for (const r of rows) {
    if (!r.fits) anyOverrun = true;
    console.log(
      `${r.scene}     | ${r.measuredSec.toString().padEnd(13)} | ${r.measuredFrames
        .toString()
        .padEnd(16)} | ${r.budgetFrames.toString().padEnd(13)} | ${r.fits ? "yes" : "NO — overrun"}`,
    );
  }

  if (anyOverrun) {
    console.warn(
      "\nOne or more lines overran their scene budget. Trim the wording, nudge that scene's " +
        "voStart earlier in src/audio.ts, or (last resort) extend the scene's duration in " +
        "Root.tsx's MASTER array — the last option cascades into the music envelope and the " +
        "Scene5/6 transition frame math, so treat it as a re-derivation, not a one-line tweak.",
    );
  } else {
    console.log("\nAll lines fit their scene budgets. Update VO_CUES.durFrames in src/audio.ts to the measured values above.");
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
