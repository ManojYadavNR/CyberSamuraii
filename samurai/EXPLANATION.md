# How It Works — Feature-by-Feature Explanation

This document explains **where** each piece of information comes from and
**which method/endpoint** the scraper uses to get it. All function names refer
to `main.py`.

---

## The two data sources

Instagram exposes profile data through different surfaces. This tool uses two,
picked automatically:

| Source | Endpoint | When it's used | What it gives |
|---|---|---|---|
| **Authenticated API** | `GET /api/v1/users/web_profile_info/` | Only when `IG_SESSIONID` is set | Everything (bio, posts, reels, etc.) |
| **Public embed** | `GET /<username>/embed/` | Default (no login) | Followers, posts, captions, hashtags, reel stats |

The decision happens in `collect_profile()`:

```
make_session(sessionid)            # build a (optionally logged-in) session
  └─ fetch_web_profile_info()      # try the authenticated API first
       ├─ success → profile_from_web_api()      (source = "web_profile_info")
       └─ fail/none → fetch_profile_from_embed() (source = "embed")
                       + enrich_from_profile_page()
  └─ enrich_reels()                # add video URL / views / duration
  └─ enrich_comments()             # add real comment text (only if logged in)
```

### Why the embed endpoint?
The normal profile page (`/<username>/`) now returns a JavaScript-only
"error" shell to anonymous visitors, and the `web_profile_info` API returns
`429` without a login. The **embed** page (`/<username>/embed/`) still contains
a full JSON blob (`contextJSON`) with the profile and recent posts, so it is the
reliable anonymous source.

### How the embedded JSON is read
The embed HTML hides a JSON document inside a JavaScript string. Two helpers
decode it safely:
- `extract_json_string()` — scans character by character honoring `\` escapes
  to pull the full `contextJSON` value (a plain regex breaks on `\"`).
- `load_context_json()` — JSON-decodes it twice (string layer, then object).
- `find_key()` — depth-first search for a key (e.g. `graphql_media`).

---

## Getting the profile (username, name, picture, verified, private)

**Method:** Embed page JSON + meta-tag fallback.

- `fetch_profile_from_embed()` reads `/<username>/embed/` and extracts
  `username`, `full_name`, `is_verified`, `is_private`, `id`, and the
  profile picture (`extract_profile_pic_url()`).
- The real **user ID** is taken from a post's `owner.id` (a bare `id` match can
  accidentally grab a media ID).
- `enrich_from_profile_page()` fills any gaps (full name, profile picture) from
  the profile page's Open Graph meta tags (`og:title`, `og:image`).
- With a session, `profile_from_web_api()` reads these straight from the API.

---

## Getting the followers count (exact, no rounding)

**Method:** Embed page JSON.

- In `fetch_profile_from_embed()`, the exact number is read from the embed's
  `followers_count` field, with a fallback to `edge_followed_by.count`
  (`extract_embed_value()` / `extract_graphql_count()`).
- Following count comes from `edge_follow.count`; post count from
  `posts_count` / `edge_owner_to_timeline_media.count`.
- As a last resort, `enrich_from_profile_page()` parses the
  `og:description` text ("686M Followers, 228 Following, 8,492 Posts") via
  `parse_meta_counts()` — but that is rounded, so the embed JSON is preferred.
- With a session, the API provides `edge_followed_by.count` directly.

> This is the core feature: Instagram's UI shows `686M`, but the embed JSON
> carries the exact integer (e.g. `685,926,813`).

---

## Getting the bio

**Method:** Authenticated API only.

- The embed page does **not** contain the biography, and the profile page is
  blocked for anonymous users.
- `fetch_web_profile_info()` returns `biography` only when `IG_SESSIONID` is
  set. Without it, the bio is left empty and the output shows a note.
- Bio hashtags/mentions are parsed from the bio text using
  `extract_hashtags()` / `extract_mentions()`.

---

## Getting recent posts

**Method:** Embed page JSON (`graphql_media`).

- `fetch_profile_from_embed()` finds the `graphql_media` array in `contextJSON`
  and converts each item with `normalize_post()`.
- Each post records: `shortcode`, `media_id`, `url`, `type`
  (Image / Video / Reel / Carousel via `media_type()`), `like_count`,
  `comment_count`, and `timestamp` (`timestamp_to_str()`).
- With a session, posts come from `edge_owner_to_timeline_media.edges` in the
  API response.

---

## Getting captions

**Method:** From the post node in the embed/API JSON.

- `caption_text()` reads `edge_media_to_caption.edges[0].node.text`, falling
  back to `accessibility_caption` when there is no caption.

---

## Getting hashtags (and mentions)

**Method:** Regex parsing of the caption/bio text.

- `extract_hashtags()` uses the pattern `#([A-Za-z0-9_]+)`.
- `extract_mentions()` uses `@([A-Za-z0-9_.]+)`.
- Applied to every post caption and to the bio.

---

## Getting images

**Method:** Media URLs from the post JSON + HTTP download.

- `collect_media()` builds the list of every image in a post:
  - Single image → `display_url`.
  - **Carousel/album** → iterates `edge_sidecar_to_children.edges` so **all**
    images are captured, not just the cover.
- `download_media()` (enabled with `IG_DOWNLOAD=1`) downloads each file with
  `download_file()` into `<username>_media/`, naming them
  `NN_<shortcode>[_k].jpg`. `_safe_extension()` picks the extension.

---

## Getting videos / reels (and reel metadata)

**Method:** Per-post embed enrichment + media download.

- The profile-level embed lists videos but **omits** the playable URL, view
  count, and duration. `enrich_reels()` fetches each video post's own embed
  (`fetch_post_details()` → `/p/<shortcode>/embed/captioned/`) to obtain:
  - `video_url` (the `.mp4`)
  - `video_view_count`
  - `video_duration`
- Reels are detected by `product_type == "clips"` or `is_video` in
  `media_type()`.
- `download_media()` saves the `.mp4` when the URL is exposed; if Instagram
  withholds it for an anonymous request, it falls back to saving the cover
  image. (A session ID makes the video URL reliable.)
- Fetches are capped (`MAX_REEL_DETAIL_FETCHES`) with a small delay
  (`DETAIL_FETCH_DELAY`) to avoid rate limiting.

---

## Getting comments

**Method:** Comment count (always) + real comment text (with session).

- **Counts** come from `edge_media_to_comment.count` on each post (embed/API).
- **Real comment text** is fetched by `fetch_comments()` via the authenticated
  endpoint `GET /api/v1/media/<media_id>/comments/`, returning each comment's
  `username`, `text`, `comment_like_count`, and `created_at`.
- This runs only when `IG_SESSIONID` is set (`enrich_comments()`), because
  Instagram returns a login wall for anonymous comment requests. Without a
  session, only counts are shown.

---

## Output methods

- **Formatted tables** (default): `render_profile()`, `render_posts()`,
  `render_reels()`, `render_comments()` using the `rich` library.
- **JSON**: `build_json_payload()` assembles a clean structure; `save_json()`
  always writes `<username>.json`; set `IG_OUTPUT=json` to print JSON to the
  console instead of tables.

---

## Environment variables summary

| Variable | Effect |
|---|---|
| `IG_SESSIONID` | Log in → unlocks **bio** and **real comment text**, makes video URLs reliable |
| `IG_DOWNLOAD=1` | Download post **images and videos** into `<username>_media/` |
| `IG_OUTPUT=json` | Print the full result as **JSON** to the console |

---

## Quick reference: feature → method

| Feature | Endpoint / Method | Needs login? |
|---|---|---|
| Followers / following / post count | Embed JSON (`followers_count`, `edge_*`) | No |
| Profile (name, pic, verified, private, ID) | Embed JSON + OG meta tags / API | No |
| Bio | `web_profile_info` API | **Yes** |
| Recent posts | Embed `graphql_media` / API | No |
| Captions | Post node `edge_media_to_caption` | No |
| Hashtags / mentions | Regex on caption & bio | No |
| Images (incl. carousels) | `display_url` / `edge_sidecar_to_children` + download | No |
| Videos / reels metadata | Per-post embed (`video_url`, views, duration) | No (URL more reliable with login) |
| Comment counts | Post node `edge_media_to_comment.count` | No |
| Comment text | `/api/v1/media/<id>/comments/` | **Yes** |
