"""Generate discovery leads and evidence chains from reverse image matches."""

from __future__ import annotations

from urllib.parse import urlparse
from uuid import uuid4

from schemas.discovery import DiscoveryLead
from schemas.reverse_image import EvidenceChain, EvidenceChainLink, ReverseImageMatch
from services.discovery.router import build_routable_lead
from services.discovery.validators import normalize_domain
from services.reverse_image.extractors import extract_usernames_from_url


def _domain_from_url(url: str) -> str | None:
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower().replace("www.", "")
    return normalize_domain(host) if host else None


def leads_from_matches(
    matches: list[ReverseImageMatch],
    *,
    source_query: str,
    depth: int = 0,
    max_leads: int = 30,
) -> list[DiscoveryLead]:
    leads: list[DiscoveryLead] = []
    seen: set[str] = set()

    def add(query: str, lead_type: str, reason: str, priority: float, meta: dict) -> None:
        key = f"{lead_type}:{query.lower()}"
        if key in seen:
            return
        lead = build_routable_lead(
            query,
            lead_type=lead_type,
            depth=depth,
            priority=min(1.0, priority),
            source_query=source_query,
            reason=reason,
            metadata={**meta, "pivot": True, "reverse_image": True},
        )
        if not lead:
            return
        seen.add(key)
        leads.append(lead)

    for match in matches:
        base_priority = 0.45 + match.confidence * 0.4
        for profile_url in match.profile_urls[:3]:
            handles = extract_usernames_from_url(profile_url)
            for handle in handles:
                add(
                    handle,
                    "username",
                    f"reverse_image_profile:{match.source}",
                    base_priority + 0.12,
                    {"profile_url": profile_url, "match_id": match.match_id},
                )
            if not handles:
                add(
                    profile_url,
                    "image",
                    f"reverse_image:{match.source}:{match.match_type}",
                    base_priority + 0.1,
                    {"match_id": match.match_id, "source": match.source, "match_url": match.match_url},
                )
        domain = _domain_from_url(match.page_url or match.match_url)
        if domain:
            add(
                domain,
                "domain",
                f"reverse_image_domain:{match.source}",
                base_priority,
                {"match_id": match.match_id},
            )
        if match.match_url.startswith("http"):
            add(
                match.match_url,
                "image",
                f"reverse_image_url:{match.source}",
                base_priority - 0.05,
                {"match_type": match.match_type},
            )

    leads.sort(key=lambda l: -l.priority)
    return leads[:max_leads]


def evidence_chains_from_matches(
    matches: list[ReverseImageMatch],
    *,
    seed_image: str,
) -> list[EvidenceChain]:
    chains: list[EvidenceChain] = []
    for match in matches[:20]:
        links = [
            EvidenceChainLink(step="image", value=seed_image, source="seed", confidence=1.0),
            EvidenceChainLink(step="match", value=match.match_url, source=match.source, confidence=match.confidence),
        ]
        terminal = match.match_url
        for profile in match.profile_urls[:2]:
            links.append(EvidenceChainLink(step="profile", value=profile, source=match.source, confidence=match.confidence))
            terminal = profile
        for org in match.organizations[:1]:
            links.append(EvidenceChainLink(step="organization", value=org, source=match.source, confidence=match.confidence * 0.9))
            terminal = org
        chains.append(EvidenceChain(
            chain_id=str(uuid4()),
            seed_image=seed_image,
            links=links,
            terminal_lead=terminal,
            confidence=match.confidence,
        ))
    return chains
