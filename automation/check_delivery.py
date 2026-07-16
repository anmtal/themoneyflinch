"""Alert if the account has gone dark.

check_buffer.py measures INVENTORY — how much content is left. That says nothing
about whether anything actually reached Instagram. Both misses so far were silent
in exactly this way: the queue was full, the runs were green, and no reel posted.
This watches the only thing that actually matters — the timestamp of the last
successful publish — and shouts if it goes stale.

Posts go out at 12:00 and 20:00 local, so the longest healthy gap is 16h (20:00 to
the next 12:00). 26h leaves comfortable slack while still catching a miss within
one cycle.

Env: GH_TOKEN (to open the issue), GITHUB_REPOSITORY.
"""
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAST_POST = os.path.join(ROOT, "content", "last-post.json")
MAX_SILENCE_HOURS = 26
TITLE = "Money Flinch: nothing has posted recently"
REPO = os.environ.get("GITHUB_REPOSITORY", "")


def gh(*a):
    return subprocess.run(["gh"] + list(a), capture_output=True, text=True)


def alert(body):
    print("ALERT:", body.splitlines()[0])
    if not REPO or not os.environ.get("GH_TOKEN"):
        print("(no GH_TOKEN/repo — not opening an issue)")
        return
    found = gh("issue", "list", "--repo", REPO, "--state", "open",
               "--search", f"{TITLE} in:title", "--json", "number", "-q", ".[0].number")
    num = found.stdout.strip()
    if num:
        # Comment rather than skip: a silently-suppressed alert is how a dark
        # account stays dark. Every check must produce a fresh notification.
        gh("issue", "comment", num, "--repo", REPO, "--body", body)
        print(f"commented on existing issue #{num}")
    else:
        gh("issue", "create", "--repo", REPO, "--title", TITLE, "--body", body)
        print("opened a new issue")


def main():
    now = dt.datetime.now(dt.timezone.utc)

    if not os.path.exists(LAST_POST):
        print("no last-post.json yet — nothing has been recorded by the new publisher. OK for now.")
        return

    try:
        with open(LAST_POST, encoding="utf-8") as f:
            d = json.load(f)
        last = dt.datetime.fromisoformat(d["published_at"])
    except Exception as e:
        alert(f"last-post.json is unreadable ({e}). The delivery watchdog is blind — check the repo.")
        sys.exit(1)

    if last.tzinfo is None:
        last = last.replace(tzinfo=dt.timezone.utc)
    hours = (now - last).total_seconds() / 3600
    print(f"last publish: {d.get('slug')} at {d['published_at']} ({hours:.1f}h ago)")

    if hours > MAX_SILENCE_HOURS:
        alert(
            f"Nothing has posted to @themoneyflinch in {hours:.0f} hours "
            f"(last: `{d.get('slug')}` at {d['published_at']} UTC).\n\n"
            f"Expected cadence is 2/day at 12:00 and 20:00 Eastern, so anything over "
            f"{MAX_SILENCE_HOURS}h means the scheduler is stuck.\n\n"
            f"Check, in order:\n"
            f"1. The **Money Flinch scheduler** workflow runs — are they failing?\n"
            f"2. `content/failed.json` — is a post quarantined?\n"
            f"3. The token — run the scheduler manually with mode `check`.\n"
            f"4. cron-job.org — are the 12:00/20:00 triggers still firing?"
        )
        sys.exit(1)

    print("delivery OK")


if __name__ == "__main__":
    main()
