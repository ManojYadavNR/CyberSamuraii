"""Priority scoring for lead visual capture."""

from __future__ import annotations

LEAD_TYPE_WEIGHT = {
    "hackathon": 100,
    "achievement": 95,
    "event": 85,
    "college": 80,
    "news": 75,
    "article": 70,
    "video": 65,
    "profile": 40,
    "image": 55,
    "mention": 20,
}

KEYWORD_BOOSTS = (
    ("hackathon", 40),
    ("winner", 35),
    ("finalist", 30),
    ("college", 25),
    ("university", 25),
    (".edu", 20),
    ("congratulations", 20),
    ("award", 18),
    ("devpost", 15),
    ("newspaper", 15),
    ("/posts/", 12),
    ("/photos/", 10),
)


def score_lead(
    *,
    lead_type: str,
    title: str,
    snippet: str,
    url: str,
    dork_category: str = "",
    fusion_score: float = 0.5,
) -> float:
    blob = f"{title} {snippet} {url} {dork_category}".lower()
    score = float(LEAD_TYPE_WEIGHT.get(lead_type, 10))
    for term, boost in KEYWORD_BOOSTS:
        if term in blob:
            score += boost
    score += min(15.0, fusion_score * 15.0)
    if "login" in url.lower() or "/search" in url.lower():
        score -= 50
    return round(score, 2)
