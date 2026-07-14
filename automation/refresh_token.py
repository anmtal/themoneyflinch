"""Refresh the long-lived Instagram user token and update the GitHub secret.

Instagram user tokens last ~60 days but can be renewed for another 60 days
indefinitely (token must be >24h old and still valid). Run monthly in Actions
so the token effectively never expires, with zero manual work.

Env: IG_ACCESS_TOKEN (current token), GH_TOKEN (PAT that can write the secret),
     GITHUB_REPOSITORY (auto-set in Actions), IG_GRAPH_BASE (optional).
"""
import os
import subprocess
import sys

import requests

BASE = os.environ.get("IG_GRAPH_BASE", "https://graph.instagram.com")


def main():
    token = os.environ.get("IG_ACCESS_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        sys.exit("need IG_ACCESS_TOKEN and GITHUB_REPOSITORY")

    r = requests.get(
        f"{BASE}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=60,
    )
    data = {}
    try:
        data = r.json()
    except Exception:
        pass
    new = data.get("access_token")
    if r.status_code >= 400 or not new:
        msg = r.text.replace(token, "***") if token else r.text
        sys.exit(f"refresh failed ({r.status_code}): {msg}")

    days = int(data.get("expires_in", 0)) // 86400
    print(f"refreshed OK; new token valid ~{days} days")

    # Update the secret. Value passed via stdin so it never lands in argv or logs.
    p = subprocess.run(
        ["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", repo],
        input=new, text=True,
    )
    if p.returncode != 0:
        sys.exit("gh secret set failed (check GH_PAT has Secrets: write on this repo)")
    print("IG_ACCESS_TOKEN secret updated — token renewed for another ~60 days")


if __name__ == "__main__":
    main()
