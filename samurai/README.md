# Instagram Public Profile Data Scraper  
### Exact Followers Count & Public Instagram Data

A Python-based web scraping tool designed to retrieve **exact Instagram followers count**
and other **public profile data** without login, authentication, or cookies.

Instagram displays follower numbers in an abbreviated format such as **10K** or **1M**.  
This tool retrieves the **real numeric value** behind those numbers.

**Example:**
- Instagram display: `10K followers`
- Actual value returned by this tool: `10,436 followers`

---

## Project Overview

Instagram limits the visibility of precise metrics by rounding large numbers.
This project demonstrates how **public Instagram profile data**
can be accessed programmatically to extract **accurate numerical values**.

The main focus of this project is **data accuracy and transparency**,
making it a practical example of responsible **Python web scraping**
using public endpoints.

---

## Key Features

- Retrieves the **exact Instagram followers count** (no rounding)
- Fetches **public Instagram profile data only**
- Works **without login or authentication**
- No Instagram account required
- No cookies are stored or reused
- Simple input: username or public profile URL

---

## Public Data Collected

- Exact followers count
- Following count and total number of posts
- Account privacy status
- Verification status
- Profile full name and profile picture URL
- **Recent posts** (shortcode, type, date, like and comment counts)
- **Captions** for each recent post
- **Hashtags and mentions** parsed from captions (and the bio)
- **Comment counts** per post (and **real comment text** with a session ID)
- **Reels / video metadata** (video URL, view count, duration)
- **Media download** of public post images **and** videos (incl. carousels)
- **Bio** *(requires a logged-in session — see below)*
- **JSON export** of everything above

---

## Downloading post media (images + videos)

Set `IG_DOWNLOAD=1` to download the actual media from the recent public posts
into a `<username>_media/` folder. Carousel/album posts download every image,
and reels/videos download the `.mp4` when Instagram exposes it (otherwise the
cover image is saved as a fallback).

```bash
# Windows (PowerShell)
$env:IG_DOWNLOAD="1"; python main.py

# macOS / Linux
IG_DOWNLOAD=1 python main.py
```

Files are named `NN_<shortcode>[_k].<ext>` (e.g. `02_DPmAUeXEz2v.mp4`,
`03_DOqotnSEwLa_1.jpg`). The local paths are also recorded in the JSON output
under each post's `media` list.

> Some reels do not expose a direct video URL to anonymous visitors. Provide a
> session ID via `IG_SESSIONID` (see below) for the most reliable video links.

---

## JSON output

Every run automatically saves the complete result to `<username>.json` in the
current folder. The file includes the profile, recent posts, captions,
hashtags, mentions, comment counts, reel metadata, and summary stats.

To print the JSON directly to the console instead of the formatted tables, set
`IG_OUTPUT=json`:

```bash
# Windows (PowerShell)
$env:IG_OUTPUT="json"; python main.py

# macOS / Linux
IG_OUTPUT=json python main.py
```

This is handy for piping the data into other tools, e.g.
`IG_OUTPUT=json python main.py > nasa.json`.

---

## Optional: unlock Bio (and richer data) with a session ID

Instagram no longer serves the biography (or individual comment text) to
anonymous visitors. Everything else is collected without logging in, but if you
want the bio you can supply a session ID from your own logged-in browser via the
`IG_SESSIONID` environment variable:

```bash
# Windows (PowerShell)
$env:IG_SESSIONID="your_sessionid_cookie_value"; python main.py

# macOS / Linux
IG_SESSIONID="your_sessionid_cookie_value" python main.py
```

To find the value: open Instagram in your browser while logged in, open
DevTools → Application/Storage → Cookies → `https://www.instagram.com`, and copy
the `sessionid` value. When set, the scraper uses the authenticated profile API,
which also returns the biography, category, and website.

When a session ID is provided, the tool additionally fetches **real comment
text** (author, text, like count, time) for recent posts via Instagram's
authenticated comments API (`/api/v1/media/<id>/comments/`). Without a session,
only per-post comment **counts** are available, since Instagram no longer serves
comment text to anonymous visitors.

---

## Authentication & Privacy

This tool operates **without logging in** to Instagram.

It does **not** require:
- Username or password
- Session tokens
- Stored or reused cookies

The user only needs to provide:
- An Instagram username  
**or**
- A public Instagram profile URL

All retrieved data is **publicly accessible** without authentication.

---

## How It Works

The script uses Python and standard HTTP requests against Instagram's public
endpoints:

1. If `IG_SESSIONID` is set, it queries the authenticated `web_profile_info`
   API for the most complete data (including bio).
2. Otherwise it reads the public **embed** endpoint for the profile and parses
   the embedded JSON for follower counts and recent posts.
3. Recent video posts/reels are enriched by reading each post's embed to obtain
   the video URL, view count, and duration.

It extracts **raw numeric values** that are not fully visible
through Instagram’s user interface.

This makes the project useful for:
- Understanding how social media platforms expose public data
- Learning real-world web scraping techniques
- Analyzing public Instagram metrics accurately

---

## Installation

```bash
git clone https://github.com/walieed122/Instagram-Follower-Count-Public-Profile-Data-Scraper.git
cd Instagram-Follower-Count-Public-Profile-Data-Scraper
pip install -r requirements.txt