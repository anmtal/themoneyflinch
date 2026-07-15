"""The Money Flinch — broad-appeal LIST carousel renderer.

Reads content/list-specs.json and renders each 5-item list carousel to
content/posts/<slug>/slide-N.jpg (7 slides: hook cover -> 5 items -> end).
Reuses the brand system + helpers from carousel_batch so the look matches.
"""
import json
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from carousel_batch import (  # noqa: E402
    W, H, INK, CREAM, CREAM_SOFT, CORAL, block, chrome, flinch_mark, wrap,
)
from brandfonts import F  # noqa: E402

SPECS = r"C:\Users\anmta\.claude\IG Automation\content\list-specs.json"
POSTS = r"C:\Users\anmta\.claude\IG Automation\content\posts"
HANDLE = "@themoneyflinch"


def render_cover(spec, total):
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    d.text((W / 2, 250), "THE MONEY FLINCH", font=F("courbd.ttf", 40), fill=CORAL, anchor="mm")
    # the list hook, big serif, accent last word coral
    _, bot = block(d, spec["coverHook"], F("georgia.ttf", 96), 620, CREAM, max_w=920, accent_last=True)
    if spec.get("coverSub"):
        block(d, spec["coverSub"], F("segoeui.ttf", 46), bot + 120, CREAM_SOFT, max_w=840, gap=1.35, anchor_top=True)
    d.text((W / 2, 1120), "save this  ↓", font=F("segoeuib.ttf", 44), fill=CORAL, anchor="mm")
    flinch_mark(d, W / 2, H - 150, 0.42, line=CREAM)
    d.text((W / 2, H - 82), HANDLE, font=F("segoeuib.ttf", 30), fill=CREAM_SOFT, anchor="mm")
    return img


def render_item(item, number, idx, total):
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    # big coral numeral anchor
    d.text((W / 2, 300), str(number), font=F("georgia.ttf", 150), fill=CORAL, anchor="mm")
    _, bot = block(d, item["title"], F("georgia.ttf", 78), 540, CREAM, max_w=900, accent_last=False)
    if item.get("detail"):
        block(d, item["detail"], F("segoeui.ttf", 46), bot + 110, CREAM_SOFT, max_w=860, gap=1.4, anchor_top=True)
    chrome(d, idx, total)
    return img


def render_end(spec, total):
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    _, bot = block(d, spec["closer"], F("georgia.ttf", 82), 480, CREAM, max_w=900, accent_last=True)
    block(d, spec["commentBait"], F("segoeuib.ttf", 46), bot + 140, CORAL, max_w=860, gap=1.35, anchor_top=True)
    chrome(d, total, total)
    return img


def render_spec(spec):
    slug = spec["slug"]
    out = os.path.join(POSTS, slug)
    os.makedirs(out, exist_ok=True)
    items = spec["items"]
    total = 1 + len(items) + 1  # cover + items + end = 7
    slides = [render_cover(spec, total)]
    for i, it in enumerate(items):
        slides.append(render_item(it, i + 1, 2 + i, total))
    slides.append(render_end(spec, total))
    for i, s in enumerate(slides, start=1):
        s.convert("RGB").save(os.path.join(out, f"slide-{i}.jpg"), "JPEG", quality=90)
    return slug, len(slides)


def main():
    with open(SPECS, encoding="utf-8") as f:
        specs = json.load(f)
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for spec in specs:
        if only and spec["slug"] != only:
            continue
        slug, n = render_spec(spec)
        print(f"  {slug:34}  {n} slides")


if __name__ == "__main__":
    main()
