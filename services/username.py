import re


def normalize_username(query: str) -> tuple[str, list[str]]:
    """Normalize a username handle for OSINT scanners."""
    original = query.strip()
    warnings: list[str] = []

    if not original:
        return original, warnings

    if re.search(r"\s", original):
        warnings.append(
            f"Query '{original}' contains spaces. Username tools expect handles; "
            "using a normalized form for scanning."
        )

    normalized = re.sub(r"[^\w.-]", "", original.replace(" ", ""))
    if not normalized:
        normalized = re.sub(r"\s+", "_", original).lower()
    else:
        normalized = normalized.lower()

    return normalized, warnings


def safe_filename(value: str) -> str:
    """Create a filesystem-safe slug from arbitrary query text."""
    slug = re.sub(r"[^\w.-]", "_", value.strip())
    return slug or "query"
