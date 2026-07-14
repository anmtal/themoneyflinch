"""The Money Flinch — data-driven carousel batch renderer.

Reads content/specs.json (12 verified 7-slide specs) and renders every carousel
to content/posts/<slug>/slide-N.jpg using the brand system + cover_scenes.

7 slides each: cover (themed phone-screen + overlay) -> 5 body slides -> end.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cover_scenes  # noqa: E402
from brandfonts import F  # noqa: E402  (bundled open fonts; portable across machines)

W, H = 1080, 1350
INK = (22, 35, 42)
CREAM = (246, 241, 231)
CREAM_SOFT = (196, 199, 196)
CORAL = (217, 108, 79)
MANILA = (233, 223, 200)
LINE = (74, 84, 92)

SPECS = r"C:\Users\anmta\.claude\IG Automation\content\specs.json"
POSTS = r"C:\Users\anmta\.claude\IG Automation\content\posts"
HANDLE = "@themoneyflinch"


def wrap(d, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def block(d, text, font, cy, fill, max_w=900, gap=1.22, accent_last=False, anchor_top=False):
    """Centered wrapped text block, vertically centered on cy (or top at cy). Returns (top, bottom)."""
    lines = wrap(d, text, font, max_w)
    lh = font.size * gap
    total_h = lh * (len(lines) - 1)
    y0 = cy if anchor_top else cy - total_h / 2
    for i, line in enumerate(lines):
        y = y0 + i * lh
        if accent_last and i == len(lines) - 1 and " " in line:
            head, last = line.rsplit(" ", 1)
            tw = d.textlength(line, font=font)
            x = (W - tw) / 2
            d.text((x, y), head + " ", font=font, fill=fill, anchor="lm")
            d.text((x + d.textlength(head + " ", font=font), y), last, font=font, fill=CORAL, anchor="lm")
        else:
            d.text((W / 2, y), line, font=font, fill=fill, anchor="mm")
    return y0 - lh / 2, y0 + total_h + lh / 2


def flinch_mark(d, cx, cy, scale, line=CREAM):
    w = int(10 * scale)
    def seg(pts, color):
        pts = [(cx + x * scale, cy + y * scale) for x, y in pts]
        d.line(pts, fill=color, width=w, joint="curve")
        r = w / 2
        for x, y in pts:
            d.ellipse([x - r, y - r, x + r, y + r], fill=color)
    seg([(-95, 0), (-29, 0)], line)
    seg([(29, 0), (95, 0)], line)
    seg([(-29, 0), (-9, -38), (14, 43), (29, 0)], CORAL)


def chrome(d, idx, total, dark=True):
    color = CREAM_SOFT if dark else INK
    d.text((W - 70, 78), f"{idx} / {total}", font=F("consola.ttf", 34), fill=color, anchor="rm")
    flinch_mark(d, W / 2, H - 150, 0.42, line=CREAM if dark else INK)
    d.text((W / 2, H - 82), HANDLE, font=F("segoeuib.ttf", 30), fill=color, anchor="mm")


def render_cover(spec, total):
    img = cover_scenes.render_scene(spec["coverScene"], spec.get("coverConfig", {}))
    d = ImageDraw.Draw(img)
    ov = spec["coverOverlay"]
    d.text((W / 2, 858), ov["series"], font=F("courbd.ttf", 40), fill=CORAL, anchor="mm")
    _, bot = block(d, ov["hook"], F("georgiai.ttf", 74), 1010, CREAM, max_w=900)
    sub = ov.get("subhook", "").replace("->", "→").replace("-&gt;", "→")
    d.text((W / 2, min(bot + 60, 1215)), sub, font=F("segoeui.ttf", 36), fill=CREAM_SOFT, anchor="mm")
    d.text((W / 2, H - 60), HANDLE, font=F("segoeuib.ttf", 30), fill=CREAM_SOFT, anchor="mm")
    # no slide counter on the cover — the phone status bar owns that corner
    return img


def render_statement(slide, idx, total):
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    _, bot = block(d, slide["headline"], F("georgia.ttf", 84), 520, CREAM, max_w=900, accent_last=True)
    if slide.get("sub"):
        block(d, slide["sub"], F("segoeui.ttf", 44), bot + 120, CREAM_SOFT, max_w=820, gap=1.35, anchor_top=True)
    chrome(d, idx, total)
    return img


def render_card(slide, idx, total):
    img = Image.new("RGB", (W, H), MANILA)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([100, 330, 980, 760], radius=18, outline=INK, width=5)
    d.text((W / 2, 450), "FIELD NOTE", font=F("courbd.ttf", 40), fill=INK, anchor="mm")
    d.line([320, 520, 760, 520], fill=INK, width=3)
    term_lines = wrap(d, slide["term"], F("courbd.ttf", 66), 800)
    ty = 620 - (len(term_lines) - 1) * 40
    for i, line in enumerate(term_lines):
        d.text((W / 2, ty + i * 78), line, font=F("courbd.ttf", 66), fill=CORAL, anchor="mm")
    block(d, "(n.)  " + slide["definition"], F("georgiai.ttf", 46), 900, INK, max_w=800, gap=1.3, anchor_top=True)
    chrome(d, idx, total, dark=False)
    return img


def render_end(spec, idx, total):
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    es = spec["endSlide"]
    _, bot = block(d, es["question"], F("georgia.ttf", 80), 500, CREAM, max_w=880)
    block(d, es["repLine"], F("segoeuib.ttf", 46), bot + 130, CORAL, max_w=820, gap=1.3, anchor_top=True)
    chrome(d, idx, total)
    return img


def render_spec(spec):
    slug = spec["slug"]
    out = os.path.join(POSTS, slug)
    os.makedirs(out, exist_ok=True)
    body = spec["bodySlides"]
    total = 1 + len(body) + 1  # cover + body + end
    slides = [render_cover(spec, total)]
    for i, b in enumerate(body):
        idx = 2 + i
        slides.append(render_card(b, idx, total) if b["type"] == "card" else render_statement(b, idx, total))
    slides.append(render_end(spec, total, total))
    for i, img in enumerate(slides, start=1):
        p = os.path.join(out, f"slide-{i}.jpg")
        img.convert("RGB").save(p, "JPEG", quality=90)
    return slug, len(slides)


def main():
    with open(SPECS, encoding="utf-8") as f:
        specs = json.load(f)
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for spec in specs:
        if only and spec["slug"] != only:
            continue
        slug, n = render_spec(spec)
        print(f"  day {spec['day']:2}  {slug:16}  {n} slides")


if __name__ == "__main__":
    main()
