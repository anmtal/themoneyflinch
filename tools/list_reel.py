"""Render one broad-appeal LIST post as an animated reel (1080x1920) with a
calm instrumental bed. No voiceover — text-on-screen paced for reading.

Usage: python list_reel.py <slug>
"""
import json
import os
import subprocess
import sys

import imageio_ffmpeg
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from carousel_batch import INK, CREAM, CREAM_SOFT, CORAL, wrap, flinch_mark  # noqa: E402
from brandfonts import F  # noqa: E402
import gen_ambient  # noqa: E402

W, H = 1080, 1920
SS = 1.10
SW, SH = int(W * SS), int(H * SS)
FPS = 30
HANDLE = "@themoneyflinch"

SPECS = r"C:\Users\anmta\.claude\IG Automation\content\list-specs.json"
OUT_DIR = r"C:\Users\anmta\.claude\IG Automation\content\reels"
WORK = os.path.join(os.environ.get("TEMP", "."), "flinch_reel_work")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(WORK, exist_ok=True)


def block(d, text, font, cy, fill, max_w=1000, gap=1.2, accent_last=False, top=False):
    lines = wrap(d, text, font, max_w)
    lh = font.size * gap
    total = lh * (len(lines) - 1)
    y0 = cy if top else cy - total / 2
    for i, line in enumerate(lines):
        y = y0 + i * lh
        if accent_last and i == len(lines) - 1 and " " in line:
            head, last = line.rsplit(" ", 1)
            tw = d.textlength(line, font=font)
            x = (SW - tw) / 2
            d.text((x, y), head + " ", font=font, fill=fill, anchor="lm")
            d.text((x + d.textlength(head + " ", font=font), y), last, font=font, fill=CORAL, anchor="lm")
        else:
            d.text((SW / 2, y), line, font=font, fill=fill, anchor="mm")
    return y0 + total


def base_cover(spec):
    img = Image.new("RGB", (SW, SH), INK)
    d = ImageDraw.Draw(img)
    d.text((SW / 2, 430), "THE MONEY FLINCH", font=F("courbd.ttf", 46), fill=CORAL, anchor="mm")
    bot = block(d, spec["coverHook"], F("georgia.ttf", 110), 860, CREAM, max_w=980, accent_last=True)
    if spec.get("coverSub"):
        block(d, spec["coverSub"], F("segoeui.ttf", 50), bot + 150, CREAM_SOFT, max_w=920, gap=1.35, top=True)
    flinch_mark(d, SW / 2, SH - 230, 0.5, line=CREAM)
    d.text((SW / 2, SH - 150), HANDLE, font=F("segoeuib.ttf", 38), fill=CREAM_SOFT, anchor="mm")
    return img


def base_item(item, number, total_items):
    img = Image.new("RGB", (SW, SH), INK)
    d = ImageDraw.Draw(img)
    d.text((SW / 2, 520), str(number), font=F("georgia.ttf", 200), fill=CORAL, anchor="mm")
    bot = block(d, item["title"], F("georgia.ttf", 88), 900, CREAM, max_w=980)
    if item.get("detail"):
        block(d, item["detail"], F("segoeui.ttf", 50), bot + 120, CREAM_SOFT, max_w=940, gap=1.4, top=True)
    # progress dots
    dot_gap = 46
    x0 = SW / 2 - dot_gap * (total_items - 1) / 2
    for i in range(total_items):
        c = CORAL if i == number - 1 else (70, 80, 88)
        d.ellipse([x0 + i * dot_gap - 9, SH - 250 - 9, x0 + i * dot_gap + 9, SH - 250 + 9], fill=c)
    d.text((SW / 2, SH - 150), HANDLE, font=F("segoeuib.ttf", 38), fill=CREAM_SOFT, anchor="mm")
    return img


def base_end(spec):
    img = Image.new("RGB", (SW, SH), INK)
    d = ImageDraw.Draw(img)
    bot = block(d, spec["closer"], F("georgia.ttf", 92), 820, CREAM, max_w=980, accent_last=True)
    block(d, spec["commentBait"], F("segoeuib.ttf", 52), bot + 170, CORAL, max_w=940, gap=1.35, top=True)
    flinch_mark(d, SW / 2, SH - 230, 0.5, line=CREAM)
    d.text((SW / 2, SH - 150), HANDLE, font=F("segoeuib.ttf", 38), fill=CREAM_SOFT, anchor="mm")
    return img


def render_reel(spec):
    slug = spec["slug"]
    n_items = len(spec["items"])
    segments = [("cover", base_cover(spec), 3.6)]
    for i, it in enumerate(spec["items"]):
        segments.append(("item", base_item(it, i + 1, n_items), 4.7))
    segments.append(("end", base_end(spec), 3.8))
    total_dur = sum(s[2] for s in segments)

    wav = os.path.join(WORK, f"bed-{slug}.wav")
    gen_ambient.generate(total_dur, wav)

    tmp = os.path.join(WORK, f"reel-{slug}-noaudio.mp4")
    writer = imageio_ffmpeg.write_frames(tmp, (W, H), pix_fmt_in="rgb24", fps=FPS,
                                         quality=8, macro_block_size=1,
                                         output_params=["-movflags", "+faststart"])
    writer.send(None)

    # timeline
    starts = []
    acc = 0.0
    for _, _, dur in segments:
        starts.append(acc)
        acc += dur

    n_frames = int(total_dur * FPS)
    for f in range(n_frames):
        t = f / FPS
        idx = max(i for i in range(len(segments)) if starts[i] <= t)
        _, base, dur = segments[idx]
        lt = t - starts[idx]
        # fade-in first 0.5s
        alpha = min(1.0, lt / 0.5)
        frame = Image.new("RGB", (SW, SH), INK)
        if alpha >= 1.0:
            comp = base
        else:
            comp = Image.blend(Image.new("RGB", (SW, SH), INK), base, alpha)
        # drift zoom 1.02 -> 1.08 across the segment
        z = 1.02 + 0.06 * min(1.0, lt / dur)
        cw, ch = SW / z, SH / z
        left, top = (SW - cw) / 2, (SH - ch) / 2
        out = comp.crop((int(left), int(top), int(left + cw), int(top + ch))).resize((W, H), Image.LANCZOS)
        writer.send(out.tobytes())
        if f % 120 == 0:
            print(f"  frame {f}/{n_frames}", flush=True)
    writer.close()

    out_path = os.path.join(OUT_DIR, f"{slug}.mp4")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([ffmpeg, "-y", "-i", tmp, "-i", wav, "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", out_path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:]); sys.exit("mux failed")
    return out_path, total_dur


def main():
    with open(SPECS, encoding="utf-8") as f:
        specs = json.load(f)
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    targets = specs if arg == "all" else [s for s in specs if s["slug"] == arg]
    for i, spec in enumerate(targets, 1):
        p, dur = render_reel(spec)
        print(f"[{i}/{len(targets)}] {os.path.basename(p)}  {dur:.1f}s", flush=True)


if __name__ == "__main__":
    main()
