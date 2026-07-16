"""Commit and push the run's durable logs, merging with whatever landed on origin.

Why this exists instead of `git pull --rebase && git push`:

posted.json writes one slug per line, so two runs recording DIFFERENT slugs from
the same base commit touch the same lines and rebase CONFLICTS. A conflicted
rebase exits 128, the step fails, and the record of a post that is already live on
Instagram is lost forever — which resurfaces as a duplicate once the caption ages
out of the 50-post lookback. Rebase is simply the wrong merge for this data.

posted.json is an append-only SET. The correct merge is a union, and a union can
never conflict. So on a rejected push we re-read origin's copy, union it with
ours, and retry.

Usage: python automation/commit_logs.py [branch]
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCH = sys.argv[1] if len(sys.argv) > 1 else "main"

POSTED = "content/posted.json"
FAILED = "content/failed.json"
LAST = "content/last-post.json"
MANIFEST = "automation/posts-manifest.json"
TRACKED = [POSTED, FAILED, LAST, MANIFEST]
ATTEMPTS = 5


def git(*a, check=True):
    r = subprocess.run(["git"] + list(a), cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)} failed: {r.stderr.strip()}")
    return r


def read_local(path):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def read_origin(path):
    r = git("show", f"origin/{BRANCH}:{path}", check=False)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def write(path, obj):
    with open(os.path.join(ROOT, path), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def reunion():
    """Fold origin's records into ours. Never drops a slug either side recorded."""
    ours, theirs = read_local(POSTED), read_origin(POSTED)
    if isinstance(ours, list) and isinstance(theirs, list):
        write(POSTED, sorted(set(ours) | set(theirs)))

    ours, theirs = read_local(FAILED), read_origin(FAILED)
    if isinstance(ours, dict) and isinstance(theirs, dict):
        merged = dict(theirs)
        for slug, entry in ours.items():
            other = merged.get(slug)
            if not isinstance(other, dict) or \
               int(entry.get("attempts", 0)) >= int(other.get("attempts", 0)):
                merged[slug] = entry          # keep the higher attempt count
        write(FAILED, merged)


def sane_posted():
    """Never let a malformed log reach main — load_posted() halts the publisher on
    a corrupt file, which would take the whole account dark until someone noticed."""
    d = read_local(POSTED)
    if d is None:
        return True                            # nothing to commit yet is fine
    return isinstance(d, list) and all(isinstance(x, str) for x in d)


def main():
    git("config", "user.name", "flinch-bot")
    git("config", "user.email", "flinch-bot@users.noreply.github.com")

    for attempt in range(ATTEMPTS):
        present = [p for p in TRACKED if os.path.exists(os.path.join(ROOT, p))]
        if present:
            git("add", *present, check=False)
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            print("logs: nothing to record")
            return
        if not sane_posted():
            sys.exit(f"{POSTED} is malformed — refusing to commit it.")

        git("commit", "-m", "chore: record posted content")
        if git("push", "origin", f"HEAD:{BRANCH}", check=False).returncode == 0:
            print(f"logs: pushed on attempt {attempt + 1}")
            return

        print(f"logs: push rejected (attempt {attempt + 1}/{ATTEMPTS}) — merging with origin")
        git("fetch", "origin", BRANCH)
        git("reset", "--soft", f"origin/{BRANCH}")   # keep our files, sit on origin's tip
        git("reset", check=False)                    # unstage; working tree keeps our version
        reunion()
        time.sleep(2 + 3 * attempt)

    sys.exit("FAILED to push the posted log after "
             f"{ATTEMPTS} attempts — a post may be LIVE but unrecorded. Fix this before the next run.")


if __name__ == "__main__":
    main()
