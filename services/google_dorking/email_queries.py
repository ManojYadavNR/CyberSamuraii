"""Email-specific Google dork templates — separate from username dork logic."""

from __future__ import annotations

from services.google_dorking.queries import DorkQuery, EVENT_TERMS

CONSUMER_MAIL = frozenset({
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "icloud.com",
    "protonmail.com",
    "proton.me",
    "aol.com",
})


def build_email_dork_queries(email: str, *, max_queries: int = 14) -> list[DorkQuery]:
    """Build web-search queries for an email address (incl. Gmail-specific slices)."""
    q = email.strip()
    if not q or "@" not in q:
        return []

    local, _, domain = q.partition("@")
    domain_l = domain.strip().lower()
    escaped = q.replace('"', "")
    local_esc = local.replace('"', "")

    templates: list[tuple[str, str]] = [
        (f'"{escaped}"', "email_exact"),
        (f'intext:"{escaped}"', "email_intext"),
        (f'"{local_esc}" "@{domain}"', "email_local_domain"),
        (f'intext:"{escaped}" {EVENT_TERMS}', "email_events"),
        (f'filetype:pdf "{escaped}"', "email_documents"),
        (f'intext:"{escaped}" phone OR mobile OR contact', "email_phone"),
        (f'"{escaped}" filetype:jpg OR filetype:png OR filetype:webp', "email_images"),
        (f'intext:"{escaped}" resume OR cv OR portfolio OR "about me"', "email_resume"),
        (
            f'(site:github.com OR site:gitlab.com OR site:stackoverflow.com) intext:"{escaped}"',
            "email_dev_profiles",
        ),
        (
            f'(site:pastebin.com OR site:hastebin.com OR site:ghostbin.com) "{escaped}"',
            "email_pastes",
        ),
        (f'site:linkedin.com intext:"{escaped}"', "email_linkedin"),
        (f'(site:twitter.com OR site:x.com) intext:"{escaped}"', "email_social"),
        (f'intext:"{escaped}" leak OR breach OR paste OR exposed', "email_breach_mentions"),
        (f'filetype:csv OR filetype:xls OR filetype:xlsx intext:"{escaped}"', "email_spreadsheets"),
        (f'intext:"{escaped}" author OR byline OR contributor OR writer', "email_publications"),
        (f'intext:"{escaped}" forum OR discussion OR thread OR community', "email_forums"),
        (f'site:gravatar.com "{escaped}"', "email_gravatar"),
        (
            f'(site:medium.com OR site:dev.to OR site:hashnode.dev OR site:substack.com) intext:"{escaped}"',
            "email_blogs",
        ),
    ]

    if domain_l in ("gmail.com", "googlemail.com"):
        templates.extend([
            (f'intext:"{local_esc}" gmail', "email_gmail_local"),
            (f'"{local_esc}" gmail.com', "email_gmail_handle"),
            (f'site:groups.google.com "{local_esc}" OR "{escaped}"', "email_google_groups"),
            (f'site:github.com "{local_esc}" OR intext:"{escaped}"', "email_gmail_github"),
            (
                f'intext:"{escaped}" OR intext:"{local_esc}@gmail.com" hackathon OR devpost OR "coding contest"',
                "email_gmail_hackathons",
            ),
            (f'site:docs.google.com intext:"{escaped}"', "email_gmail_docs"),
            (f'intext:"{escaped}" site:reddit.com OR site:quora.com', "email_gmail_qa"),
        ])
    elif domain_l not in CONSUMER_MAIL:
        templates.extend([
            (f'site:{domain_l} "{escaped}"', "email_org_site"),
            (f'intext:"{escaped}" site:{domain_l}', "email_org_intext"),
            (f'filetype:pdf site:{domain_l} "{local_esc}"', "email_org_documents"),
        ])

    seen: set[str] = set()
    out: list[DorkQuery] = []
    for text, category in templates:
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(DorkQuery(query=text, category=category))

    return out[:max_queries]
