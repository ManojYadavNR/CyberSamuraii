import hashlib
from typing import Any

import httpx

from schemas.common import ToolResult

# Major webmail providers — theHarvester cannot find inbox-specific intel here.
CONSUMER_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "protonmail.com",
        "proton.me",
        "aol.com",
        "mail.ru",
        "yandex.ru",
        "yandex.com",
        "gmx.com",
        "zoho.com",
    }
)

# Sort holehe leads by confidence, not platform brand.
MAX_INVESTIGATION_LEADS = 25


def _platform_priority(_platform: str) -> int:
    return 0


def email_domain(email: str) -> str:
    return email.split("@", 1)[1].strip().lower()


def is_consumer_mail(email: str) -> bool:
    return email_domain(email) in CONSUMER_MAIL_DOMAINS


async def fetch_gravatar_profile(email: str) -> dict[str, Any] | None:
    """Public Gravatar profile tied to an email hash (no API key)."""
    digest = hashlib.md5(email.strip().lower().encode()).hexdigest()
    url = f"https://www.gravatar.com/{digest}.json"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            payload = resp.json()
            entries = payload.get("entry") or []
            if not entries:
                return None
            entry = entries[0]
            return {
                "type": "public_profile",
                "source": "gravatar",
                "platform": "gravatar",
                "confidence": "public",
                "display_name": entry.get("displayName"),
                "profile_url": entry.get("profileUrl"),
                "avatar_url": f"https://www.gravatar.com/avatar/{digest}",
                "location": entry.get("currentLocation"),
                "about": entry.get("aboutMe"),
                "bio": entry.get("aboutMe"),
                "accounts": [
                    {
                        "domain": acct.get("domain"),
                        "username": acct.get("username"),
                        "display": acct.get("display"),
                        "verified": acct.get("verified"),
                    }
                    for acct in (entry.get("accounts") or [])
                ],
            }
    except Exception:
        return None


def _confirmed_from_holehe(item: dict[str, Any]) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "type": "account_registration",
        "platform": item.get("platform"),
        "email": item.get("email"),
        "confidence": "confirmed",
        "source_tool": item.get("source_tool", "holehe"),
        "check_type": "live_scan",
        "registered": True,
    }
    for key in ("email_recovery_hint", "phone_hint", "profile_metadata"):
        if item.get(key):
            finding[key] = item[key]
    return finding


def _lead_from_holehe(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "inconclusive_check",
        "platform": item.get("platform"),
        "email": item.get("email"),
        "confidence": "inconclusive",
        "reason": "rate_limited",
        "source_tool": item.get("source_tool", "holehe"),
        "recommendation": "Platform blocked automated check — verify manually.",
    }


def _public_from_tool(item: dict[str, Any]) -> dict[str, Any] | None:
    platform = item.get("platform", "")
    if platform in ("_scan_summary", "email"):
        return None
    if item.get("status") not in (None, "registered") and item.get("registered") is not True:
        return None
    finding: dict[str, Any] = {
        "type": "harvested_intel",
        "platform": platform,
        "confidence": "public",
        "source_tool": item.get("source_tool"),
    }
    if item.get("email"):
        finding["email"] = item["email"]
    if item.get("url"):
        finding["url"] = item["url"]
    if item.get("hostname"):
        finding["hostname"] = item["hostname"]
    return finding


def build_email_investigation(
    tool_results: list[ToolResult],
    query: str,
    public_profiles: list[dict[str, Any]],
) -> tuple[list[dict], list[dict], list[dict], dict[str, Any]]:
    confirmed: list[dict[str, Any]] = []
    leads: list[dict[str, Any]] = []
    scan_summary: dict[str, Any] = {"email": query, "domain": email_domain(query)}

    for result in tool_results:
        if not result.success:
            scan_summary[result.tool] = {"status": "failed", "error": result.error}
            continue

        if result.tool == "holehe":
            holehe_summary: dict[str, Any] = {}
            holehe_leads: list[dict[str, Any]] = []

            for item in result.data:
                platform = item.get("platform")
                status = item.get("status")

                if platform == "_scan_summary":
                    holehe_summary = {
                        k: v
                        for k, v in item.items()
                        if k not in ("platform", "source_tool")
                    }
                    continue

                if status == "registered":
                    confirmed.append(_confirmed_from_holehe(item))
                elif status == "rate_limited":
                    holehe_leads.append(_lead_from_holehe(item))

            holehe_leads.sort(key=lambda x: _platform_priority(x.get("platform", "")))
            leads.extend(holehe_leads[:MAX_INVESTIGATION_LEADS])
            scan_summary["holehe"] = holehe_summary or {"status": "completed"}

        elif result.tool == "theharvester":
            harvest_items = [_public_from_tool(item) for item in result.data]
            harvest_items = [x for x in harvest_items if x]
            if harvest_items:
                confirmed.extend(harvest_items)
            skipped = (
                not harvest_items
                and bool(result.raw_output)
                and "Skipped theHarvester" in result.raw_output
            )
            scan_summary["theharvester"] = {
                "status": "skipped" if skipped else "completed",
                "items": len(harvest_items),
                "note": (result.raw_output or "")[:240] if skipped else None,
            }

        elif result.tool == "google_dorking":
            dork_hits = [
                item
                for item in result.data
                if item.get("platform") != "_scan_summary"
                and item.get("check_type") in ("google_dork", "google_search_discovery", None)
                and (item.get("url") or item.get("check_type") == "google_search_discovery")
            ]
            summary_row = next(
                (item for item in result.data if item.get("platform") == "_scan_summary"),
                {},
            )
            hit_count = len(dork_hits) or int(summary_row.get("sites_found") or 0)
            scan_summary["google_dorking"] = {
                "status": "completed",
                "hits": hit_count,
                "dorks_run": summary_row.get("sites_checked") or len(dork_hits) or 0,
                "note": summary_row.get("note"),
            }
            for item in dork_hits[:12]:
                url = item.get("url")
                if not url:
                    continue
                confirmed.append(
                    {
                        "type": "email_web_mention",
                        "platform": item.get("platform") or "google_search",
                        "email": query,
                        "url": url,
                        "title": item.get("title"),
                        "snippet": item.get("snippet"),
                        "dork_category": item.get("dork_category"),
                        "confidence": "public",
                        "source_tool": "google_dorking",
                    }
                )

        elif result.tool == "gravatar":
            found = any(item.get("platform") == "gravatar" for item in result.data)
            scan_summary["gravatar"] = {
                "status": "completed",
                "found": found,
            }

        elif result.tool == "ghunt":
            ghunt_items = [item for item in result.data if item.get("profile_metadata") or item.get("email")]
            scan_summary["ghunt"] = {
                "status": "completed",
                "items": len(ghunt_items),
                "note": (result.raw_output or "")[:200] if not ghunt_items else None,
            }
            for item in ghunt_items:
                meta = item.get("profile_metadata") or {}
                confirmed.append(
                    {
                        "type": "google_account_intel",
                        "platform": "google",
                        "email": query,
                        "confidence": "public",
                        "source_tool": "ghunt",
                        "profile_metadata": meta,
                    }
                )

        elif result.tool == "spiderfoot":
            sf_items = [_public_from_tool(item) for item in result.data]
            sf_items = [x for x in sf_items if x]
            if sf_items:
                confirmed.extend(sf_items)
            scan_summary["spiderfoot"] = {
                "status": "completed",
                "items": len(sf_items),
                "note": (
                    "No extra breach or enrichment data without HIBP/Hunter/Clearbit API keys."
                    if not sf_items
                    else None
                ),
            }

    public_data = list(public_profiles)
    from services.email_profile_resolver import build_profile_url

    for profile in public_data:
        for acct in profile.get("accounts") or []:
            if acct.get("domain"):
                username = acct.get("username") or acct.get("display")
                profile_url = build_profile_url(str(acct["domain"]), str(username) if username else None)
                confirmed.append(
                    {
                        "type": "linked_account",
                        "platform": acct["domain"],
                        "username": username,
                        "confidence": "public",
                        "source_tool": "gravatar",
                        "profile_url": profile_url or profile.get("profile_url"),
                        "url": profile_url,
                        "linked_from_gravatar": True,
                    }
                )

    # Deduplicate confirmed by platform+email
    seen: set[str] = set()
    deduped_confirmed: list[dict[str, Any]] = []
    for item in confirmed:
        key = f"{item.get('platform')}:{item.get('email', '')}:{item.get('username', '')}"
        if key in seen:
            continue
        seen.add(key)
        deduped_confirmed.append(item)

    scan_summary["confirmed_count"] = len(deduped_confirmed)
    scan_summary["investigation_leads_count"] = len(leads)
    scan_summary["public_profiles_found"] = len(public_data)

    return deduped_confirmed, public_data, leads, scan_summary
