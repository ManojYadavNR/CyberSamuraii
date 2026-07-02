"""Extract follow-up search terms from initial username SERP hits — no hardcoded names."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from services.discovery.attribution import (
    context_references_seed,
    person_name_variants,
    split_handle_to_display_name,
    url_references_seed,
)
from services.evidence.document_parser import SCHOOL_RE, _extract_event_labels
from services.platform_registry import (
    is_priority_social_host,
    is_social_post_url,
    platform_label_from_host,
)

GENERIC_STOP = frozenset({
    "home", "about", "profile", "linkedin", "instagram", "facebook", "youtube",
    "google", "search", "sign in", "log in", "photos and videos", "more about",
    "followers", "following", "posts", "official page", "website", "contact",
    "the", "and", "for", "with", "from", "your", "this", "that", "have", "been",
})

ORG_PATTERNS = (
    re.compile(r"(?:Experience|Works?\s+at|Employer|Company)\s*[:\|•-]\s*([^|•\n]{3,72})", re.I),
    re.compile(r"(?:at|@)\s+([A-Z][\w\s&'.-]{2,58}(?:Ltd|LLC|Inc|Pvt|Corp|GmbH|International)?)", re.I),
)

ROLE_PATTERNS = (
    re.compile(r"\b(Full[\s-]?Stack Developer|Software Engineer|Data Scientist|DevOps Engineer|"
               r"Product Manager|Consultant|Analyst|Architect|Designer|Student|Intern)\b", re.I),
)

ACHIEVEMENT_HINT = re.compile(
    r"hackathon|winner|won|award|finalist|champion|runner-up|trophy|medal|recognition|"
    r"congratulations|competition|fest|placed|ranked|selected|honored",
    re.I,
)

HACKATHON_EVENT_RE = re.compile(
    r"([\w][\w\s]*(?:hack(?:athon)?|fest)(?:\s*(?:v?\d+\.?\d*))?)",
    re.I,
)

COLLEGE_TITLE_PREFIX_RE = re.compile(r"^([A-Z][\w\s&'.-]{2,56})\s*[-–|]\s*", re.I)

PLACEMENT_RE = re.compile(
    r"\b(winner|won|first\s+place|champion|runner-?up|runners-?up|finalist|second\s+place|third\s+place)\b",
    re.I,
)

INSTITUTION_IN_TITLE_RE = re.compile(
    r"([\w][\w\s&'.-]{2,72}(?:Institute|College|University|School|Polytechnic)(?:\s+[\w][\w\s&'.-]{0,48})?)",
    re.I,
)

HASHTAG_RE = re.compile(r"#[\w][\w\d_]{2,39}")

INSTITUTION_WORD_RE = re.compile(
    r"\b(?:institute|college|university|school|academy|polytechnic)\b",
    re.I,
)


def _is_education_phrase(phrase: str) -> bool:
    clean = " ".join(phrase.split()).strip()
    return len(clean) >= 8 and bool(INSTITUTION_WORD_RE.search(clean))


def _clean_label(value: str) -> str | None:
    clean = " ".join(value.split()).strip(" .,-|•")
    if not clean or len(clean) < 4:
        return None
    if "..." in clean or clean.endswith("…"):
        return None
    if clean.lower() in GENERIC_STOP:
        return None
    return clean

PROFESSIONAL_HINT = re.compile(
    r"developer|engineer|manager|consultant|analyst|director|founder|ceo|cto|student|intern|"
    r"experience|employer|company|professional",
    re.I,
)


@dataclass
class DiscoveredKeyword:
    phrase: str
    category: str
    source_url: str = ""
    source_title: str = ""
    score: float = 0.5
    source_snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phrase": self.phrase,
            "category": self.category,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "source_snippet": self.source_snippet[:240],
            "score": round(self.score, 3),
        }


def _normalize_phrase(phrase: str) -> str:
    return " ".join(phrase.split()).strip(" .,-|•")


def _is_noise(phrase: str, seed_query: str) -> bool:
    low = phrase.lower().strip()
    if len(low) < 3 or len(low) > 80:
        return True
    if low in GENERIC_STOP:
        return True
    for variant in person_name_variants(seed_query):
        if low == variant.lower():
            return True
    seed_compact = seed_query.split("|")[0].strip().lower().replace(" ", "")
    if seed_compact and seed_compact in low.replace(" ", ""):
        return True
    return False


def _add(
    bucket: dict[str, DiscoveredKeyword],
    *,
    phrase: str,
    category: str,
    hit: dict[str, Any],
    score: float,
) -> None:
    clean = _normalize_phrase(phrase)
    if not clean:
        return
    key = clean.lower()
    existing = bucket.get(key)
    if existing and existing.score >= score:
        return
    bucket[key] = DiscoveredKeyword(
        phrase=clean,
        category=category,
        source_url=str(hit.get("url") or ""),
        source_title=str(hit.get("title") or "")[:160],
        source_snippet=str(hit.get("snippet") or "")[:240],
        score=score,
    )


def _hit_references_seed(hit: dict[str, Any], seed_query: str) -> bool:
    title = str(hit.get("title") or "")
    snippet = str(hit.get("snippet") or "")
    url = str(hit.get("url") or "")
    if context_references_seed(title, snippet, seed_query=seed_query):
        return True
    return url_references_seed(url, seed_query)


def extract_keywords_from_serp(
    hits: list[dict[str, Any]],
    *,
    seed_query: str,
    limit: int = 20,
) -> list[DiscoveredKeyword]:
    """
    Pull highlighted terms from plain username Google/DDG results.
    Works for hackathon winners, college posts, or professional profiles — per person.
    """
    seed = seed_query.split("|")[0].strip()
    if not seed:
        return []

    bucket: dict[str, DiscoveredKeyword] = {}

    for hit in hits:
        if not _hit_references_seed(hit, seed_query):
            continue

        title = str(hit.get("title") or "")
        snippet = str(hit.get("snippet") or "")
        url = str(hit.get("url") or "")
        text = f"{title} {snippet}".strip()
        if not text:
            continue

        host = (urlparse(url).netloc or "").lower()

        for label in _extract_event_labels(text):
            if not _is_noise(label, seed):
                _add(bucket, phrase=label, category="achievement", hit=hit, score=0.92)

        for match in SCHOOL_RE.finditer(text):
            school = _normalize_phrase(match.group(0))
            if school and _is_education_phrase(school) and not _is_noise(school, seed):
                _add(bucket, phrase=school, category="education", hit=hit, score=0.88)

        for tag in HASHTAG_RE.findall(text):
            if not _is_noise(tag, seed):
                _add(bucket, phrase=tag, category="hashtag", hit=hit, score=0.87)

        for pattern in ORG_PATTERNS:
            for match in pattern.finditer(text):
                org = _normalize_phrase(match.group(1))
                if not _is_noise(org, seed):
                    cat = "professional" if PROFESSIONAL_HINT.search(text) else "organization"
                    _add(bucket, phrase=org, category=cat, hit=hit, score=0.82)

        for pattern in ROLE_PATTERNS:
            for match in pattern.finditer(text):
                role = _normalize_phrase(match.group(1))
                if not _is_noise(role, seed):
                    _add(bucket, phrase=role, category="professional", hit=hit, score=0.75)

        if ACHIEVEMENT_HINT.search(text):
            for part in re.split(r"[-–|•]", title):
                part = _normalize_phrase(part)
                if len(part) >= 8 and not _is_noise(part, seed) and ACHIEVEMENT_HINT.search(part):
                    _add(bucket, phrase=part, category="achievement", hit=hit, score=0.85)
            for match in HACKATHON_EVENT_RE.finditer(text):
                event = _normalize_phrase(match.group(1))
                if len(event) >= 6 and not _is_noise(event, seed):
                    _add(bucket, phrase=event, category="achievement", hit=hit, score=0.94)

        if is_priority_social_host(host):
            if " - " in title:
                left, right = title.split(" - ", 1)
                left_clean = _clean_label(left)
                if left_clean and _is_education_phrase(left_clean) and not _is_noise(left_clean, seed):
                    _add(bucket, phrase=left_clean, category="education", hit=hit, score=0.89)
                for inst in INSTITUTION_IN_TITLE_RE.findall(right):
                    inst_clean = _clean_label(inst)
                    if inst_clean and _is_education_phrase(inst_clean) and not _is_noise(inst_clean, seed):
                        _add(bucket, phrase=inst_clean, category="education", hit=hit, score=0.93)
            prefix = COLLEGE_TITLE_PREFIX_RE.match(title)
            if prefix:
                college = _clean_label(prefix.group(1))
                if college and _is_education_phrase(college) and not _is_noise(college, seed):
                    _add(bucket, phrase=college, category="education", hit=hit, score=0.91)

        if is_priority_social_host(host) and ACHIEVEMENT_HINT.search(text):
            label = platform_label_from_host(host).lower()
            _add(bucket, phrase=f"{label} post", category="social", hit=hit, score=0.9)
        elif is_priority_social_host(host) and not is_social_post_url(str(hit.get("url") or "")):
            label = platform_label_from_host(host).lower()
            _add(bucket, phrase=f"{label} profile", category="professional", hit=hit, score=0.7)

        display = split_handle_to_display_name(seed)
        if display and display.lower() in text.lower():
            for name in person_name_variants(seed):
                if len(name) >= 6:
                    _add(bucket, phrase=name, category="identity", hit=hit, score=0.95)

    ranked = sorted(bucket.values(), key=lambda k: (-k.score, -len(k.phrase)))
    return ranked[:limit]
