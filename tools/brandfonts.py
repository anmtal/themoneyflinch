"""Portable brand fonts.

Maps the Windows font names the renderers were written against to bundled
open-source near-identical clones, so rendering is byte-identical on any machine
(your PC now, a Linux cloud runner later). Drop-in: `from brandfonts import F`.

  Georgia   -> Gelasio        (Google's metric Georgia clone)
  Segoe UI  -> Inter          (humanist sans, weights 300/400/700)
  Consolas  -> Courier Prime  (mono)
"""
import os
from PIL import ImageFont

FONTS_DIR = os.environ.get(
    "BRAND_FONTS_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fonts"),
)

# windows name -> (bundled file, target weight or None for static)
MAP = {
    "georgia.ttf": ("Gelasio.ttf", 400),
    "georgiai.ttf": ("Gelasio-Italic.ttf", 400),
    "segoeui.ttf": ("Sans.ttf", 400),
    "segoeuib.ttf": ("Sans.ttf", 700),
    "segoeuil.ttf": ("Sans.ttf", 300),
    "consola.ttf": ("CourierPrime-Regular.ttf", None),
    "courbd.ttf": ("CourierPrime-Bold.ttf", None),
}

_cache = {}


def _apply_variation(font, size, weight):
    try:
        axes = font.get_variation_axes()
    except Exception:
        return
    if not axes:
        return
    vals = []
    for a in axes:
        nm = a.get("name", b"")
        nm = nm.decode() if isinstance(nm, bytes) else nm
        if "Weight" in nm and weight:
            vals.append(weight)
        elif "Optical" in nm:
            vals.append(min(a.get("maximum", 32), max(a.get("minimum", 14), float(size))))
        else:
            vals.append(a.get("default", a.get("minimum", 0)))
    try:
        font.set_variation_by_axes(vals)
    except Exception:
        pass


def F(name, size):
    """name = a Windows font filename (as written in the renderers). Returns a
    configured PIL font from the bundled clone."""
    size = int(size)
    key = (name, size)
    if key in _cache:
        return _cache[key]
    fname, weight = MAP.get(name, ("Sans.ttf", 400))
    path = os.path.join(FONTS_DIR, fname)
    font = ImageFont.truetype(path, size)
    _apply_variation(font, size, weight)
    _cache[key] = font
    return font
