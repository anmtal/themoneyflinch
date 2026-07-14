# Auto-Posting Setup Guide

This turns The Money Flinch into a hands-off machine: every day at 7:00pm, a free
cloud job publishes the scheduled carousel to Instagram and posts your comment-bait
line — while your computer is off.

**What the machine does for you (already built):**
- Renders the carousels (the generators)
- Hosts the images (GitHub)
- Publishes daily on schedule (GitHub Actions + Instagram Graph API)
- Posts the first comment (the bait)

**What only you can do (this guide — ~40 minutes, one time, free):**
1. Connect Instagram to a Facebook Page
2. Create a Meta developer app + access token
3. Put the code on GitHub with your secrets

Nothing here costs money. You never give me your password — you generate the token
yourself and paste it into GitHub.

---

## Step 1 — Instagram must be Professional + linked to a Facebook Page

The Graph API only publishes from a Professional (Business/Creator) account that is
connected to a Facebook Page. You already switched to Professional. Now:

1. Create a Facebook Page (free): facebook.com → Pages → Create → name it "The Money Flinch."
2. In the Instagram app: **Settings → Accounts Center → Connected experiences → Add accounts**, and connect that Page.

Confirm: Instagram app → **Edit profile → Page** shows your Page linked.

> **This Facebook Page is never posted to.** It exists only because Instagram's API
> requires a linked Page to authorize publishing. The publisher only ever calls
> Instagram endpoints (`/media`, `/media_publish`, `/comments`) — it touches no
> Facebook-posting endpoint. Leave the Page empty; nothing will ever appear on it.
> If you'd prefer it not be findable at all, set the Page to **unpublished**
> (Page → Settings → Privacy → "Page visibility" → Unpublished) — API publishing to
> Instagram still works while the Page is hidden.

---

## Step 2 — Create a Meta developer app

1. Go to **developers.facebook.com** → log in with the same Facebook account → **My Apps → Create App**.
2. Use case: choose **"Other"** → type **"Business."**
3. Name it "money-flinch-poster." Create.
4. In the app dashboard → **Add Product** → add **"Instagram Graph API"** (and "Facebook Login for Business" if prompted).

---

## Step 3 — Get a long-lived access token

Easiest path is the Graph API Explorer:

1. App dashboard → **Tools → Graph API Explorer**.
2. Top-right: select your app.
3. **Add permissions** (Permissions dropdown): `instagram_basic`, `instagram_content_publish`, `instagram_manage_comments`, `pages_show_list`, `pages_read_engagement`, `business_management`.
   (`instagram_manage_comments` is what lets the machine post your comment-bait line. Without it the carousel still posts but the first comment silently fails.)
4. Click **Generate Access Token** → approve the popup (select your Page and IG account). Confirm the token is for the right account by clicking **Submit** on the default `me` query — it should return your name.
5. This gives a SHORT-lived token (~1 hour). Exchange it for a LONG-lived one — paste this in your browser, replacing the three values:

   ```
   https://graph.facebook.com/v23.0/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=SHORT_LIVED_TOKEN
   ```

   (App ID + secret are in **App settings → Basic**.) The response contains a
   long-lived **user** token (~60 days).

6. **Get the non-expiring PAGE token** (do this — it saves you re-doing step 3 every 60 days).
   Paste, replacing with the long-lived user token from above:
   ```
   https://graph.facebook.com/v23.0/me/accounts?access_token=YOUR_LONG_LIVED_USER_TOKEN
   ```
   In the response, find your Page and copy its `access_token`. **This Page token does
   not expire** as long as the app stays active. This is your `IG_ACCESS_TOKEN`.

---

## Step 4 — Get your Instagram account ID

Paste in your browser, replacing the token:

```
https://graph.facebook.com/v23.0/me/accounts?access_token=YOUR_LONG_LIVED_TOKEN
```

Copy the Page `id` from the response, then:

```
https://graph.facebook.com/v23.0/PAGE_ID?fields=instagram_business_account&access_token=YOUR_LONG_LIVED_TOKEN
```

The `instagram_business_account.id` it returns is your `IG_USER_ID` (a long number).

---

## Step 5 — Put the project on GitHub (this also hosts the images)

Instagram's API fetches images from public URLs, so the repo does double duty: it stores
the code AND serves the slide JPGs.

1. Create a free account at **github.com** if you don't have one.
2. Create a new **public** repository named `themoneyflinch`.
   (Public is required so Instagram can read the image URLs.)
3. Upload this whole `IG Automation` folder to the repo (drag-and-drop in the GitHub web
   UI works). Make sure `content/posts/...`, `automation/`, `.gitignore`, and
   `.github/workflows/daily-post.yml` are included.

> **Never upload a `.env` file.** Your access token belongs ONLY in GitHub Secrets
> (Step 6), never in a file in the repo. There is a `.gitignore` that excludes `.env`,
> but GitHub's web drag-and-drop **ignores `.gitignore`** — so if a `.env` exists in the
> folder you drag, it WILL be published to the public repo. Before uploading, make sure
> no `.env` file exists in the folder. (The publisher never reads `.env`; it only reads
> GitHub Secrets. The `.env.example` file is safe — it has no real values.)

Your `IMAGE_BASE_URL` is then:
```
https://raw.githubusercontent.com/YOUR_USERNAME/themoneyflinch/main/content
```
Test it: open `IMAGE_BASE_URL/posts/after-check/slide-1.jpg` in a browser — you should
see the Day 1 cover. (If it 404s, the folder or filename is wrong; fix before going live.)

---

## Step 6 — Add your secrets and schedule

In the GitHub repo → **Settings → Secrets and variables → Actions**:

**Secrets** (New repository secret) — hidden, for sensitive values:
- `IG_USER_ID` = the number from Step 4
- `IG_ACCESS_TOKEN` = the non-expiring **Page** token from Step 3
- `IMAGE_BASE_URL` = the raw URL from Step 5

**Variables** (Variables tab) — non-sensitive:
- `LAUNCH_DATE` = your day-1 date, e.g. `2026-07-20`
- `GRAPH_VERSION` = `v23.0`

**Posting time:** the workflow runs at `0 23 * * *` (23:00 UTC) — about 7pm Eastern in
summer. You only need to pick the *hour*: the publisher computes the calendar day in your
timezone (`America/Toronto` in the manifest), so the correct day always posts even if the
cron hour drifts across daylight-saving. GitHub cron is best-effort and can run 5–30 min
late; that's normal. For the launch post specifically, use the manual trigger (Step 7) so
timing is exact.

---

## Step 7 — Test before you trust it

**Optional local dry run** (validates the manifest + checks your image URLs are live JPEGs,
posts nothing). It needs Python once:
1. Install **Python 3.12** from python.org — tick **"Add Python to PATH"** during install.
2. Open the `automation` folder, Shift+right-click → **Open PowerShell window here**.
3. Run:
   ```
   pip install requests
   $env:IMAGE_BASE_URL="https://raw.githubusercontent.com/YOUR_USERNAME/themoneyflinch/main/content"
   python publisher.py --slug after-check --dry-run
   ```
   Every slide should print `OK`. Any `NOT REACHABLE` or `not image/jpeg` means fix the repo
   before going live. (Without setting `IMAGE_BASE_URL` it prints placeholder URLs and skips
   the check — set it so the check actually runs.)

**The real test — do this once before trusting the schedule:**
In GitHub → **Actions → Daily Money Flinch post → Run workflow**. In the **slug** box type
`after-check` and run it. This posts Day 1 immediately (not the cron), regardless of your
launch date. Watch the log: `PUBLISHED media …` means it worked — check your Instagram.
Once that one manual run succeeds, the daily schedule needs nothing further.

---

## Guardrails (important)

- **Comment replies stay human.** The machine posts; it does NOT reply to people. Replying
  in your own voice within the first hour is the growth engine — never automate it.
- **This uses only the official API.** No auto-follow, no auto-DM, no fake browser bots —
  those get accounts banned. Everything here is Meta-sanctioned.
- **No duplicate posts.** The publisher checks your recent posts and skips if today's
  carousel is already up, so a manual run + the scheduled run can't double-post.
- **The Page token doesn't expire,** but if the app is ever disabled or you revoke access,
  the job fails with an auth error and GitHub emails you. Redo Step 3's Page-token step and
  update the `IG_ACCESS_TOKEN` secret.
- **Keep the repo active.** GitHub disables scheduled workflows after ~60 days with **no
  commits**. Pushing your weekly content is usually enough; if you ever get a "workflow
  disabled" email, click to re-enable.
- **To skip a day,** set that post's `"status"` to anything other than `"ready"` in the
  manifest (the publisher refuses to post a non-ready day). **Timing** lives only in the
  cron in `daily-post.yml` — editing the manifest does not change *when* it posts.
