"""Generate Google dork queries from investigation targets — no hardcoded platforms."""

from __future__ import annotations

from dataclasses import dataclass

from services.platform_registry import build_site_or_query, generic_search_domains

EVENT_TERMS = (
    "event OR conference OR meetup OR workshop OR seminar OR summit OR festival "
    "OR competition OR tournament OR expo OR symposium OR ceremony OR webinar "
    "OR conclave OR fest OR showcase OR gala OR forum OR congress OR convocation "
    "OR participated OR speaker OR keynote OR panel OR hosted OR organized"
)

ACHIEVEMENT_TERMS = (
    "winner OR award OR finalist OR champion OR runner-up OR medal OR trophy "
    "OR recognition OR honored OR placed OR ranked OR selected"
)

DISCUSSION_TERMS = (
    "discussion OR thread OR reply OR comment OR posted OR forum post OR community post"
)

# Query-shape priority — simulates typing the username in Google first, then targeted slices.
PRIORITY_CATEGORIES = frozenset({
    "google_plain",
    "profile_exact",
    "serp_discovered",
    "social_post_search",
    "web_inurl",
    "web_intext",
    "profile_mentions",
    "contact_email",
    "contact_phone",
    "media_images",
    "media_images_inurl",
    "forum_mentions",
    "discussion_search",
    "blog_search",
    "article_search",
    "news_mentions",
    "events_general",
    "achievements",
    "discovered_domain",
})


@dataclass(frozen=True)
class DorkQuery:
    query: str
    category: str


def build_dork_queries(
    query: str,
    query_type: str | None = None,
    *,
    discovered_domains: list[str] | None = None,
    extra_queries: list[DorkQuery] | None = None,
    max_queries: int = 28,
) -> list[DorkQuery]:
    """Build username-wide web search queries — blogs, forums, images, events, emails, etc."""
    q = query.strip()
    if not q:
        return []

    qt = query_type or detect_query_type(q)
    ql = q.lower().replace(" ", "")
    escaped = q.replace('"', "")

    templates: list[tuple[str, str]] = []

    if qt == "email":
        from services.google_dorking.email_queries import build_email_dork_queries

        return build_email_dork_queries(q, max_queries=max_queries)
    elif qt == "domain":
        templates = [
            (f"site:{q}", "domain_site"),
            (f'site:{q} filetype:pdf', "domain_documents"),
            (f'site:{q} "contact"', "domain_contact"),
            (f'inurl:{q}', "domain_inurl"),
            (f'"{q}" email', "domain_email"),
            (f'intext:"{q}" profile OR account', "domain_profiles"),
        ]
    elif qt == "phone":
        compact = "".join(c for c in q if c.isdigit() or c == "+")
        templates = [
            (f'"{q}"', "phone_exact"),
            (f'"{compact}"', "phone_compact"),
            (f'intext:"{q}"', "phone_intext"),
            (f'intext:"{q}" email OR contact', "phone_contact"),
        ]
    else:
        # Plain Google search + comprehensive username intelligence slices.
        templates = [
            (escaped, "google_plain"),
            (f'"{escaped}"', "profile_exact"),
            (f'site:youtube.com OR site:youtu.be "{escaped}"', "media_video"),
            (f'site:github.com "{escaped}" OR inurl:{ql}', "code_mentions"),
            (f'inurl:portfolio OR inurl:about "{escaped}"', "portfolio_resume"),
            (f"inurl:{ql}", "web_inurl"),
            (f'intext:"{escaped}"', "web_intext"),
            (f'intext:"{escaped}" profile OR account OR user OR member', "profile_mentions"),
            (f'intext:"{escaped}" blog OR blogger OR weblog OR "blog post"', "blog_search"),
            (f'intext:"{escaped}" article OR story OR editorial OR feature OR write-up', "article_search"),
            (f'intext:"{escaped}" news OR headline OR press OR reported OR coverage', "news_mentions"),
            (f'intext:"{escaped}" forum OR discussion OR thread OR community OR "forum post"', "forum_mentions"),
            (f'intext:"{escaped}" {DISCUSSION_TERMS}', "discussion_search"),
            (f'intext:"{escaped}" {EVENT_TERMS}', "events_general"),
            (f'intext:"{escaped}" {ACHIEVEMENT_TERMS}', "achievements"),
            (f'intext:"{escaped}" hackathon OR devpost OR "coding contest" OR "hackathon winner"', "achievements"),
            (f'intext:"{escaped}" email OR "@" OR contact', "contact_email"),
            (f'intext:"{escaped}" phone OR mobile OR contact OR whatsapp', "contact_phone"),
            (f'"{escaped}" filetype:jpg OR filetype:png OR filetype:webp OR filetype:gif', "media_images"),
            (f'inurl:{ql} (filetype:jpg OR filetype:png OR filetype:webp OR filetype:gif)', "media_images_inurl"),
            (f'intext:"{escaped}" photo OR picture OR avatar OR headshot OR portrait', "media_images"),
            (f'intext:"{escaped}" video OR channel OR watch OR youtube OR vimeo', "media_video"),
            (f'intext:"{escaped}" university OR college OR institute OR school OR alumni', "education"),
            (
                build_site_or_query(
                    generic_search_domains(2),
                    f'"{escaped}"',
                    "hackathon OR winner OR won OR award OR fest OR college OR university",
                ),
                "achievements",
            ),
            (f'filetype:pdf "{escaped}"', "documents"),
            (f'intext:"{escaped}" resume OR cv OR portfolio OR about me', "portfolio_resume"),
            (f'intext:"{escaped}" repository OR repo OR github OR gitlab OR source code', "code_mentions"),
            (f'inurl:portfolio OR inurl:about OR inurl:resume "{escaped}"', "portfolio_resume"),
            (f'(site:pastebin.com OR site:hastebin.com OR site:ghostbin.com) "{escaped}"', "paste_sites"),
            (f'(site:medium.com OR site:dev.to OR site:hashnode.dev OR site:substack.com) "{escaped}"', "dev_blogs"),
        ]
        for domain in (discovered_domains or [])[:5]:
            d = domain.strip().lower().replace("www.", "")
            if d and d not in (ql, escaped.lower()):
                templates.append((f'site:{d} "{escaped}"', "discovered_domain"))

    seen: set[str] = set()
    out: list[DorkQuery] = []
    for text, category in templates:
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(DorkQuery(query=text, category=category))

    for extra in extra_queries or []:
        if extra.query and extra.query not in seen:
            seen.add(extra.query)
            out.insert(0, extra)

    if qt not in ("email", "domain", "phone"):
        def _sort_key(d: DorkQuery) -> tuple[int, int, str]:
            if d.category == "serp_discovered":
                return (0, 0, d.query)
            if d.category == "google_plain":
                return (0, 1, d.category)
            if d.category in PRIORITY_CATEGORIES:
                return (0, 2, d.category)
            return (1, 0, d.category)

        out.sort(key=_sort_key)
    return out[:max_queries]
