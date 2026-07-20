"""Rebuild automation/posts-manifest.json from the v2 reel scripts.

Swaps the queue over to the new voiced single-idea reels on a fixed weekly
schedule: one reel at 12:00 local on each POST_WEEKDAY. The old static list reels
are dropped from the queue (already-posted ones stay recorded in
content/posted.json, so nothing re-posts). New v2 slugs are all fresh.

Cadence is 2 days/week (Mon + Thu) while we test the new format — fewer, better,
each post a clean read. Edit POST_WEEKDAYS to change the days.

Usage: python build_v2_manifest.py             # first slot = today if today is a
       python build_v2_manifest.py 2026-07-23  #   post-day before ~11:00, else the
                                               #   next post-day
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

POST_WEEKDAYS = [0, 3]         # Mon=0 ... Sun=6  -> Monday & Thursday
SLOT_HOUR = 12                 # noon local
CUTOFF_HOUR = 11               # if it's past this on a post-day, start next post-day instead


def start_date():
    if len(sys.argv) > 1:
        return dt.date.fromisoformat(sys.argv[1])
    now = dt.datetime.now(TZ)
    d = now.date()
    # if today is a post-day and it's still comfortably before noon, we can use today
    if d.weekday() in POST_WEEKDAYS and now.hour < CUTOFF_HOUR:
        return d
    # otherwise advance to the next post-day
    for i in range(1, 8):
        cand = d + dt.timedelta(days=i)
        if cand.weekday() in POST_WEEKDAYS:
            return cand
    return d


def post_days_from(start, count):
    """Yield `count` consecutive post-day dates on/after `start`."""
    days, d = [], start
    while len(days) < count:
        if d.weekday() in POST_WEEKDAYS:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def main():
    with open(SCRIPTS, encoding="utf-8") as f:
        scripts = json.load(f)
    if not scripts:
        sys.exit("no scripts in reel-v2-scripts.json")

    days = post_days_from(start_date(), len(scripts))
    posts = []
    for s, day in zip(scripts, days):
        posts.append({
            "slug": s["slug"],
            "slides": 1,                          # unused for reels; kept for schema parity
            "status": "ready",
            "caption": s["caption"],
            "firstComment": s["firstComment"],
            "publish_at": f"{day.isoformat()}T{SLOT_HOUR:02d}:00",
            "type": "reel",
        })

    manifest = {
        "timezone": "America/Toronto",
        "posts_per_day": round(len(POST_WEEKDAYS) / 7, 3),   # ~0.286 -> buffer alert reads in days
        "posts_per_week": len(POST_WEEKDAYS),
        "note": ("v2 voiced single-idea reels (tools/reel_v2.py). 2 days/week (Mon + Thu) at "
                 "12:00 ET while we test the new format. Old static list reels retired from the "
                 "queue; posted slugs remain in content/posted.json so nothing re-posts."),
        "posts": posts,
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {len(posts)} v2 reels on {[d for d in POST_WEEKDAYS]} (Mon=0), noon ET")
    for p in posts:
        wd = dt.date.fromisoformat(p["publish_at"][:10]).strftime("%a")
        print(f"  {wd} {p['publish_at']}  {p['slug']}")


if __name__ == "__main__":
    main()
