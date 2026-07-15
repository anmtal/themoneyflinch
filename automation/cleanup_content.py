"""Delete already-posted reel videos from the repo to keep it lean.

Once a reel is published, Instagram serves its own copy, so the GitHub-hosted
mp4 (~10MB) is no longer needed. This removes videos for reels whose scheduled
time is more than a day in the past (safely posted). Runs every 2 days.

Only touches reel videos in content/reels/. Leaves carousel images, specs,
and unscheduled content alone. Files are always re-creatable from the specs.
"""
import datetime as dt
import json
import os

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUFFER_DAYS = 1   # only delete videos this many days past their post time

with open(os.path.join(HERE, "posts-manifest.json"), encoding="utf-8") as f:
    m = json.load(f)

tz = None
if ZoneInfo is not None:
    try:
        tz = ZoneInfo(m.get("timezone", "UTC"))
    except Exception:
        tz = None
now = dt.datetime.now(tz) if tz else dt.datetime.now(dt.timezone.utc)
cutoff = now - dt.timedelta(days=BUFFER_DAYS)

removed = []
for post in m["posts"]:
    if post.get("type") != "reel":
        continue
    pub = dt.datetime.fromisoformat(post["publish_at"])
    pub = pub.replace(tzinfo=tz) if tz else pub.replace(tzinfo=dt.timezone.utc)
    if pub >= cutoff:
        continue   # future or too recent — keep the video live
    path = os.path.join(ROOT, "content", "reels", f"{post['slug']}.mp4")
    if os.path.exists(path):
        os.remove(path)
        removed.append(f"content/reels/{post['slug']}.mp4")

print(f"cleanup at {now.isoformat()}")
print("removed:", removed if removed else "nothing (no posted videos past the buffer)")
