# Cirvia advert (Remotion)

Motion-design advert for Cirvia, rendered from React with [Remotion](https://remotion.dev).
Brand tokens are hex conversions of the site's OKLCH custom properties in
`app/landing.py`; the motion language matches the site (ease-out quint,
masked line rises, small fades).

## Compositions

| ID | Format | Length | Scenes |
|---|---|---|---|
| `CirviaAd` | 1920x1080 (16:9) | 50s | 1-7 (full story) |
| `CirviaAdVertical` | 1080x1920 (9:16) | 20s | cold open, channel fan-out, end card |
| `CirviaAdSquare` | 1080x1080 (1:1) | 15s | same, tighter |

Scene map (master): 1 cold open + headline · 2 web digest · 3 macro alert ·
4 chat · 5 channel fan-out (SMS / email / Discord / web) · 6 trust ·
7 end card.

## Commands

```bash
npm install
npm run studio            # live preview + scrubbing
npm run render            # out/cirvia-ad-16x9.mp4
npm run render:vertical   # out/cirvia-ad-9x16.mp4
npm run render:square     # out/cirvia-ad-1x1.mp4
```

## Where things live

- `src/theme.ts` - brand tokens, easing, digest row data
- `src/components.tsx` - Screen, Caption, DigestCard, frames, bubbles, buttons
- `src/scenes.tsx` - Scene1..Scene7 (scenes 1, 5, 7 adapt to portrait/square)
- `src/Root.tsx` - compositions and scene timelines

The video is silent by design (works muted). To add music, drop a track in
`public/` and add an `<Audio>` element in `Root.tsx`.
