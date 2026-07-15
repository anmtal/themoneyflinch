"""The Money Flinch — automated Instagram carousel publisher.

Official Instagram API (Instagram Login / graph.instagram.com). ToS-legal, no bots.
Posts run on a schedule with no human in the loop.

Modes:
    python publisher.py --due              # publish the next post that is due and not yet posted
    python publisher.py --slug after-check # publish a specific post now
    python publisher.py --check            # read-only: verify the token/account works, post nothing
    python publisher.py --due --dry-run    # show what's due, post nothing (no token needed)

Each post in the manifest has a local 'publish_at' (interpreted in 'timezone').
--due posts the earliest post that is ready, due, and not already on the account
(idempotency guard = matching caption in recent media), one per run. Two-a-day is
achieved by scheduling two publish_at times per day and running the cron often.

Env: IG_USER_ID, IG_ACCESS_TOKEN, IMAGE_BASE_URL, GRAPH_VERSION (opt), IG_GRAPH_BASE (opt).
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


def tzinfo(manifest):
    tz = manifest.get("timezone", "UTC")
    if ZoneInfo is not None:
        try:
            return ZoneInfo(tz)
        except Exception:
            pass
    return dt.timezone.utc


def now_local(manifest):
    return dt.datetime.now(tzinfo(manifest))


def due_dt(post, tz):
    return dt.datetime.fromisoformat(post["publish_at"]).replace(tzinfo=tz)


def first_line(caption):
    s = caption.strip().splitlines()
    return s[0] if s else caption.strip()


# ---- Graph API (only used on real publish/check) ----

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
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{GRAPH}/{version}/{path}", params=params, headers=headers, timeout=60)
    except Exception as e:
        raise RuntimeError(_scrub(f"network error on GET {path}: {e}", token))
    if r.status_code >= 400:
        raise RuntimeError(f"Graph error {r.status_code} on {path}: {r.text}")
    return r.json()


def posted_first_lines(version, ig_id, token):
    res = graph_get(version, f"{ig_id}/media", {"fields": "caption", "limit": 50}, token)
    out = set()
    for m in res.get("data", []):
        cap = (m.get("caption") or "").strip()
        if cap:
            out.add(first_line(cap))
    return out


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


# ---- URLs / validation ----

def slide_urls(base_url, post):
    base = base_url.rstrip("/")
    return [f"{base}/posts/{post['slug']}/slide-{i}.jpg" for i in range(1, post["slides"] + 1)]


def check_url(url):
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code == 200, ""
    except Exception:
        return False, ""


# ---- Selection ----

def pick_due(manifest, posted):
    """Earliest post that is ready, due now, and not already posted."""
    tz = tzinfo(manifest)
    now = now_local(manifest)
    ready = [p for p in manifest["posts"] if p.get("status") == "ready" and "publish_at" in p]
    ready.sort(key=lambda p: p["publish_at"])
    for p in ready:
        if due_dt(p, tz) <= now and first_line(p["caption"]) not in posted:
            return p
    return None


# ---- Actions ----

def do_check(manifest):
    version = os.environ.get("GRAPH_VERSION", "v23.0")
    ig_id = env("IG_USER_ID")
    token = env("IG_ACCESS_TOKEN")
    res = graph_get(version, ig_id, {"fields": "username,media_count"}, token)
    print(f"OK — token valid. account @{res.get('username')} "
          f"(id {ig_id}), media_count={res.get('media_count')}")


def video_url(base_url, post):
    return f"{base_url.rstrip('/')}/reels/{post['slug']}.mp4"


def _post_comment(version, media_id, message, token):
    try:
        graph_post(version, f"{media_id}/comments",
                   {"message": message, "access_token": token}, token)
        print("  posted first comment")
    except RuntimeError as e:
        print(f"  (comment skipped: {e})")


def publish(manifest, post, dry_run):
    version = os.environ.get("GRAPH_VERSION", "v23.0")
    base_url = os.environ.get("IMAGE_BASE_URL", "")
    if not base_url and not dry_run:
        sys.exit("Missing required env var: IMAGE_BASE_URL")
    ptype = post.get("type", "carousel")

    print(f"\n=== {post['slug']}  [{ptype}]  @ {post.get('publish_at','?')} ===")
    print("Caption:\n" + post["caption"])
    print("\nFirst comment: " + post["firstComment"])

    # ---------- REEL ----------
    if ptype == "reel":
        url = video_url(base_url, post) if base_url else f"<IMAGE_BASE_URL>/reels/{post['slug']}.mp4"
        problems = 0
        print("\nVideo:")
        if base_url:
            ok, ctype = check_url(url)
            cl = ctype.lower()
            if not ok:
                problems += 1; print("  " + url + "  !! NOT REACHABLE")
            elif not any(x in cl for x in ("mp4", "video", "octet-stream")):
                problems += 1; print("  " + url + f"  !! not a video ({ctype})")
            else:
                print("  " + url + "  OK")
        else:
            print("  " + url)
        if dry_run:
            if base_url and problems:
                sys.exit(f"\n[dry-run] {problems} video problem(s).")
            print("\n[dry-run] Validated. Nothing posted."); return
        if problems:
            sys.exit(f"\n{problems} video problem(s). Aborting.")
        ig_id = env("IG_USER_ID"); token = env("IG_ACCESS_TOKEN")
        res = graph_post(version, f"{ig_id}/media",
                         {"media_type": "REELS", "video_url": url, "caption": post["caption"],
                          "share_to_feed": "true", "access_token": token}, token)
        cid = res["id"]
        print(f"  reel container {cid} — processing video (can take a minute)...")
        wait_finished(version, cid, token, tries=60, delay=6)   # video processing is slower
        published = graph_post(version, f"{ig_id}/media_publish",
                               {"creation_id": cid, "access_token": token}, token)
        media_id = published["id"]
        print(f"  PUBLISHED reel {media_id}")
        _post_comment(version, media_id, post["firstComment"], token)
        return

    # ---------- CAROUSEL (default) ----------
    urls = slide_urls(base_url, post) if base_url else \
        [f"<IMAGE_BASE_URL>/posts/{post['slug']}/slide-{i}.jpg" for i in range(1, post["slides"] + 1)]
    problems = 0
    print("\nSlides:")
    for u in urls:
        note = ""
        if base_url:
            ok, ctype = check_url(u)
            if not ok:
                note, problems = "  !! NOT REACHABLE", problems + 1
            elif "jpeg" not in ctype.lower():
                note, problems = f"  !! not image/jpeg ({ctype})", problems + 1
            else:
                note = "  OK"
        print("  " + u + note)

    if dry_run:
        if base_url and problems:
            sys.exit(f"\n[dry-run] {problems} slide problem(s).")
        print("\n[dry-run] Validated. Nothing posted.")
        return
    if problems:
        sys.exit(f"\n{problems} slide problem(s). Aborting before publish.")

    ig_id = env("IG_USER_ID")
    token = env("IG_ACCESS_TOKEN")

    child_ids = []
    for u in urls:
        res = graph_post(version, f"{ig_id}/media",
                         {"image_url": u, "is_carousel_item": "true", "access_token": token}, token)
        wait_finished(version, res["id"], token, tries=12, delay=3)
        child_ids.append(res["id"])
        print(f"  container {res['id']} <- {u}")

    carousel = graph_post(version, f"{ig_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": post["caption"],
        "access_token": token,
    }, token)
    cid = carousel["id"]
    print(f"  carousel container {cid} — waiting for FINISHED...")
    wait_finished(version, cid, token)

    published = graph_post(version, f"{ig_id}/media_publish",
                           {"creation_id": cid, "access_token": token}, token)
    media_id = published["id"]
    print(f"  PUBLISHED media {media_id}")
    _post_comment(version, media_id, post["firstComment"], token)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--due", action="store_true", help="publish the next due, unposted item")
    ap.add_argument("--slug", help="publish a specific post by slug")
    ap.add_argument("--check", action="store_true", help="read-only token/account check; posts nothing")
    ap.add_argument("--dry-run", action="store_true", help="validate + print, post nothing")
    args = ap.parse_args()

    manifest = load_manifest()

    if args.check:
        do_check(manifest)
        return

    if args.slug:
        post = next((p for p in manifest["posts"] if p["slug"] == args.slug), None)
        if not post:
            sys.exit(f"no post with slug '{args.slug}'")
        publish(manifest, post, args.dry_run)
        return

    if args.due:
        if args.dry_run:
            # can't read the account without a token; show due-by-time only
            tz = tzinfo(manifest)
            now = now_local(manifest)
            due = [p for p in manifest["posts"]
                   if p.get("status") == "ready" and due_dt(p, tz) <= now]
            print(f"now={now.isoformat()}  due-by-time: {[p['slug'] for p in due] or 'none'}")
            if due:
                publish(manifest, sorted(due, key=lambda p: p['publish_at'])[0], True)
            return
        ig_id = env("IG_USER_ID")
        token = env("IG_ACCESS_TOKEN")
        version = os.environ.get("GRAPH_VERSION", "v23.0")
        posted = posted_first_lines(version, ig_id, token)
        post = pick_due(manifest, posted)
        if post is None:
            print(f"{now_local(manifest).isoformat()} — nothing due to post. Done.")
            return
        publish(manifest, post, False)
        return

    ap.error("pass --due, --slug, or --check")


if __name__ == "__main__":
    main()
