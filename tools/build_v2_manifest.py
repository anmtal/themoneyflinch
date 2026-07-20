"""Rebuild automation/posts-manifest.json from the v2 reel scripts.

Swaps the queue over to the new voiced single-idea reels at 2/day, 12:00 and 20:00
local. The old static list reels are dropped from the queue (already-posted ones
stay recorded in content/posted.json, so nothing re-posts). New v2 slugs are all
fresh.

Usage: python build_v2_manifest.py             # first slot = today 12:00 if it's
       python build_v2_manifest.py 2026-07-21  #   still before ~11:00, else next slot
"""
import datetime as dt
import json
import os
import sys

from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "content", "reel-v2-scripts.json")
MANIFEST = os.path.join(ROOT, "automation", "posts-manifest.json")
TZ = ZoneInfo("America/Toronto")

SLOT_HOURS = [12, 20]          # 2/day: noon + 8pm local
CUTOFF_HOUR = 11               # if it's past this on the first day, skip today's noon slot


def slots(count):
    """Yield `count` (date, hour) slots at SLOT_HOURS/day, starting today if a start
    date is given, else today when still before the cutoff, else tomorrow."""
    if len(sys.argv) > 1:
        day = dt.date.fromisoformat(sys.argv[1])
        skip_noon = False
    else:
        now = dt.datetime.now(TZ)
        day = now.date()
        # only try to grab today's noon if we're comfortably ahead of it
        skip_noon = now.hour >= CUTOFF_HOUR

    out = []
    while len(out) < count:
        for h in SLOT_HOURS:
            if skip_noon and h == SLOT_HOURS[0] and day == (dt.datetime.now(TZ).date()):
                continue
            out.append((day, h))
            if len(out) >= count:
                break
        day += dt.timedelta(days=1)
    return out


def main():
    with open(SCRIPTS, encoding="utf-8") as f:
        scripts = json.load(f)
    if not scripts:
        sys.exit("no scripts in reel-v2-scripts.json")

    posts = []
    for s, (day, h) in zip(scripts, slots(len(scripts))):
        posts.append({
            "slug": s["slug"],
            "slides": 1,                          # unused for reels; kept for schema parity
            "status": "ready",
            "caption": s["caption"],
            "firstComment": s["firstComment"],
            "publish_at": f"{day.isoformat()}T{h:02d}:00",
            "type": "reel",
        })

    manifest = {
        "timezone": "America/Toronto",
        "posts_per_day": len(SLOT_HOURS),
        "note": ("v2 voiced single-idea reels (tools/reel_v2.py), 2/day at 12:00 and 20:00 ET. "
                 "Old static list reels retired from the queue; posted slugs remain in "
                 "content/posted.json so nothing re-posts."),
        "posts": posts,
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {len(posts)} v2 reels, 2/day at {SLOT_HOURS} ET")
    for p in posts:
        wd = dt.date.fromisoformat(p["publish_at"][:10]).strftime("%a")
        print(f"  {wd} {p['publish_at']}  {p['slug']}")


if __name__ == "__main__":
    main()
