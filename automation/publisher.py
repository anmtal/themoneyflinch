"""The Money Flinch — automated Instagram carousel publisher.

Uses the official Instagram Graph API (ToS-legal, no bots). Publishes the
carousel scheduled for today and posts the comment-bait line as the first comment.

Usage:
    python publisher.py --today            # publish the post scheduled for today
    python publisher.py --slug after-check # publish a specific post now
    python publisher.py --today --dry-run  # validate + check URLs, post nothing (no token, no pip installs needed)

Config comes from environment variables (see .env.example):
    IG_USER_ID        Instagram professional account ID (numeric)
    IG_ACCESS_TOKEN   long-lived PAGE access token (does not expire; see setup guide)
    IMAGE_BASE_URL    public URL that serves the content/ folder, no trailing slash
    GRAPH_VERSION     optional, defaults to v23.0
    LAUNCH_DATE       YYYY-MM-DD, day 1 of the calendar (for --today)

Notes: Instagram requires JPEG images; slides are served as slide-N.jpg. The image
folder name must equal the post slug. 'today' is computed in the manifest timezone.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request
import urllib.error

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "posts-manifest.json")
# Instagram API with Instagram Login uses graph.instagram.com + an Instagram user
# token (not a Facebook Page token). The publish flow ({ig-id}/media ->
# media_publish -> comments) is otherwise identical to the Facebook path.
GRAPH = os.environ.get("IG_GRAPH_BASE", "https://graph.instagram.com")


def load_manifest():
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def env(name, required=True, default=None):
    v = os.environ.get(name, default)
    if required and not v:
        sys.exit(f"Missing required env var: {name}")
    return v


def _scrub(msg, token):
    return msg.replace(token, "***TOKEN***") if token else msg


def today_in_tz(manifest):
    tz = manifest.get("timezone", "UTC")
    if ZoneInfo is not None:
        try:
            return dt.datetime.now(ZoneInfo(tz)).date()
        except Exception:
            pass
    return dt.datetime.utcnow().date()


def pick_post(manifest, args):
    """Returns (post, fatal). fatal=True means exit non-zero (misconfig/missing content)."""
    posts = manifest["posts"]
    if args.slug:
        for p in posts:
            if p["slug"] == args.slug:
                return p, False
        print(f"ERROR: no post with slug '{args.slug}' in manifest")
        return None, True

    launch = dt.date.fromisoformat(env("LAUNCH_DATE", default=manifest.get("launch_date")))
    day_index = (today_in_tz(manifest) - launch).days + 1
    last_day = max(p["day"] for p in posts)
    print(f"launch_date={launch}  today(day {day_index} of {last_day})")

    if day_index < 1:
        print("Before launch date. Nothing to do.")
        return None, False
    if day_index > last_day:
        print("Past the end of the posting calendar. Nothing scheduled.")
        return None, False
    for p in posts:
        if p["day"] == day_index:
            if p.get("status") != "ready":
                print(f"ERROR: day {day_index} ('{p['slug']}') is status '{p.get('status')}', not 'ready'.")
                return None, True
            return p, False
    print(f"ERROR: no manifest entry for day {day_index}.")
    return None, True


def slide_urls(base_url, post):
    base = base_url.rstrip("/")
    return [f"{base}/posts/{post['slug']}/slide-{i}.jpg" for i in range(1, post["slides"] + 1)]


def check_url(url):
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            ctype = r.headers.get("Content-Type", "")
            return r.status == 200, ctype
    except urllib.error.HTTPError as e:
        return e.code == 200, ""
    except Exception:
        return False, ""


# ---- Graph API (only imported/used on real publish) ----

def graph_post(version, path, data, token):
    import requests
    try:
        r = requests.post(f"{GRAPH}/{version}/{path}", data=data, timeout=60)
    except Exception as e:
        raise RuntimeError(_scrub(f"network error on POST {path}: {e}", token))
    if r.status_code >= 400:
        raise RuntimeError(f"Graph error {r.status_code} on {path}: {r.text}")
    return r.json()


def graph_get(version, path, params, token):
    import requests
    # token in Authorization header, not the query string (avoids leaking into logs)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{GRAPH}/{version}/{path}", params=params, headers=headers, timeout=60)
    except Exception as e:
        raise RuntimeError(_scrub(f"network error on GET {path}: {e}", token))
    if r.status_code >= 400:
        raise RuntimeError(f"Graph error {r.status_code} on {path}: {r.text}")
    return r.json()


def already_posted(version, ig_id, token, caption):
    """Idempotency guard: skip if a recent post already has this exact caption."""
    try:
        res = graph_get(version, f"{ig_id}/media", {"fields": "caption", "limit": 25}, token)
    except RuntimeError as e:
        print(f"  (idempotency check skipped: {e})")
        return False
    first_line = caption.strip().splitlines()[0]
    for m in res.get("data", []):
        cap = (m.get("caption") or "").strip()
        if cap.startswith(first_line):
            return True
    return False


def wait_finished(version, container_id, token, tries=30, delay=5):
    for _ in range(tries):
        s = graph_get(version, container_id, {"fields": "status_code,status"}, token)
        code = s.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise RuntimeError(f"Container {container_id} failed: {s.get('status')}")
        time.sleep(delay)
    raise RuntimeError(f"Container {container_id} not ready after {tries * delay}s")


def publish(post, dry_run):
    version = os.environ.get("GRAPH_VERSION", "v23.0")
    base_url = os.environ.get("IMAGE_BASE_URL", "")
    if not base_url and not dry_run:
        sys.exit("Missing required env var: IMAGE_BASE_URL")

    urls = slide_urls(base_url, post) if base_url else \
        [f"<IMAGE_BASE_URL>/posts/{post['slug']}/slide-{i}.jpg" for i in range(1, post["slides"] + 1)]

    print(f"\n=== {post['day']:>2}. {post['slug']}  ({post['slides']} slides) ===")
    print("Caption:\n" + post["caption"])
    print("\nFirst comment: " + post["firstComment"])
    print("\nSlide URLs:")
    problems = 0
    for u in urls:
        note = ""
        if base_url:
            ok, ctype = check_url(u)
            if not ok:
                note = "  !! NOT REACHABLE"
                problems += 1
            elif "jpeg" not in ctype.lower():
                note = f"  !! not image/jpeg (got '{ctype}') — Instagram will reject"
                problems += 1
            else:
                note = "  OK"
        print("  " + u + note)

    if dry_run:
        if base_url and problems:
            sys.exit(f"\n[dry-run] {problems} slide URL problem(s). Fix before going live.")
        print("\n[dry-run] Validated. Nothing posted.")
        return
    if problems:
        sys.exit(f"\n{problems} slide URL problem(s). Aborting before publish.")

    ig_id = env("IG_USER_ID")
    token = env("IG_ACCESS_TOKEN")

    if already_posted(version, ig_id, token, post["caption"]):
        print("  Already posted (matching caption found in recent media). Skipping — no duplicate.")
        return

    # 1. one container per slide (poll each to FINISHED)
    child_ids = []
    for u in urls:
        res = graph_post(version, f"{ig_id}/media",
                         {"image_url": u, "is_carousel_item": "true", "access_token": token}, token)
        wait_finished(version, res["id"], token, tries=12, delay=3)
        child_ids.append(res["id"])
        print(f"  container {res['id']} <- {u}")

    # 2. carousel container
    carousel = graph_post(version, f"{ig_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": post["caption"],
        "access_token": token,
    }, token)
    cid = carousel["id"]
    print(f"  carousel container {cid} — waiting for FINISHED...")
    wait_finished(version, cid, token)

    # 3. publish
    published = graph_post(version, f"{ig_id}/media_publish",
                           {"creation_id": cid, "access_token": token}, token)
    media_id = published["id"]
    print(f"  PUBLISHED media {media_id}")

    # 4. first comment (comment-bait). Requires instagram_manage_comments scope.
    #    Cannot PIN via API — pin manually in-app if desired.
    try:
        graph_post(version, f"{media_id}/comments",
                   {"message": post["firstComment"], "access_token": token}, token)
        print("  posted first comment")
    except RuntimeError as e:
        print(f"  (comment skipped — check instagram_manage_comments scope: {e})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true", help="publish the post scheduled for today")
    ap.add_argument("--slug", help="publish a specific post by slug")
    ap.add_argument("--dry-run", action="store_true", help="validate + check URLs, post nothing")
    args = ap.parse_args()
    if not (args.today or args.slug):
        ap.error("pass --today or --slug")

    manifest = load_manifest()
    post, fatal = pick_post(manifest, args)
    if post is None:
        sys.exit(1 if fatal else 0)
    publish(post, args.dry_run)


if __name__ == "__main__":
    main()
