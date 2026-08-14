# Cirvia advert (Remotion)

Motion-design advert for Cirvia, rendered from React with [Remotion](https://remotion.dev).
Brand tokens are hex conversions of the site's OKLCH custom properties in
`app/landing.py`; the motion language matches the site (ease-out quint,
masked line rises, small fades).

## Compositions

| ID | Format | Length | Scenes |
|---|---|---|---|
| `CirviaWalkthrough` | 1920x1080 (16:9) | ~34s | **Current promo** — landscape feature walkthrough, real full-page screenshots of the live app in browser-chrome frames with continuous Ken Burns motion and crossfade transitions. See below. |
| `CirviaMotion` | 1080x1920 (9:16) | ~39s | Previous vertical cut — real screenshots of the live app as phone notifications + kinetic typography. Superseded as the promo by `CirviaWalkthrough` (landscape, no phone-frame gimmick, smoother transitions) but still a valid vertical/social cut if one's needed later — same real-screenshot approach, just a different presentation. |
| `CirviaAd` | 1920x1080 (16:9) | 50s | Old narrated dashboard/chat walkthrough (`Scene1`-`Scene7`). Superseded — its "morning digest by 7:45" hook predates the current positioning and its UI mockups predate the current app UI. Left in place for reference, not the one to ship. |
| `CirviaAdVertical` / `CirviaAdSquare` | 9:16 / 1:1 | 20s / 15s | Cutdowns of the old `CirviaAd` scenes — same caveat. |
| `CirviaDemo` | 1920x1080 (16:9) | 74s | Old onboarding-to-pricing walkthrough. Unrelated to the promo, untouched this round. |

### `CirviaWalkthrough` — the current promo (landscape)

Rebuilt again after feedback on `CirviaMotion` (below): make it landscape,
drop the phone-frame gimmick entirely, make the motion actually flow
instead of static holds, stop leaving most of the frame on flat background,
and keep every visual from the real live product.

**Structure**: 8 beats, split-screen layout — a populated text column
(eyebrow label, title, description, a progress indicator) on one side, a
`BrowserChrome`-framed real screenshot (`src/landscape.tsx`) bleeding to
the frame edge on the other. Sides alternate per beat (odd index = text
left, even = text right) so it doesn't read as one template repeating.
Every screenshot has continuous `KenBurnsImage` motion — a slow
scale+pan across the full beat duration — so nothing is ever a frozen
static frame. Beats crossfade into each other via `@remotion/transitions`'
`TransitionSeries` (18-frame `fade()`, carved out of the adjacent beats'
own duration, not added on top) instead of hard-cutting.

**Screenshots are real, captured desktop-width** (1600×1000 viewport, 2x
scale, animations disabled via injected CSS, same Playwright method as
`CirviaMotion`'s assets) — seven pages in `public/ui-land/`:

| Beat | Page captured | What's shown |
|---|---|---|
| Hero | `/` | Headline + all four hero notification cards in their real positions |
| Digest | `/sample-digest` | The full sample morning digest |
| Chat | `/` (scrolled to the chat section) | The dedicated "Ask about your investments" Q&A mockup — also happens to show the track-record stat strip above it, which the Ken Burns pan reveals |
| Screener | `/screener` | The real valuation table, live tickers and verdicts |
| Track record | `/track-record` | Full stat strip + the actual dated picks table |
| Read-only | `/` (scrolled to "Built read-only") | The real trust checklist |
| Pricing | `/pricing` | Free and Pro plans side by side, full feature list |

No feature is illustrated with a fabricated screenshot — same rule as
`CirviaMotion`. The end card is the exception to "no blank background": it
reuses `shot-c-endcard-loop.mp4`, the one piece of actual Higgsfield B-roll
from the original build, which is a real generated asset rather than a
flat color.

Regenerate any of the seven screenshots by re-running the same Playwright
capture against the live site if a page's copy or layout changes — see the
capture commands in this file's git history or reconstruct from
`src/landscapeScenes.tsx`'s beat list.

**Stats and copy** are the same live data as `CirviaMotion` (pulled
2026-08-13) — see that section below for the actual numbers and the
refresh note.

**Silent**, same reason as `CirviaMotion`: ElevenLabs MCP still has no
working API key.

### `CirviaMotion` — vertical cut (superseded as the promo)

Built from scratch, not a trim of the old scenes. Rebuilt across four
rounds of feedback, each one worth keeping in mind before touching this
again:
1. Don't reuse the old UI mockups or slow 50s pacing — use Higgsfield for
   real motion design like a fast fintech ad (e.g. Wealthsimple).
2. Don't lead with "morning digest by 7:45" — that's not the current pitch.
   `marketing.md` (reviewed 2026-07-30) has moved to **"the AI analyst that
   shows its work"**: frozen entry prices, published misses, adversarial
   fact-checking, benchmarked against the S&P 500.
3. Show *realistic* product moments (notifications popping up on a phone),
   built from real clips/frames of the actual app, not recreated
   approximations — and it had gotten too fast to register any of it.
4. It's not just a hook, it's a **feature walkthrough** — show what the
   app actually does, all of it, not only the proof/positioning angle.

**The app UI itself changed too, discovered mid-rebuild (round 3)**:
`PRODUCT.md` describes a near-black canvas, but the live site
(`www.cirvia.ca`) is now light-themed — soft lavender/white, dark ink text,
one purple accent. That's a real, current design decision (confirmed with
`prefers-color-scheme: dark` forced on, same result), not a rendering
fluke. `src/kinetic.tsx`'s `PhoneFrame` screen gradient matches it.

**UI assets are real screenshots, not recreated mockups.** Captured with
Playwright (`.venv/bin/playwright`, already installed in this repo) against
the live site on 2026-08-13, animations disabled via injected CSS so
elements would screenshot cleanly, then cropped with `ffmpeg` — see
`raw-ui/` for the capture output and `public/ui/` for what's actually used.
Six assets: `ui-macro-alert.png`, `ui-chat-question.png`,
`ui-digest-card.png`, `ui-verified.png` (all from the homepage hero, mobile
notification-card treatment via `NotificationSlide` — punch-in slide from
above, own drop-shadow rather than the screenshot's baked-in one, since an
earlier version left a visible seam where the crop's background didn't
match the phone screen gradient), plus `ui-screener.png` (`/screener`,
mobile viewport) and `ui-pricing.png` (`/pricing`'s Pro card, mobile
viewport) — both full real app screens rather than small cards, so they're
composited via `PhoneScreenFill` (fills the phone screen, gentle fade/scale
rather than a notification drop). `PhoneScreenFill` insets 56px from the
top specifically to clear `PhoneFrame`'s notch — an early pass let the
notch sit on top of live screenshot text near the crop's top edge, fixed
at the component level so it can't recur on a future re-crop.

**No feature is shown with a fabricated screenshot.** Deep Dives and Risk
Lab have no public sample page to capture honestly, so rather than invent
a mockup of either, they're covered by the real `/pricing` Pro-card
screenshot (which lists every Pro feature verbatim) plus a caption — real
content, not a guess at what those screens might look like.

Regenerate any of the six by re-running the same Playwright capture
against the live site and re-cropping if the source page's copy or layout
changes.

**Stats are live data, pulled from `www.cirvia.ca` on 2026-08-13 — refresh
`TRACK_RECORD` in `src/motionScenes.tsx` before reusing this cut, the site
updates daily as more picks are measured:**
- 100 Model Picks measured
- 67% beat the S&P 500 over the same span
- +5.39% average return per pick

Beat map (13 beats, 1180 frames @ 30fps = 39.4s):

| Beat | Frames | Copy | Visual |
|---|---|---|---|
| Cold open | 50 | "The AI analyst that shows its work." | none (black) |
| Connect | 80 | "Connect Wealthsimple, Questrade, and more. Read-only, in under three minutes." | none — no honest screenshot of the OAuth flow exists to capture |
| Digest | 100 | "Written from your real holdings, every weekday morning." | phone: digest notification |
| Macro alerts | 100 | "Alerts only when world events touch what you own." | phone: macro-alert notification |
| Chat | 100 | "Ask anything. Answers grounded in your actual positions." | phone: chat notification |
| Screener | 110 | "563 stocks. A cheap-or-expensive verdict for every one, against real peers." | phone: full screener screen |
| Verified | 100 | "An adversarial critic checks every claim before it ships." | phone: verified notification |
| Mechanism | 70 | "100 Model Picks. Frozen entry price. Nothing deleted." | none |
| Stat | 75 | **67%** / "beat the S&P 500, same span" | none — disclaimer visible |
| Stat | 65 | **+5.39%** / "average return per pick" | none — disclaimer visible |
| Read-only | 85 | "Read-only." / "We can never trade for you." / "Your brokerage password stays with your bank." | none |
| Pricing | 115 | "Free to start. Pro unlocks the rest, $20 a month." | phone: full Pro-card screen (lists every Pro feature) |
| End card | 130 | Logo, "The AI analyst that shows its work.", CTA "Get started free", cirvia.ca, full compliance footer | Shot C (silk loop, from the old Higgsfield B-roll) |

Only the end card still uses generated B-roll (`shot-c-endcard-loop.mp4`,
the standout of the three from the old cut) — everything else is either a
real screenshot or pure typography, so the Higgsfield-credit constraint
(11.5 of 110 left) hasn't mattered since round 2.

**Silent.** No music bed is wired up (ElevenLabs MCP still has no working
API key). A cut this content-dense benefits less from a driving beat than
a pure hook would, but a track would still help — the beat-by-beat frame
counts above would need re-timing to its actual tempo, not just dropped in
underneath.

Copy has no em dashes anywhere (`PRODUCT.md`: "No em dashes in copy") —
check that going forward if this gets edited.

## `CirviaAd`'s example scenario

The macro-alert beat (Scenes 1, 3, 4, 5) uses a hyperscaler-flags-slower-AI-spending
story touching **Broadcom (AVGO)** and **Micron (MU)** — chosen because they're
widely recognizable AI-buildout names, unlike the earlier oil/OPEC+/Enbridge
example. If you change this again, the strings live in `src/theme.ts`
(`DIGEST_ROWS`), `src/dashboard.tsx` (`HOLDINGS` + the news-feed item), and
`src/scenes.tsx` (the notification body, chat Q&A, and the SMS/email/Discord
copy in Scene5) — keep all of them in sync, and keep the voiceover in
`scripts/lib/voiceover-script.mts` matching.

## Voiceover, music bed, and B-roll

`CirviaAd` is narrated and scored:

- **Voiceover** — one mp3 per scene in `public/audio/scene{1-7}-vo.mp3`.
  Wording lives in `scripts/lib/voiceover-script.mts`; cue timing (`voStart`,
  measured `durFrames`) lives in `src/audio.ts`. The current set was
  generated via the **Higgsfield MCP `generate_audio`/`generate_audio_batch`
  tools** (`seed_audio` model, preset voice "Holden") rather than ElevenLabs
  — the ElevenLabs MCP connector had no `ELEVENLABS_API_KEY` configured when
  these were made (every call 401'd). `scripts/generate-voiceover.mts` /
  `.env.example` are still there for the ElevenLabs path once that's fixed;
  either source writes to the same `public/audio/scene{n}-vo.mp3` paths, so
  swapping later is a drop-in replacement — just regenerate and re-measure
  durations (see "Regenerating voiceover" below).

  Scene3's line was trimmed from its original two-sentence draft after the
  first take measured 10.8s against an 8s scene budget — the dropped
  sentence duplicated Scene3's on-screen caption verbatim, so nothing is
  lost. Scene6's `voStart` is 24, not 12, so its line doesn't start before
  Scene5's VO tail (which runs ~21f past Scene5's own boundary) finishes.
- **Music bed** — `public/audio/music-bed.mp3` is currently **55s of
  silence**, a placeholder. Real music is still unsourced: ElevenLabs'
  `compose_music` needs that same missing API key, and Higgsfield's music
  models (`sonilo_music`/`mirelo_text_to_audio`) are restricted to its
  game-generation pipeline and can't be used standalone. Once
  `ELEVENLABS_API_KEY` is set, either call `compose_music` directly or drop
  a licensed stock track (see the plan doc) at that same path.
- **B-roll** — three short, restrained AI-generated video shots (near-black +
  violet accent, slow camera moves only — no warm tones, no fast movement) in
  `public/video/`, generated via the **Higgsfield MCP `generate_video_batch`**
  tool (`seedance_2_0`, 720p, `generate_audio: false`), then conformed to
  1920x1080/30fps/muted with `npm run broll:conform`. Composited as
  atmosphere behind/around the code-driven scenes, never replacing them:
  - `shot-a-coldopen.mp4` — dark pre-dawn cityscape, behind Scene1's headline.
    Prompt: "A dark, near-black pre-dawn cityscape skyline silhouette, thin
    deep-violet rim-light along the horizon, one or two lone lit windows,
    faint atmospheric haze, extremely slow and subtle dolly-in camera
    movement, still and cinematic. Muted palette: near-black base (#08060c)
    with a single violet accent (#683eb6 to #b599ff) — no warm tones, no
    orange, no lens flare, no people, no text or logos, no fast camera
    movement. Restrained, quiet, moody minimalist night photography." Came
    back with a subtle warm pink/orange horizon band despite the "no warm
    tones" instruction — left as-is since the scrim mutes it and it still
    reads as premium, but worth a reprompt/reroll if that bothers you.
  - `shot-b-transition.mp4` — abstract particle/data-flow motif bridging the
    Scene5→Scene6 cut. Prompt: "Abstract slow-moving violet and lilac light
    particles and thin data-flow trails drifting and converging on a pure
    near-black background, minimal and elegant motion, no text, no logos,
    no warm colors, no crowds, no lens flare, no glassmorphism, restrained
    slow camera movement, dark cinematic abstract background loop."
  - `shot-c-endcard-loop.mp4` — looping silk/smoke drift behind Scene7's glow.
    Prompt: "Slow, seamless looping drift of silk-like smoke and fabric
    folds in deep violet and near-black tones, soft glowing light from
    within, extremely slow gentle movement, elegant and minimal, no text,
    no logos, no warm colors, no people, no fast movement, cinematic
    ambient background loop." — the standout of the three, dead-on brand.

  All three generated at 720p and upscaled to 1080p by `broll:conform`'s
  scale filter; regenerate at `resolution: "1080p"`/`"4k"` (more credits)
  for a sharper source if the upscale reads soft on a large screen.

  Metadata (opacity, blend mode, which scene mounts which shot) lives in
  `src/broll.ts`.

### Regenerating voiceover

```bash
cp .env.example .env   # fill in ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID
npm run voiceover:generate
```

Prints a `scene | measured sec | measured frames | budget frames | fits?`
table. If a line overruns its scene's budget, trim the wording, nudge that
scene's `voStart` in `src/audio.ts`, or (last resort) extend the scene's
duration in `Root.tsx`'s `MASTER` array — the last option cascades into the
music envelope and the Scene5/6 transition math, so treat it as a
re-derivation, not a one-line tweak. After generating, update `VO_CUES.durFrames`
in `src/audio.ts` to the measured values.

### Conforming B-roll

Generate the three shots (Higgsfield, or another video tool), then:

```bash
brew install ffmpeg   # once, if not already installed
npm run broll:conform -- <raw-shot-a> <raw-shot-b> <raw-shot-c>
```

Conforms each to 1920x1080 h.264 mp4 @ 30fps and drops it at the path
`src/broll.ts` expects. Pass `-` for any shot you're not ready to conform yet.

## Commands

```bash
npm install
npm run studio            # live preview + scrubbing
npm run render             # out/cirvia-ad-16x9.mp4
npm run render:vertical    # out/cirvia-ad-9x16.mp4
npm run render:square      # out/cirvia-ad-1x1.mp4
npm run voiceover:generate # regenerate the 7 VO mp3s from ElevenLabs
npm run broll:conform      # normalize raw B-roll clips into public/video/
```

## Where things live

- `src/theme.ts` - brand tokens, easing, digest row data
- `src/components.tsx` - Screen, Caption, DigestCard, frames, bubbles, buttons, TransitionOverlay
- `src/scenes.tsx` - Scene1..Scene7 (scenes 1, 5, 7 adapt to portrait/square)
- `src/audio.ts` - VO cue timing + music-bed ducking envelope
- `src/broll.ts` - B-roll shot metadata
- `src/Root.tsx` - compositions and scene timelines
- `scripts/generate-voiceover.mts` / `scripts/lib/voiceover-script.mts` - VO generation
- `scripts/conform-broll.mts` - B-roll normalization
