"""Extract client/session context for audit entries."""

from __future__ import annotations

import re
from typing import Any


def parse_user_agent(user_agent: str) -> dict[str, str]:
    ua = user_agent or ""
    low = ua.lower()
    browser = "Unknown"
    if "edg/" in low or "edge/" in low:
        browser = "Edge"
    elif "chrome/" in low and "chromium" not in low:
        browser = "Chrome"
    elif "firefox/" in low:
        browser = "Firefox"
    elif "safari/" in low and "chrome" not in low:
        browser = "Safari"

    os_name = "Unknown"
    if "windows" in low:
        os_name = "Windows"
    elif "mac os" in low or "macintosh" in low:
        os_name = "macOS"
    elif "android" in low:
        os_name = "Android"
    elif "iphone" in low or "ipad" in low:
        os_name = "iOS"
    elif "linux" in low or "ubuntu" in low:
        os_name = "Linux"

    device = "Desktop"
    if "mobile" in low or "android" in low or "iphone" in low:
        device = "Mobile"
    elif "ipad" in low or "tablet" in low:
        device = "Tablet"
    elif "laptop" in low:
        device = "Laptop"

    return {"browser": browser, "os": os_name, "device": device}


def approximate_location(ip: str) -> str:
    if not ip:
        return ""
    if ip.startswith("127.") or ip == "::1" or ip.startswith("192.168.") or ip.startswith("10."):
        return "Private network"
    if ip.startswith("172."):
        return "Private network"
    return ""


def audit_context_from_request(request: Any | None) -> dict[str, str]:
    if request is None:
        return {}
    headers = getattr(request, "headers", None)
    client = getattr(request, "client", None)
    ip = ""
    if client and getattr(client, "host", None):
        ip = str(client.host)
    forwarded = headers.get("x-forwarded-for") if headers else None
    if forwarded:
        ip = str(forwarded).split(",")[0].strip() or ip
    user_agent = str(headers.get("user-agent", "")) if headers else ""
    parsed = parse_user_agent(user_agent)
    session_id = ""
    auth = str(headers.get("authorization", "")) if headers else ""
    if auth.lower().startswith("bearer "):
        session_id = re.sub(r"[^a-zA-Z0-9_-]", "", auth[-24:])
    return {
        "ip": ip,
        "user_agent": user_agent[:256],
        "session_id": session_id,
        "browser": parsed["browser"],
        "os": parsed["os"],
        "device": parsed["device"],
        "location_approx": approximate_location(ip),
    }
