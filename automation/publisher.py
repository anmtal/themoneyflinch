"""The Money Flinch — automated Instagram publisher (reels + carousels).

Official Instagram API (Instagram Login / graph.instagram.com). ToS-legal, no bots.
Posts run on a schedule with no human in the loop.

Modes:
    python publisher.py --due              # publish the next post that is due and not yet posted
    python publisher.py --slug after-check # publish a specific post now (refuses if already posted)
    python publisher.py --check            # read-only: verify the token/account works, post nothing
    python publisher.py --due --dry-run    # show what's due, post nothing (no token needed)

Each post in the manifest has a local 'publish_at' (interpreted in 'timezone').
--due posts the earliest post that is ready, due, and not already published,
one per run. Two-a-day comes from two publish_at times per day + a frequent cron.

Idempotency has two layers, in this order:
  1. content/posted.json — the permanent record of what we published. Authoritative.
  2. the last 50 live captions on the account — a backstop for the gap between
     media_publish returning and posted.json being committed.
Layer 2 alone is NOT enough: deleting a post from Instagram makes its caption
disappear, and the account only exposes recent media. Layer 1 is why deleting a
reel by hand never causes an automated re-post.

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
CONTENT = os.path.join(os.path.dirname(HERE), "content")
MANIFEST = os.path.join(HERE, "posts-manifest.json")
POSTED_LOG = os.path.join(CONTENT, "posted.json")      # slugs we have published — authoritative
FAILED_LOG = os.path.join(CONTENT, "failed.json")      # {slug: {attempts, last_error}} — quarantine counter
LAST_POST_LOG = os.path.join(CONTENT, "last-post.json")  # heartbeat for the delivery watchdog
GRAPH = os.environ.get("IG_GRAPH_BASE", "https://graph.instagram.com")

MAX_ATTEMPTS = 3      # after this many failures a post is quarantined so the queue advances
GRACE_HOURS = 6       # a post more than this late is rescheduled, not fired off-hours
SLOT_HOURS = (12, 20)  # the only times of day we ever publish (local tz)


# ---- Durable state ----

def _write_json_atomic(path, obj):
    """Write via a temp file + os.replace.

    A plain open(path, "w") truncates immediately, so a process killed mid-write
    leaves a half-written file on disk. For posted.json that is catastrophic: the
    truncated log parses as nothing, every slug looks unposted, and the whole back
    catalogue re-posts. os.replace is atomic — readers see the old file or the new
    one, never a partial one.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_posted():
    """Slugs already published.

    A missing file means a legitimate first run. A corrupt file is FATAL on purpose:
    returning an empty set for unreadable input would be a fail-open that re-posts
    everything we have ever published. Halting is always the safe direction here.
    """
    if not os.path.exists(POSTED_LOG):
        return set()
    try:
        with open(POSTED_LOG, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"posted.json is corrupt ({e}) — refusing to run. "
                 f"Restore it: git checkout <last-good-sha> -- content/posted.json")
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        sys.exit("posted.json is not a list of strings — refusing to run rather than risk re-posting.")
    return set(data)


def mark_posted(slug):
    posted = load_posted()
    posted.add(slug)
    _write_json_atomic(POSTED_LOG, sorted(posted))


def load_failed():
    """Failure counters. Unlike posted.json this fails OPEN by design: the worst
    case of losing it is that we retry a post, not that we duplicate one."""
    try:
        with open(FAILED_LOG, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def attempts_of(failed, slug):
    e = failed.get(slug)
    return int(e.get("attempts", 0)) if isinstance(e, dict) else 0


def record_failure(slug, err):
    failed = load_failed()
    entry = failed.get(slug) if isinstance(failed.get(slug), dict) else {}
    entry["attempts"] = attempts_of(failed, slug) + 1
    entry["last_error"] = str(err)[:300]
    entry["last_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    failed[slug] = entry
    _write_json_atomic(FAILED_LOG, failed)
    return entry["attempts"]


def clear_failure(slug):
    failed = load_failed()
    if slug in failed:
        del failed[slug]
        _write_json_atomic(FAILED_LOG, failed)


def record_delivery(slug, media_id):
    """Heartbeat: the last time anything actually reached Instagram. The buffer alert
    measures inventory, which says nothing about delivery — both silent misses so far
    had a full queue and green runs. The watchdog reads this."""
    _write_json_atomic(LAST_POST_LOG, {
        "slug": slug,
        "media_id": str(media_id),
        "published_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    })


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


def find_live_media(version, ig_id, token, post):
    """Media id of a live post matching this caption, or None.

    Used to resolve the ambiguity when media_publish throws: the request may have
    succeeded and only the response was lost. An unrecorded-but-live post is the
    seed of a duplicate weeks later, so we always go and look before giving up.
    """
    try:
        res = graph_get(version, f"{ig_id}/media", {"fields": "caption,id", "limit": 5}, token)
    except Exception:
        return None
    want = first_line(post["caption"])
    for m in res.get("data", []):
        if first_line((m.get("caption") or "").strip()) == want:
            return m.get("id")
    return None


# ---- URLs / validation ----

def slide_urls(base_url, post):
    base = base_url.rstrip("/")
    return [f"{base}/posts/{post['slug']}/slide-{i}.jpg" for i in range(1, post["slides"] + 1)]


def check_url(url, tries=3):
    """(ok, content_type, fatal).

    fatal=True only for 404/410 — the file is genuinely gone and publishing would
    fail anyway. Everything else (timeout, 429, 5xx) is transient and returns
    ok=False/fatal=False: we let Instagram's own fetcher decide, because a blip on
    a HEAD check must not abort a publish. A container IG truly cannot fetch errors
    out at wait_finished, which is the honest place to fail.
    """
    last = None
    for i in range(tries):
        req = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status == 200, r.headers.get("Content-Type", ""), False
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return False, "", True
            last = f"HTTP {e.code}"
        except Exception as e:
            last = str(e)
        if i < tries - 1:
            time.sleep(1 + 4 * i)
    print(f"  (HEAD check inconclusive after {tries} tries: {last})")
    return False, "", False


def report_url(url, kind, want):
    """Print + validate one asset URL. Returns 1 if it's a real problem, else 0."""
    ok, ctype, fatal = check_url(url)
    if fatal:
        print(f"  {url}  !! NOT REACHABLE (gone)")
        return 1
    if not ok:
        print(f"  {url}  (unverified — letting Instagram fetch it)")
        return 0
    if ctype and not any(x in ctype.lower() for x in want):
        print(f"  {url}  !! not {kind} ({ctype})")
        return 1
    print(f"  {url}  OK")
    return 0


# ---- Selection ----

def is_stale(post, tz, now):
    return now - due_dt(post, tz) > dt.timedelta(hours=GRACE_HOURS)


def pick_due(manifest, posted_captions, posted_slugs, failed=None, now=None):
    """Earliest post that is ready, due, not already published, not quarantined,
    and not so late that firing it now would post at a random hour."""
    failed = failed or {}
    tz = tzinfo(manifest)
    now = now or now_local(manifest)
    ready = [p for p in manifest["posts"] if p.get("status") == "ready" and "publish_at" in p]
    ready.sort(key=lambda p: p["publish_at"])
    for p in ready:
        if p["slug"] in posted_slugs:
            continue
        if attempts_of(failed, p["slug"]) >= MAX_ATTEMPTS:
            continue   # quarantined: it would otherwise block everything behind it forever
        if first_line(p["caption"]) in posted_captions:
            continue
        d = due_dt(p, tz)
        if d > now:
            continue
        if is_stale(p, tz, now):
            continue   # reschedule_stale() moves these; never dump a backlog at 2/hour
        return p
    return None


def next_free_slot(manifest, tz, after):
    """First 12:00/20:00 slot strictly after `after` that no post already occupies."""
    taken = {p.get("publish_at") for p in manifest["posts"]}
    day = after.date()
    for _ in range(120):
        for h in SLOT_HOURS:
            cand = dt.datetime.combine(day, dt.time(h, 0))
            if cand.replace(tzinfo=tz) > after and cand.isoformat() not in taken:
                return cand.isoformat()
        day += dt.timedelta(days=1)
    return None


def reschedule_stale(manifest, posted_slugs, failed, now=None):
    """Move posts more than GRACE_HOURS late to the back of the queue.

    Without this, any outage turns the */30 cron into a firehose: pick_due would
    return backlogged post after backlogged post and drain days of content at two
    reels an HOUR, at 3am, which reads as spam. Rescheduling (rather than skipping)
    means no content is ever lost — it just goes out later, still at 12:00/20:00.
    """
    tz = tzinfo(manifest)
    now = now or now_local(manifest)
    moved = []
    for p in manifest["posts"]:
        if p.get("status") != "ready" or "publish_at" not in p:
            continue
        if p["slug"] in posted_slugs or attempts_of(failed, p["slug"]) >= MAX_ATTEMPTS:
            continue
        if due_dt(p, tz) > now or not is_stale(p, tz, now):
            continue
        latest = max(q["publish_at"] for q in manifest["posts"] if "publish_at" in q)
        anchor = max(dt.datetime.fromisoformat(latest).replace(tzinfo=tz), now)
        slot = next_free_slot(manifest, tz, anchor)
        if not slot:
            continue
        moved.append((p["slug"], p["publish_at"], slot))
        p["publish_at"] = slot
    if moved:
        _write_json_atomic(MANIFEST, manifest)
        for slug, old, new in moved:
            print(f"  rescheduled {slug}: {old} -> {new} (was more than {GRACE_HOURS}h late)")
    return moved


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


def _publish_container(version, ig_id, cid, token, post):
    """media_publish, resolving the lost-response case. Returns the media id."""
    try:
        return graph_post(version, f"{ig_id}/media_publish",
                          {"creation_id": cid, "access_token": token}, token)["id"]
    except Exception as e:
        time.sleep(10)
        live = find_live_media(version, ig_id, token, post)
        if live:
            print(f"  publish call errored ({e}) but the post IS live as {live} — recording it")
            return live
        raise


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
            problems = report_url(url, "a video", ("mp4", "video", "octet-stream"))
        else:
            print("  " + url)
        if dry_run:
            if problems:
                sys.exit(f"\n[dry-run] {problems} video problem(s).")
            print("\n[dry-run] Validated. Nothing posted.")
            return
        if problems:
            sys.exit(f"\n{problems} video problem(s). Aborting.")
        ig_id = env("IG_USER_ID"); token = env("IG_ACCESS_TOKEN")
        res = graph_post(version, f"{ig_id}/media",
                         {"media_type": "REELS", "video_url": url, "caption": post["caption"],
                          "share_to_feed": "true", "access_token": token}, token)
        cid = res["id"]
        print(f"  reel container {cid} — processing video (can take a minute)...")
        wait_finished(version, cid, token, tries=60, delay=6)   # video processing is slower
        media_id = _publish_container(version, ig_id, cid, token, post)
        print(f"  PUBLISHED reel {media_id}")
        mark_posted(post["slug"])            # record BEFORE the comment: a failed comment
        record_delivery(post["slug"], media_id)  # must never make us re-post the reel
        _post_comment(version, media_id, post["firstComment"], token)
        return

    # ---------- CAROUSEL (default) ----------
    urls = slide_urls(base_url, post) if base_url else \
        [f"<IMAGE_BASE_URL>/posts/{post['slug']}/slide-{i}.jpg" for i in range(1, post["slides"] + 1)]
    problems = 0
    print("\nSlides:")
    for u in urls:
        if base_url:
            problems += report_url(u, "image/jpeg", ("jpeg",))
        else:
            print("  " + u)

    if dry_run:
        if problems:
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

    media_id = _publish_container(version, ig_id, cid, token, post)
    print(f"  PUBLISHED media {media_id}")
    mark_posted(post["slug"])
    record_delivery(post["slug"], media_id)
    _post_comment(version, media_id, post["firstComment"], token)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--due", action="store_true", help="publish the next due, unposted item")
    ap.add_argument("--slug", help="publish a specific post by slug")
    ap.add_argument("--force", action="store_true", help="with --slug: publish even if already posted")
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
        # "Re-run all jobs" on an old workflow_dispatch replays --slug against a live
        # account, so --slug honours the log too. --force is the explicit override.
        if not args.dry_run and not args.force and post["slug"] in load_posted():
            sys.exit(f"{args.slug} is already in posted.json — pass --force to publish it anyway")
        publish(manifest, post, args.dry_run)
        return

    if args.due:
        if args.dry_run:
            # can't read the account without a token; show due-by-time only
            tz = tzinfo(manifest)
            now = now_local(manifest)
            posted_slugs = load_posted()
            failed = load_failed()
            due = [p for p in manifest["posts"]
                   if p.get("status") == "ready" and p["slug"] not in posted_slugs
                   and due_dt(p, tz) <= now and not is_stale(p, tz, now)]
            print(f"now={now.isoformat()}  due-by-time: {[p['slug'] for p in due] or 'none'}")
            if due:
                publish(manifest, sorted(due, key=lambda p: p['publish_at'])[0], True)
            return

        ig_id = env("IG_USER_ID")
        token = env("IG_ACCESS_TOKEN")
        version = os.environ.get("GRAPH_VERSION", "v23.0")
        posted_slugs = load_posted()
        failed = load_failed()
        reschedule_stale(manifest, posted_slugs, failed)
        posted_captions = posted_first_lines(version, ig_id, token)
        post = pick_due(manifest, posted_captions, posted_slugs, failed)
        if post is None:
            print(f"{now_local(manifest).isoformat()} — nothing due to post. Done.")
            return

        # One post per run, always. A failure here records an attempt rather than
        # retrying in-process: after MAX_ATTEMPTS the slug is quarantined and the
        # queue moves on, so one bad post can never wedge everything behind it.
        try:
            publish(manifest, post, False)
        except (SystemExit, Exception) as e:
            reason = getattr(e, "code", None) or e
            if reason in (0, None):
                raise
            n = record_failure(post["slug"], reason)
            print(f"\n!! {post['slug']} failed (attempt {n}/{MAX_ATTEMPTS}): {reason}")
            if n >= MAX_ATTEMPTS:
                print(f"!! quarantining {post['slug']} — the queue will skip it and carry on. "
                      f"Fix it, then remove it from content/failed.json to re-enable.")
            sys.exit(1)
        clear_failure(post["slug"])
        return

    ap.error("pass --due, --slug, or --check")


if __name__ == "__main__":
    main()
