"""Voiceover step for the Remotion reel pipeline.

Reuses the exact edge-tts voice + word-boundary approach proven in
tools/reel_v2.py, but instead of rendering frames it just emits the two things
the Remotion composition needs from Node:

    video/public/<slug>.mp3          — the voiceover audio track
    video/public/<slug>.words.json   — [{t, d, w}, ...] word timings (seconds)

Splitting voice (Python/edge-tts) from visuals (Remotion/React) lets each side do
what it is best at: edge-tts already gives exact word boundaries for free, so
there is no reason to re-transcribe in Node.

Usage: python voice.py <slug|all>
"""
import asyncio
import json
import os
import sys

import edge_tts

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "content", "reel-v2-scripts.json")
PUBLIC = os.path.join(HERE, "public")
os.makedirs(PUBLIC, exist_ok=True)

VOICE = "en-US-AriaNeural"
RATE = "-6%"   # matches reel_v2.py — a touch slower reads calmer


async def _synth(text, mp3_path):
    c = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"t": round(ch["offset"] / 1e7, 4),
                              "d": round(ch["duration"] / 1e7, 4),
                              "w": ch["text"]})
    return words


def build(script):
    slug = script["slug"]
    mp3 = os.path.join(PUBLIC, f"{slug}.mp3")
    words = asyncio.run(_synth(script["voiceover"], mp3))
    if not words:
        sys.exit(f"{slug}: no word boundaries — check edge-tts / network")
    with open(os.path.join(PUBLIC, f"{slug}.words.json"), "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False)
    dur = words[-1]["t"] + words[-1]["d"]
    print(f"  voice: {slug}  {len(words)} words, {dur:.1f}s")
    return slug


def main():
    with open(SCRIPTS, encoding="utf-8") as f:
        scripts = json.load(f)
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    targets = scripts if arg == "all" else [s for s in scripts if s["slug"] == arg]
    if not targets:
        sys.exit(f"no script with slug '{arg}'")
    for s in targets:
        build(s)


if __name__ == "__main__":
    main()
