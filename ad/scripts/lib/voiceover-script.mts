// Narration copy as structured data — edit wording here, not in the
// imperative generation script. SSML <break> tags give the two-beat
// Scene3/Scene7 lines a natural pause without needing separate mp3 files.
//
// Delivery target: ~2.3 words/sec, measured and unhurried (not a typical
// ad-read pace) — see ELEVENLABS_VOICE_SETTINGS below for the performance
// knobs that aim for "calm, precise, nocturnal" rather than energetic.

export type VoScriptLine = { scene: 1 | 2 | 3 | 4 | 5 | 6 | 7; ssml: string };

export const VO_SCRIPT: VoScriptLine[] = [
  { scene: 1, ssml: "Know what matters before the market opens." },
  { scene: 2, ssml: "A brief for your holdings. Not the whole market." },
  {
    // Trimmed from the original two-sentence version: at this voice's
    // actual speaking pace the full line ran 10.8s against an 8s scene
    // budget. The dropped second sentence duplicates Scene3's on-screen
    // caption verbatim, so nothing is lost — see plan/README.
    scene: 3,
    ssml: "A hyperscaler flagged slower AI spending — it touches Broadcom and Micron.",
  },
  {
    scene: 4,
    ssml: "Chip demand concerns pulled AVGO lower. Broadcom is your third holding.",
  },
  { scene: 5, ssml: "Delivered where you already are. Text, email, Discord, web." },
  {
    scene: 6,
    ssml: "Read-only. Cirvia can never trade. Your password stays with your bank.",
  },
  {
    scene: 7,
    ssml:
      'Know your portfolio by 7:45.<break time="0.4s"/>Not financial advice. Read-only access.',
  },
];

// Scene budget in frames @ 30fps — mirrors ad/src/Root.tsx's MASTER array.
export const SCENE_DUR_FRAMES: Record<VoScriptLine["scene"], number> = {
  1: 180,
  2: 240,
  3: 240,
  4: 240,
  5: 240,
  6: 180,
  7: 180,
};

// Starting-point performance settings for "calm, measured, not hypey" —
// audition against real ElevenLabs voice candidates before trusting these.
export const ELEVENLABS_VOICE_SETTINGS = {
  stability: 0.7,
  similarity_boost: 0.75,
  style: 0.1,
  use_speaker_boost: true,
};
