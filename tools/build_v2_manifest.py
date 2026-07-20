"""Rebuild automation/posts-manifest.json from the v2 reel scripts.

Swaps the queue over to the new voiced single-idea reels at 1/day, 12:00 local.
The old static list reels are dropped from the queue (already-posted ones stay
recorded in content/posted.json, so nothing re-posts). New v2 slugs are all fresh.

Cadence is 1/day on purpose: while we are testing a new format, each post should be
a clean read, not volume. Change SLOTS_PER_DAY back to 2 (12:00 + 20:00) to speed up.

Usage: python build_v2_manifest.py            # first slot = today 12:00 if it's still
       python build_v2_manifest.py 2026-07-21 #   comfortably before noon, else tomorrow
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
SLOT_HOURS = [12]              # 1/day at noon; use [12, 20] for 2/day
CUTOFF_HOUR = 11               # if it's past 11:00 local, don't try to grab today's noon


def first_day(arg):
    if arg:
        return dt.date.fromisoformat(arg)
    now = dt.datetime.now(TZ)
    if now.hour < CUTOFF_HOUR:
        return now.date()
    return (now + dt.timedelta(days=1)).date()


def main():
    with open(SCRIPTS, encoding="utf-8") as f:
        scripts = json.load(f)
    if not scripts:
        sys.exit("no scripts in reel-v2-scripts.json")

    start = first_day(sys.argv[1] if len(sys.argv) > 1 else None)
    posts = []
    day = start
    si = 0
    while si < len(scripts):
        for h in SLOT_HOURS:
            if si >= len(scripts):
                break
            s = scripts[si]
            posts.append({
                "slug": s["slug"],
                "slides": 1,                      # unused for reels; kept for schema parity
                "status": "ready",
                "caption": s["caption"],
                "firstComment": s["firstComment"],
                "publish_at": f"{day.isoformat()}T{h:02d}:00",
                "type": "reel",
            })
            si += 1
        day += dt.timedelta(days=1)

    manifest = {
        "timezone": "America/Toronto",
        "posts_per_day": len(SLOT_HOURS),
        "note": ("v2 voiced single-idea reels (tools/reel_v2.py). 1/day at 12:00 ET while we "
                 "test the new format. Old static list reels retired from the queue; posted "
                 "slugs remain in content/posted.json so nothing re-posts."),
        "posts": posts,
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {len(posts)} v2 reels, {SLOT_HOURS} per day, starting {start.isoformat()}")
    for p in posts:
        print(f"  {p['publish_at']}  {p['slug']}")


if __name__ == "__main__":
    main()
