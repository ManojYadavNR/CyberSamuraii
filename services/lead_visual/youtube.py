"""YouTube / video thumbnail URLs without browser automation."""

from __future__ import annotations

import re

YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def youtube_thumbnail(url: str) -> str | None:
    match = YT_ID_RE.search(url)
    if not match:
        return None
    vid = match.group(1)
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
