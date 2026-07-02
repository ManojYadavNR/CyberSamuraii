"""Headers for proxying external social CDN media (Facebook lookaside, Instagram CDN)."""

from __future__ import annotations

GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


def proxy_fetch_headers(url: str) -> dict[str, str]:
    from services.evidence.profile_verifier import USER_AGENT

    low = (url or "").lower()
    if "lookaside.fbsbx.com" in low or "lookaside/crawler" in low:
        return {"User-Agent": GOOGLEBOT_UA, "Referer": "https://www.facebook.com/"}
    if "facebook.com" in low or "fb.com" in low or "fb.watch" in low:
        return {"User-Agent": GOOGLEBOT_UA, "Referer": "https://www.facebook.com/"}
    if "fbcdn.net" in low or ("scontent." in low and "fb" in low):
        return {"User-Agent": GOOGLEBOT_UA, "Referer": "https://www.facebook.com/"}
    if "instagram." in low or "cdninstagram.com" in low:
        return {"User-Agent": USER_AGENT, "Referer": "https://www.instagram.com/"}
    return {"User-Agent": USER_AGENT}
