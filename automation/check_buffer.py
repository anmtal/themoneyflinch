"""Report how much unposted content is left in the queue (for the buffer alert)."""
import datetime as dt
import json
import os

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "posts-manifest.json"), encoding="utf-8") as f:
    m = json.load(f)

tz = None
if ZoneInfo is not None:
    try:
        tz = ZoneInfo(m.get("timezone", "UTC"))
    except Exception:
        tz = None
now = dt.datetime.now(tz) if tz else dt.datetime.now(dt.timezone.utc)


def due(p):
    d = dt.datetime.fromisoformat(p["publish_at"])
    return d.replace(tzinfo=tz) if tz else d.replace(tzinfo=dt.timezone.utc)


future = [p for p in m["posts"] if p.get("status") == "ready" and due(p) > now]
n = len(future)
per_day = m.get("posts_per_day", 2)
days_left = round(n / per_day, 1)
print(f"unposted={n} days_left={days_left}")

gh_out = os.environ.get("GITHUB_OUTPUT")
if gh_out:
    with open(gh_out, "a", encoding="utf-8") as f:
        f.write(f"days_left={days_left}\nunposted={n}\n")
