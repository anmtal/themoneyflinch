"""Read-only account diagnostics: followers, per-post engagement, reel insights.

Posts NOTHING. Prints a JSON block to the run log so we can judge how the page is
actually doing instead of guessing. Uses the same Instagram Login token as the
publisher. Insight metrics vary by scope/media type, so each is fetched
defensively — a missing metric is reported, never fatal.

Env: IG_USER_ID, IG_ACCESS_TOKEN, GRAPH_VERSION (opt), IG_GRAPH_BASE (opt).
"""
import json
import os
import sys

import requests

GRAPH = os.environ.get("IG_GRAPH_BASE", "https://graph.instagram.com")
VERSION = os.environ.get("GRAPH_VERSION", "v23.0")
IG_ID = os.environ.get("IG_USER_ID")
TOKEN = os.environ.get("IG_ACCESS_TOKEN")


def get(path, params=None):
    p = dict(params or {})
    p["access_token"] = TOKEN
    r = requests.get(f"{GRAPH}/{VERSION}/{path}", params=p, timeout=60)
    if r.status_code >= 400:
        return {"_error": f"{r.status_code}: {r.text[:300]}"}
    return r.json()


def first_line(cap):
    cap = (cap or "").strip()
    return cap.splitlines()[0] if cap else ""


def main():
    if not IG_ID or not TOKEN:
        sys.exit("Missing IG_USER_ID / IG_ACCESS_TOKEN")

    prof = get(IG_ID, {"fields": "username,account_type,media_count,followers_count,follows_count"})
    out = {"profile": prof, "posts": []}

    media = get(f"{IG_ID}/media", {
        "fields": "id,media_type,media_product_type,caption,like_count,comments_count,timestamp,permalink",
        "limit": 50,
    })
    for m in media.get("data", []):
        row = {
            "id": m.get("id"),
            "type": m.get("media_product_type") or m.get("media_type"),
            "when": m.get("timestamp"),
            "hook": first_line(m.get("caption"))[:80],
            "likes": m.get("like_count"),
            "comments": m.get("comments_count"),
            "permalink": m.get("permalink"),
        }
        # Reel/video insights — try a broad set, keep whatever the API returns.
        metrics = "views,reach,total_interactions,saved,shares,likes,comments,ig_reels_avg_watch_time"
        ins = get(f"{m['id']}/insights", {"metric": metrics})
        got = {}
        if "data" in ins:
            for item in ins["data"]:
                vals = item.get("values") or [{}]
                got[item.get("name")] = vals[0].get("value")
        elif "_error" in ins:
            got = {"_insights_error": ins["_error"]}
        row["insights"] = got
        out["posts"].append(row)

    print("=== ACCOUNT STATS JSON START ===")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("=== ACCOUNT STATS JSON END ===")

    # human summary
    p = prof
    print(f"\n@{p.get('username')}  followers={p.get('followers_count')}  "
          f"following={p.get('follows_count')}  live_posts={p.get('media_count')}")
    for r in out["posts"]:
        ins = r["insights"]
        v = ins.get("views") or ins.get("reach") or "?"
        print(f"  {r['when']}  {r['type']:6}  views/reach={v}  likes={r['likes']}  "
              f"comments={r['comments']}  saved={ins.get('saved','?')}  shares={ins.get('shares','?')}"
              f"  | {r['hook']}")


if __name__ == "__main__":
    main()
