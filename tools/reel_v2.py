"""Reel v2 — voiced, kinetic, single-idea reels for @themoneyflinch.

Why this replaces list_reel.py: the old reels were 31s of STATIC text cards with a
synthetic pad. Cold viewers bailed at ~1.6-4.7s (5-15% watch-through), so the
algorithm never expanded reach. This format fixes the three things that were
capping retention:

  1. A real VOICE (edge-tts) reads a tight ~16-18s script — the ear holds the
     viewer while the eyes read.
  2. KINETIC captions: words light up in sync with the voice (word boundaries from
     edge-tts), so there is motion from frame 1 — the thumb-stop trigger a static
     card never had.
  3. ONE idea, short, ending on a SEND cue ("send this to..."), because sends are
     the #1 reach lever and the old list-with-comment-bait got zero.

Still fully automated and rights-free (no trending audio — that needs manual
posting; a quiet synthesized bed sits under the voice instead).

Input: content/reel-v2-scripts.json  (list of {slug, voiceover, caption, firstComment}).
Usage: python reel_v2.py <slug|all>
"""
import asyncio
import json
import os
import subprocess
import sys
import wave

import edge_tts
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from carousel_batch import INK, CREAM, CREAM_SOFT, CORAL, flinch_mark  # noqa: E402
from brandfonts import F  # noqa: E402

W, H = 1080, 1920
FPS = 30
HANDLE = "@themoneyflinch"
VOICE = "en-US-AriaNeural"
RATE = "-6%"                      # a touch slower = calmer, easier to read along
DIM = (92, 102, 110)             # unspoken word
GAP_BREAK = 0.26                 # a pause longer than this starts a new caption phrase
MAX_WORDS = 7                    # ...or this many words, whichever comes first (keeps sentences whole)
CAP_MAXW = 960                   # caption wrap width
TAIL = 1.5                       # hold after the last word

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "content", "reel-v2-scripts.json")
OUT_DIR = os.path.join(ROOT, "content", "reels")
WORK = os.path.join(os.environ.get("TEMP", "."), "flinch_reel_v2")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(WORK, exist_ok=True)


# ---------- voice ----------

async def _synthesize(text, mp3_path):
    c = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"t": ch["offset"] / 1e7, "d": ch["duration"] / 1e7,
                              "w": ch["text"]})
    return words


def synthesize(text, mp3_path):
    return asyncio.run(_synthesize(text, mp3_path))


def phrases_from_words(words):
    """Group timed words into short caption phrases on pauses / word count."""
    out, cur = [], []
    for i, wd in enumerate(words):
        cur.append(wd)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["t"] - (wd["t"] + wd["d"])) if nxt else 999
        if nxt is None or gap > GAP_BREAK or len(cur) >= MAX_WORDS:
            out.append(cur)
            cur = []
    phrases = [{"words": p, "start": p[0]["t"], "cta": False} for p in out]
    # The send-CTA is usually the last sentence; color it (and everything after the
    # first "send") coral so the ask reads as one deliberate unit, not a stray word.
    cta_from = next((i for i, ph in enumerate(phrases)
                     if any(w["w"].lower().strip(".,!?") == "send" for w in ph["words"])), None)
    if cta_from is not None:
        for ph in phrases[cta_from:]:
            ph["cta"] = True
    return phrases


# ---------- visuals ----------

def build_glow():
    """A soft lighter-navy radial patch (as an L mask) we drift for background motion."""
    gw, gh = W + 500, H + 500
    yy, xx = np.mgrid[0:gh, 0:gw]
    r = np.sqrt((xx - gw / 2) ** 2 + (yy - gh / 2) ** 2)
    a = np.clip(1 - r / (0.62 * gh), 0, 1) ** 2 * 70
    mask = Image.fromarray(a.astype("uint8"), "L")
    patch = Image.new("RGB", (gw, gh), (44, 62, 72))
    return patch, mask


GLOW_PATCH, GLOW_MASK = build_glow()


def layout_words(d, words, font, max_w):
    """Greedy word-wrap. Returns lines, each a list of (word, x_within_line, w)."""
    space = d.textlength(" ", font=font)
    lines, cur, cur_w = [], [], 0.0
    for w in words:
        ww = d.textlength(w, font=font)
        add = ww + (space if cur else 0)
        if cur and cur_w + add > max_w:
            lines.append((cur, cur_w))
            cur, cur_w = [], 0.0
            add = ww
        cur.append((w, ww))
        cur_w += add
    if cur:
        lines.append((cur, cur_w))
    return lines


def draw_caption(d, phrase, t):
    words = phrase["words"]
    is_hook = phrase.get("hook", False)
    size = 104 if is_hook else 84
    font = F("georgia.ttf", size)
    spoken_col = CORAL if phrase["cta"] else CREAM
    # which word is "current" (latest one whose start has passed)
    cur_idx = -1
    for i, wd in enumerate(words):
        if wd["t"] <= t:
            cur_idx = i
    lines = layout_words(d, [wd["w"] for wd in words], font, CAP_MAXW)
    lh = size * 1.24
    total_h = lh * len(lines)
    y = H / 2 - total_h / 2
    space = d.textlength(" ", font=font)
    idx = 0
    for line_words, line_w in lines:
        x = (W - line_w) / 2
        for w, ww in line_words:
            spoken = words[idx]["t"] <= t
            if idx == cur_idx:
                col = CORAL if not phrase["cta"] else CREAM   # pop against the phrase color
            elif spoken:
                col = spoken_col
            else:
                col = DIM
            d.text((x, y), w, font=font, fill=col, anchor="lm")
            x += ww + space
            idx += 1
        y += lh


def frame_bg(t, total):
    bg = Image.new("RGB", (W, H), INK)
    dx = int(90 * np.sin(2 * np.pi * t / 11))
    dy = int(70 * np.sin(2 * np.pi * t / 7 + 1))
    bg.paste(GLOW_PATCH, (-250 + dx, -250 + dy), GLOW_MASK)
    return bg


def draw_chrome(d, t, total):
    # top wordmark
    d.text((W / 2, 150), "THE MONEY FLINCH", font=F("courbd.ttf", 40), fill=CORAL, anchor="mm")
    # progress bar
    bar_y, m = H - 96, 90
    d.line([(m, bar_y), (W - m, bar_y)], fill=(56, 68, 76), width=6)
    p = min(1.0, t / total)
    d.line([(m, bar_y), (m + (W - 2 * m) * p, bar_y)], fill=CORAL, width=6)
    # handle + mark
    flinch_mark(d, W / 2, H - 190, 0.42, line=CREAM_SOFT)
    d.text((W / 2, H - 140), HANDLE, font=F("segoeuib.ttf", 34), fill=CREAM_SOFT, anchor="mm")


# ---------- audio mix ----------

def make_bed(duration, path):
    sr = 44100
    n = int(sr * duration)
    tt = np.linspace(0, duration, n, endpoint=False)
    freqs = [110.0, 164.81, 220.0, 261.63]      # A minor-ish, warm
    sig = np.zeros(n)
    for f in freqs:
        sig += np.sin(2 * np.pi * f * tt) * 0.5
        sig += np.sin(2 * np.pi * f * 1.004 * tt) * 0.2
    sig *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.07 * tt)
    env = np.ones(n)
    fi, fo = int(1.2 * sr), int(2.0 * sr)
    env[:fi] = np.linspace(0, 1, fi)
    env[-fo:] = np.linspace(1, 0, fo)
    sig *= env
    sig = sig / np.max(np.abs(sig)) * 0.18
    pcm = (np.column_stack([sig, sig]) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


# ---------- render one reel ----------

def render(script):
    slug = script["slug"]
    mp3 = os.path.join(WORK, f"{slug}.mp3")
    print(f"  synthesizing voice...", flush=True)
    words = synthesize(script["voiceover"], mp3)
    if not words:
        sys.exit("no word boundaries — check edge-tts / network")
    phrases = phrases_from_words(words)
    phrases[0]["hook"] = True
    voice_end = words[-1]["t"] + words[-1]["d"]
    total = voice_end + TAIL

    bed = os.path.join(WORK, f"{slug}-bed.wav")
    make_bed(total, bed)

    tmp = os.path.join(WORK, f"{slug}-noaudio.mp4")
    writer = imageio_ffmpeg.write_frames(tmp, (W, H), pix_fmt_in="rgb24", fps=FPS,
                                         quality=8, macro_block_size=1,
                                         output_params=["-movflags", "+faststart"])
    writer.send(None)

    starts = [p["start"] for p in phrases]
    n_frames = int(total * FPS)
    for f in range(n_frames):
        t = f / FPS
        img = frame_bg(t, total)
        d = ImageDraw.Draw(img)
        # active phrase = last one started; before the first, show phrase 0 (dim)
        pi = 0
        for i, s in enumerate(starts):
            if s <= t:
                pi = i
        draw_caption(d, phrases[pi], t)
        draw_chrome(d, t, total)
        writer.send(img.tobytes())
        if f % 120 == 0:
            print(f"    frame {f}/{n_frames}", flush=True)
    writer.close()

    out = os.path.join(OUT_DIR, f"{slug}.mp4")
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    # voice at full, bed quiet under it; no normalize so the voice stays dominant
    r = subprocess.run(
        [ff, "-y", "-i", tmp, "-i", mp3, "-i", bed,
         "-filter_complex",
         "[1:a]volume=1.0[v];[2:a]volume=0.5[b];[v][b]amix=inputs=2:normalize=0:duration=longest[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", out],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1800:]); sys.exit("mux failed")
    return out, total


def main():
    with open(SCRIPTS, encoding="utf-8") as f:
        scripts = json.load(f)
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    targets = scripts if arg == "all" else [s for s in scripts if s["slug"] == arg]
    if not targets:
        sys.exit(f"no script with slug '{arg}'")
    for i, s in enumerate(targets, 1):
        p, dur = render(s)
        print(f"[{i}/{len(targets)}] {os.path.basename(p)}  {dur:.1f}s", flush=True)


if __name__ == "__main__":
    main()
