"""Parse single or multi-field investigation targets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", re.IGNORECASE)
PHONE_RE = re.compile(r"^\+?[\d\s\-().]{7,20}$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", re.IGNORECASE)
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")

KV_RE = re.compile(
    r"^\s*(username|user|email|phone|domain|name|occupation|job|title|role|company|org)\s*[:=]\s*(.+)$",
    re.IGNORECASE,
)
SPLIT_RE = re.compile(r"[\|;/\n]+|(?:\s+\+\s+)")


@dataclass
class InvestigationInputs:
    raw: str
    username: str | None = None
    email: str | None = None
    phone: str | None = None
    domain: str | None = None
    name: str | None = None
    occupation: str | None = None
    company: str | None = None
    extras: list[str] = field(default_factory=list)

    @property
    def is_multi(self) -> bool:
        signals = sum(
            1
            for v in (self.username, self.email, self.phone, self.domain, self.name, self.occupation)
            if v
        )
        return signals > 1 or bool(self.extras)

    @property
    def primary_type(self) -> str:
        import os

        if os.path.isfile(self.raw) and self.raw.lower().endswith(IMAGE_EXTENSIONS):
            return "image"
        if self.is_multi:
            return "multi"
        if self.email:
            return "email"
        if self.phone:
            return "phone"
        if self.domain:
            return "domain"
        if self.username:
            return "username"
        return "username"

    def dork_query(self) -> str:
        parts = [p for p in (self.name, self.username, self.occupation, self.company, self.email) if p]
        if not parts:
            return self.raw.strip()
        return " ".join(parts)


def attribution_seed_query(inputs: InvestigationInputs) -> str:
    """Username or email for handle matching — never the full pipe-separated raw string."""
    if inputs.username:
        return inputs.username
    if inputs.email:
        return inputs.email
    return inputs.raw.strip()


def attribution_seed_from_raw(raw: str) -> str:
    """Parse once and return the attribution seed for filters / correlation."""
    return attribution_seed_query(parse_investigation_input(raw))


def investigation_context_tokens(inputs: InvestigationInputs) -> list[str]:
    """All user-supplied identifiers for SERP / dork attribution (username + email + name)."""
    tokens: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        if not value:
            return
        clean = value.strip()
        if not clean or clean.lower() in seen:
            return
        seen.add(clean.lower())
        tokens.append(clean)

    add(inputs.username)
    add(inputs.email)
    add(inputs.name)
    return tokens


def _clean_token(token: str) -> str:
    return token.strip().strip('"').strip("'")


def _assign_token(inputs: InvestigationInputs, token: str) -> None:
    t = _clean_token(token)
    if not t:
        return

    kv = KV_RE.match(t)
    if kv:
        key, val = kv.group(1).lower(), _clean_token(kv.group(2))
        if key in ("username", "user"):
            inputs.username = val.lstrip("@")
        elif key == "email":
            inputs.email = val.lower()
        elif key == "phone":
            inputs.phone = val
        elif key == "domain":
            inputs.domain = val.lower()
        elif key == "name":
            inputs.name = val
        elif key in ("occupation", "job", "title", "role"):
            inputs.occupation = val
        elif key in ("company", "org"):
            inputs.company = val
        return

    if EMAIL_RE.match(t):
        inputs.email = t.lower()
        return
    if PHONE_RE.match(t):
        inputs.phone = t
        return
    if DOMAIN_RE.match(t) and "@" not in t:
        inputs.domain = t.lower()
        return
    if t.lower().endswith(IMAGE_EXTENSIONS):
        inputs.extras.append(t)
        return

    words = t.split()
    if len(words) >= 2 and not inputs.name and "@" not in t:
        inputs.name = t
        return
    if not inputs.username and re.match(r"^[\w.-]{2,32}$", t):
        inputs.username = t.lstrip("@")
        return

    inputs.extras.append(t)


def parse_investigation_input(query: str) -> InvestigationInputs:
    raw = query.strip()
    inputs = InvestigationInputs(raw=raw)
    if not raw:
        return inputs

    segments = [s.strip() for s in SPLIT_RE.split(raw) if s.strip()]
    if len(segments) <= 1:
        segments = [raw]

    for seg in segments:
        _assign_token(inputs, seg)

    if not any((inputs.username, inputs.email, inputs.phone, inputs.domain, inputs.name)):
        import os

        if os.path.isfile(raw) and raw.lower().endswith(IMAGE_EXTENSIONS):
            inputs.extras.append(raw)
        elif EMAIL_RE.match(raw):
            inputs.email = raw.lower()
        elif PHONE_RE.match(raw):
            inputs.phone = raw
        elif DOMAIN_RE.match(raw) and "@" not in raw:
            inputs.domain = raw.lower()
        else:
            inputs.username = raw.lstrip("@")

    return inputs
