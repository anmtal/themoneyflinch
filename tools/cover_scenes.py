"""The Money Flinch — cover-scene renderers.

Five reusable phone-screen "screenshots" for carousel slide 1. Each renders a
realistic mockup in the upper region of a 1080x1350 frame and leaves a darkened
brand zone at the bottom for the generator's overlay text.

Each function takes a config dict (keys documented per scene) and returns a PIL
RGB Image. Missing keys fall back to sensible defaults so a slightly-off spec
still renders.
"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350

# phone-screen palette (realistic dark UI, brand-adjacent)
SCREEN = (14, 20, 27)
CARD = (34, 42, 51)
CARD2 = (28, 35, 43)
TXT = (238, 240, 242)
TXT_DIM = (150, 160, 168)
DIVIDER = (52, 60, 68)
CORAL = (217, 108, 79)
GREEN = (94, 176, 125)
TOGGLE_ON = (94, 176, 125)
TOGGLE_OFF = (70, 78, 86)
BADGE = (232, 74, 62)
BANK_NAVY = (18, 60, 105)

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brandfonts import F  # noqa: E402  (bundled open fonts; portable across machines)


def _base():
    img = Image.new("RGB", (W, H), SCREEN)
    return img, ImageDraw.Draw(img)


def _status_bar(d, time="9:41"):
    d.text((70, 70), time, font=F("segoeuib.ttf", 40), fill=TXT)
    # signal / wifi / battery glyphs, minimal
    d.rounded_rectangle([W - 150, 58, W - 96, 86], radius=6, outline=TXT, width=3)
    d.rounded_rectangle([W - 145, 63, W - 118, 81], radius=3, fill=TXT)
    for i, h in enumerate((10, 16, 22, 28)):
        d.rectangle([W - 300 + i * 16, 84 - h, W - 300 + i * 16 + 10, 84], fill=TXT)


def _brand_zone(img, height=660):
    """Darken the bottom `height`px so overlay text reads over any scene content."""
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for i in range(height):
        a = int(248 * (i / height) ** 0.85)
        bd.line([(0, H - height + i), (W, H - height + i)], fill=(12, 18, 24, a))
    return Image.alpha_composite(img.convert("RGBA"), band).convert("RGB")


def _icon_bank(d, x, y, s=88):
    d.rounded_rectangle([x, y, x + s, y + s], radius=22, fill=BANK_NAVY)
    cx, cy = x + s / 2, y + s / 2
    d.polygon([(cx - 27, cy - 6), (cx, cy - 27), (cx + 27, cy - 6)], fill=TXT)
    for k in (-20, -6, 8, 22):
        d.rectangle([cx + k, cy - 2, cx + k + 8, cy + 18], fill=TXT)
    d.rectangle([cx - 27, cy + 21, cx + 27, cy + 29], fill=TXT)


def notification(cfg):
    """cfg: {time, cards:[{app,title,body}]}"""
    img, d = _base()
    time = cfg.get("time", "1:04")
    d.text((W / 2, 210), "Tuesday, July 14", font=F("segoeui.ttf", 40), fill=TXT_DIM, anchor="mm")
    d.text((W / 2, 370), time, font=F("segoeuil.ttf", 240), fill=TXT, anchor="mm")
    y = 560
    for c in cfg.get("cards", [{"app": "BANK", "title": "Balance update", "body": "Your available balance has changed."}]):
        d.rounded_rectangle([70, y, W - 70, y + 190], radius=34, fill=(58, 66, 74))
        _icon_bank(d, 104, y + 34)
        tx = 104 + 88 + 28
        d.text((tx, y + 50), c.get("app", "BANK"), font=F("segoeuib.ttf", 32), fill=TXT_DIM, anchor="lm")
        d.text((W - 104, y + 50), "now", font=F("segoeui.ttf", 30), fill=TXT_DIM, anchor="rm")
        d.text((tx, y + 108), c.get("title", ""), font=F("segoeuib.ttf", 42), fill=TXT, anchor="lm")
        d.text((tx, y + 158), c.get("body", ""), font=F("segoeui.ttf", 34), fill=TXT_DIM, anchor="lm")
        y += 220
    return _brand_zone(img)


def list_screen(cfg):
    """cfg: {appTitle, rows:[{left,right,muted}], badge, tabLabel}"""
    img, d = _base()
    _status_bar(d)
    title = cfg.get("appTitle", "Inbox")
    d.text((70, 150), title, font=F("segoeuib.ttf", 64), fill=TXT)
    badge = cfg.get("badge")
    if badge:
        tw = d.textlength(title, font=F("segoeuib.ttf", 64))
        bx = 70 + tw + 34
        r = 40
        d.ellipse([bx, 158, bx + r * 2, 158 + r * 2], fill=BADGE)
        d.text((bx + r, 158 + r), str(badge), font=F("segoeuib.ttf", 40), fill=TXT, anchor="mm")
    y = 290
    rows = cfg.get("rows", [])
    for row in rows[:4]:
        muted = row.get("muted", False)
        lc = TXT_DIM if muted else TXT
        d.ellipse([80, y + 18, 140, y + 78], fill=CARD)
        d.text((172, y + 22), str(row.get("left", "")), font=F("segoeuib.ttf", 42), fill=lc, anchor="lm")
        if row.get("sub"):
            d.text((172, y + 68), str(row["sub"]), font=F("segoeui.ttf", 32), fill=TXT_DIM, anchor="lm")
        rv = str(row.get("right", ""))
        rc = CORAL if row.get("accent") else TXT_DIM
        d.text((W - 80, y + 40), rv, font=F("segoeuib.ttf", 38), fill=rc, anchor="rm")
        d.line([70, y + 118, W - 70, y + 118], fill=DIVIDER, width=2)
        y += 132
    return _brand_zone(img)


def balance(cfg):
    """cfg: {greeting, amount, blurred, label}"""
    img, d = _base()
    _status_bar(d)
    d.text((W / 2, 260), cfg.get("label", "Checking"), font=F("segoeui.ttf", 40), fill=TXT_DIM, anchor="mm")
    d.text((W / 2, 320), cfg.get("greeting", "Available balance"), font=F("segoeui.ttf", 36), fill=TXT_DIM, anchor="mm")
    amount = cfg.get("amount", "$1,240.18")
    if cfg.get("blurred", False):
        # draw amount then blur just that band
        sub = Image.new("RGB", (W, 200), SCREEN)
        sd = ImageDraw.Draw(sub)
        sd.text((W / 2, 100), amount, font=F("segoeuib.ttf", 130), fill=TXT, anchor="mm")
        from PIL import ImageFilter
        sub = sub.filter(ImageFilter.GaussianBlur(22))
        img.paste(sub, (0, 380))
        img_d = ImageDraw.Draw(img)
        img_d.text((W / 2, 620), "tap to reveal", font=F("segoeui.ttf", 34), fill=TXT_DIM, anchor="mm")
        return _brand_zone(img)
    d.text((W / 2, 480), amount, font=F("segoeuib.ttf", 130), fill=TXT, anchor="mm")
    return _brand_zone(img)


def settings(cfg):
    """cfg: {title, rows:[{label,on}]}"""
    img, d = _base()
    _status_bar(d)
    d.text((70, 150), cfg.get("title", "Notifications"), font=F("segoeuib.ttf", 60), fill=TXT)
    y = 300
    for row in cfg.get("rows", [])[:5]:
        d.rounded_rectangle([70, y, W - 70, y + 120], radius=24, fill=CARD2)
        d.text((110, y + 60), str(row.get("label", "")), font=F("segoeui.ttf", 42), fill=TXT, anchor="lm")
        on = row.get("on", False)
        tx0, tx1 = W - 210, W - 110
        d.rounded_rectangle([tx0, y + 38, tx1, y + 82], radius=22, fill=TOGGLE_ON if on else TOGGLE_OFF)
        knob = tx1 - 30 if on else tx0 + 8
        d.ellipse([knob, y + 42, knob + 36, y + 78], fill=TXT)
        y += 148
    return _brand_zone(img)


def checkout(cfg):
    """cfg: {item, price, cardLast4, time}"""
    img, d = _base()
    _status_bar(d, cfg.get("time", "12:47"))
    d.text((70, 160), "Checkout", font=F("segoeuib.ttf", 60), fill=TXT)
    d.rounded_rectangle([70, 300, W - 70, 440], radius=24, fill=CARD2)
    d.rounded_rectangle([100, 330, 210, 410], radius=14, fill=CARD)
    d.text((240, 348), cfg.get("item", "1 item in cart"), font=F("segoeuib.ttf", 40), fill=TXT, anchor="lm")
    d.text((240, 400), "Ready to buy", font=F("segoeui.ttf", 32), fill=TXT_DIM, anchor="lm")
    d.text((W - 100, 370), cfg.get("price", "$48.00"), font=F("segoeuib.ttf", 46), fill=TXT, anchor="rm")
    # saved card row
    d.text((90, 500), "Pay with", font=F("segoeui.ttf", 34), fill=TXT_DIM)
    d.rounded_rectangle([70, 540, W - 70, 640], radius=20, fill=CARD2)
    d.rounded_rectangle([100, 566, 168, 614], radius=8, fill=CORAL)
    d.text((196, 590), f"•••• {cfg.get('cardLast4', '4242')}", font=F("segoeuib.ttf", 40), fill=TXT, anchor="lm")
    d.text((W - 100, 590), "saved", font=F("segoeui.ttf", 32), fill=TXT_DIM, anchor="rm")
    # buy button
    d.rounded_rectangle([70, 700, W - 70, 800], radius=50, fill=CORAL)
    d.text((W / 2, 750), "Buy now", font=F("segoeuib.ttf", 44), fill=(20, 20, 20), anchor="mm")
    return _brand_zone(img)


SCENES = {
    "notification": notification,
    "list": list_screen,
    "balance": balance,
    "settings": settings,
    "checkout": checkout,
}


def render_scene(scene, cfg):
    fn = SCENES.get(scene, notification)
    return fn(cfg or {})


if __name__ == "__main__":
    OUT = os.path.join(os.environ.get("TEMP", "."), "cover_scene_tests")
    os.makedirs(OUT, exist_ok=True)
    samples = {
        "notification": {"time": "1:04", "cards": [{"app": "BANK", "title": "Balance update", "body": "Your available balance has changed."}]},
        "list": {"appTitle": "Inbox", "badge": 47, "rows": [
            {"left": "Your bank", "sub": "Statement ready", "right": "2h", "muted": True},
            {"left": "Your bank", "sub": "Low balance alert", "right": "1d", "muted": True},
            {"left": "Your bank", "sub": "Payment due", "right": "3d", "muted": True},
        ]},
        "balance": {"label": "Checking", "greeting": "Available balance", "amount": "$1,240.18", "blurred": True},
        "settings": {"title": "Notifications", "rows": [
            {"label": "BANK — Alerts", "on": False},
            {"label": "BANK — Deposits", "on": False},
            {"label": "Messages", "on": True},
        ]},
        "checkout": {"item": "1 item in cart", "price": "$48.00", "cardLast4": "4242", "time": "12:47"},
    }
    for scene, cfg in samples.items():
        render_scene(scene, cfg).save(os.path.join(OUT, f"{scene}.png"))
        print("wrote", os.path.join(OUT, f"{scene}.png"))
