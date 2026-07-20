---
name: remotion
description: >-
  Generate branded @themoneyflinch Instagram reels as ANIMATED video from code,
  using the Remotion (React/TSX) project in `video/`. Use this whenever the user
  wants to make, render, refill, or restyle reels — including "generate a reel",
  "render the reels", "make a video for this script", "new reel format", "refill
  the queue", "change how the reels look", or any request to turn a Money Flinch
  script into an MP4. This is the CURRENT reel renderer; prefer it over the old PIL
  frame-stitching tools (tools/reel_v2.py, tools/list_reel.py), which produced the
  static text-card reels that capped watch-through at 5–15%. Also use it when
  editing reel visuals (motion, captions, colors, timing), since those live in
  React components, not Python.
---

# Remotion reel generator for @themoneyflinch

Renders vertical 1080×1920 animated reels from a script: a real voiceover plus
kinetic word-synced captions with spring motion, brand chrome, and a drifting
background. This replaces the static PIL slideshows an adversarial QA identified as
the growth ceiling (no motion → no thumb-stop → the algorithm never expands reach).

**The split that makes it work:** Python (edge-tts) does the voice, because it
already returns exact per-word timings for free; Remotion (React) does the visuals,
because that is where real motion design lives. Never re-transcribe in Node.

## Project layout (`video/`)

```
video/
├── build.mjs          # orchestrator: voice → bundle → render → copy to content/reels/
├── voice.py           # edge-tts → public/<slug>.mp3 + public/<slug>.words.json
├── src/
│   ├── Reel.tsx       # the composition — EDIT THIS to change how reels look/move
│   ├── Root.tsx       # registers the composition; derives duration from the voice
│   ├── captions.ts    # groups words into phrases; marks the "send…" CTA coral
│   └── brand.tsx      # colors + the flinch mark (mirrors tools/carousel_batch.py)
└── package.json
```

## One-time setup

Node 20+ is required. Install once (downloads Remotion + a headless Chrome, ~2 min):

```bash
cd video && npm install
```

If a render ever complains it can't find a browser, run `npx remotion browser ensure`.

## Generate a reel (the normal path)

1. **Add the script** to `content/reel-v2-scripts.json` — a list of objects:
   ```json
   {
     "slug": "v2-the-bill-on-the-counter",
     "voiceover": "One tight spoken idea, ~15–18s, ending on: Send this to someone who…",
     "caption": "Scroll-stopping first line.\n\n#moneyanxiety #financialtherapy #moneypsychology #moneymindset #personalfinance",
     "firstComment": "The reflective follow-up posted as the first comment."
   }
   ```
   Keep the voiceover short (the win over the old format is length: aim 15–20s, not
   31s) and end on a "Send this to…" cue — shares are the #1 reach lever.

2. **Render** (from `video/`):
   ```bash
   node build.mjs v2-the-bill-on-the-counter   # one reel
   node build.mjs all                          # every script not yet rendered
   ```
   Output lands at `content/reels/<slug>.mp4` — exactly where the publisher hosts
   and posts from, so nothing downstream changes.

3. **Schedule it**: `python tools/build_v2_manifest.py` rebuilds the manifest (2/day
   at 12:00 & 20:00 ET) from the scripts. Then push the repo (see
   [[flinch-repo-is-not-the-working-dir]] — the working dir is NOT the git repo;
   push via the clone or nothing ships).

## Tuning the look

Edit `src/Reel.tsx` (plain React). For live preview with a scrubber:

```bash
cd video && npm run studio      # opens Remotion Studio in the browser
```

Common changes and where they live:
- **Motion / timing of words** → the `CaptionWord` component and the `spring(...)`
  calls in `Reel.tsx`.
- **Phrase grouping** (words per line, pause sensitivity) → `GAP_BREAK` / `MAX_WORDS`
  in `captions.ts`.
- **Colors, wordmark, the flinch mark** → `src/brand.tsx`.
- **Voice** (speaker, pace) → `VOICE` / `RATE` in `voice.py`.

Duration is automatic: `Root.tsx`'s `calculateMetadata` sets the frame count from
the last word's end + `tail`, so a longer or shorter script just works.

## Gotchas (already handled — don't reintroduce)

- **Voice must be synthesized before `bundle()`** runs. `bundle()` snapshots
  `public/` into the Remotion bundle, so an mp3 written afterward 404s at render.
  `build.mjs` does all voices first, then bundles — keep that order.
- **Fonts are weight-constrained** in `Reel.tsx` (`loadFont(... {weights:[...]})`).
  Loading a full family fires 100+ network requests per font and stalls the render.
- **Codec/format**: H.264, yuv420p, +faststart, JPEG frames (`remotion.config.ts`).
  Instagram needs H.264 MP4; faststart lets playback begin before full download.
- **`.mp3`/`.words.json` in `public/` are generated artifacts** (git-ignored). The
  source of truth is `content/reel-v2-scripts.json`.

## When NOT to use this

- Carousels (static multi-image posts) → `tools/carousel_batch.py`, not Remotion.
- Posting/scheduling/token logic → `automation/publisher.py`. This skill only makes
  the video file; it never touches the account.
