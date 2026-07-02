"""Load site inventories for chunked username scanners — priority from tool metadata only."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from adapters.scan_config import TOP_PRIORITY_SITES, maigret_max_sites, sherlock_max_sites, social_analyzer_max_sites
from tools.registry import registry


def _load_json(path: Path) -> dict | list | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


@lru_cache(maxsize=1)
def maigret_site_ranks() -> dict[str, int]:
    """Site name -> Alexa rank (lower = scan earlier). Loaded from Maigret DB metadata."""
    db_path = Path.home() / ".maigret" / "data.json"
    data = _load_json(db_path)
    if not isinstance(data, dict):
        return {}
    sites = data.get("sites", data)
    if not isinstance(sites, dict):
        return {}
    ranks: dict[str, int] = {}
    for name, info in sites.items():
        if not isinstance(info, dict) or info.get("disabled"):
            continue
        rank = info.get("alexaRank") or info.get("alexa_rank")
        if isinstance(rank, int) and rank > 0:
            ranks[name.lower()] = rank
    return ranks


@lru_cache(maxsize=1)
def scanner_registry_domains() -> frozenset[str]:
    """All domains covered by username scanner inventories (Maigret + Social Analyzer)."""
    domains: set[str] = set()
    db_path = Path.home() / ".maigret" / "data.json"
    data = _load_json(db_path)
    if isinstance(data, dict):
        sites = data.get("sites", data)
        if isinstance(sites, dict):
            for info in sites.values():
                if not isinstance(info, dict) or info.get("disabled"):
                    continue
                url_main = str(info.get("urlMain") or info.get("url") or "")
                if url_main:
                    host = urlparse(url_main).netloc.replace("www.", "").lower()
                    if host:
                        domains.add(host)
    for token in social_analyzer_site_tokens():
        host = token if "." in token else urlparse(f"https://{token}").netloc
        host = host.replace("www.", "").lower().strip()
        if host:
            domains.add(host)
    return frozenset(domains)


def _site_rank(name: str, ranks: dict[str, int]) -> int:
    low = name.lower().strip()
    if low in ranks:
        return ranks[low]
    for site, rank in ranks.items():
        if site in low or low in site:
            return rank
    return 10_000_000


def partition_priority_sites(
    items: list[str],
    *,
    max_priority: int = TOP_PRIORITY_SITES,
) -> tuple[list[str], list[str]]:
    """Phase-1 sites = lowest Alexa rank from scanner metadata; remainder = phase 2."""
    ranks = maigret_site_ranks()
    ordered = sorted(items, key=lambda item: (_site_rank(item, ranks), item.lower()))
    priority = ordered[:max_priority]
    rest = ordered[max_priority:]
    return priority, rest


def cap_site_list(
    items: list[str],
    max_sites: int | None,
    *,
    max_priority: int | None = None,
) -> tuple[list[str], list[str]]:
    """Return (capped inventory, phase-1 priority subset)."""
    if not items:
        return [], []
    mp = max_priority if max_priority is not None else TOP_PRIORITY_SITES
    if not max_sites or max_sites <= 0 or len(items) <= max_sites:
        priority, _rest = partition_priority_sites(items, max_priority=mp)
        return items, priority
    phase_cap = min(mp, max(40, max_sites // 2))
    priority, _rest = partition_priority_sites(items, max_priority=phase_cap)
    priority = priority[:max_sites]
    remainder = [item for item in items if item not in set(priority)]
    capped = (priority + remainder)[:max_sites]
    priority = [item for item in priority if item in capped]
    return capped, priority


def _capped_tool_sites(loader, cap_fn) -> int:
    items = loader()
    capped, _priority = cap_site_list(items, cap_fn())
    return len(capped) if capped else len(items)


def estimated_username_sites() -> int:
    """Per-tool capped site counts summed — matches live progress totals."""
    return (
        _capped_tool_sites(maigret_site_names, maigret_max_sites)
        + _capped_tool_sites(sherlock_site_names, sherlock_max_sites)
        + _capped_tool_sites(social_analyzer_site_tokens, social_analyzer_max_sites)
    )


def total_username_sites() -> int:
    return estimated_username_sites()


def sherlock_site_names() -> list[str]:
    tool_path = registry.get_executable_path("sherlock")
    if not tool_path:
        return []
    candidates = [
        tool_path.parent / "resources" / "data.json",
        tool_path.parent / "sherlock_project" / "resources" / "data.json",
        tool_path.parent.parent / "sherlock_project" / "resources" / "data.json",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        data = _load_json(candidate)
        if isinstance(data, dict):
            return [k for k in data if k != "$schema"]
    return []


def maigret_site_names() -> list[str]:
    db_path = Path.home() / ".maigret" / "data.json"
    data = _load_json(db_path)
    if not isinstance(data, dict):
        return []
    sites = data.get("sites", data)
    if not isinstance(sites, dict):
        return []
    return [
        name
        for name, info in sites.items()
        if isinstance(info, dict) and not info.get("disabled")
    ]


def social_analyzer_site_tokens() -> list[str]:
    tool_path = registry.get_tool_path("social_analyzer")
    if not tool_path:
        return []
    data_file = tool_path / "data" / "sites.json"
    if not data_file.exists():
        data_file = tool_path / "sites.json"
    data = _load_json(data_file)
    if not isinstance(data, dict):
        return []
    entries = data.get("websites_entries", [])
    if not isinstance(entries, list):
        return []
    tokens: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url") or ""
        if not url:
            continue
        host = urlparse(url).netloc.replace("www.", "")
        tokens.append(host or url[:48])
    return tokens
