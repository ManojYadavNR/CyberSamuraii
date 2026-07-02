"""Rule-based Investigation Brief — instant copilot facts without LLM."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
_TEMPLATE_RE = re.compile(r"\{(?:username|q|handle)\}", re.I)
_COLLEGE_RE = re.compile(r"\b(college|university|institute|campus|school)\b", re.I)
_HACKATHON_RE = re.compile(r"\bhackathon\b", re.I)


def is_template_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return bool(_TEMPLATE_RE.search(t) or re.search(r"\{[a-z_]+\}", t, re.I))


def resolve_investigation_url(url: str, query: str) -> str | None:
    u = (url or "").strip().strip("<>")
    if not u:
        return None
    if is_template_text(u) and query:
        u = _TEMPLATE_RE.sub(query.strip(), u)
        u = re.sub(r"\{[a-z_]+\}", query.strip(), u, flags=re.I)
    if is_template_text(u) or "{" in u:
        return None
    if not u.startswith("http"):
        return None
    return u


def format_account_line(account: dict[str, Any], query: str) -> str | None:
    platform = str(account.get("platform") or "").strip() or "?"
    handle = str(account.get("handle") or query or "").strip()
    tool = str(account.get("tool") or "").strip()
    url = resolve_investigation_url(str(account.get("url") or ""), query)
    prefix = f"[{tool}] " if tool else ""
    if url:
        label = handle or platform
        return f"• {prefix}**{platform}** — {label}: [{url}]({url})"
    if handle and not is_template_text(handle):
        return f"• {prefix}**{platform}** — {handle}"
    return None


def empty_brief(*, investigation_id: str = "", query: str = "") -> dict[str, Any]:
    return {
        "version": 1,
        "investigation_id": investigation_id,
        "query": query,
        "status": "indexing",
        "tools_done": [],
        "facts": _empty_facts(),
        "by_tool": {},
        "llm_notes": {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _empty_facts() -> dict[str, list[Any]]:
    return {
        "accounts": [],
        "urls": [],
        "colleges": [],
        "hackathons": [],
        "instagram_posts": [],
        "facebook_posts": [],
        "bios": [],
        "handles": [],
        "titles": [],
        "snippets": [],
        "errors": [],
        "platforms": [],
    }


def _dedupe_str(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _walk_strings(obj: Any, out: list[str], *, depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(obj, str) and len(obj) > 2:
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_strings(v, out, depth=depth + 1)
    elif isinstance(obj, list):
        for v in obj[:200]:
            _walk_strings(v, out, depth=depth + 1)


def extract_tool_facts(tool_result: dict[str, Any]) -> dict[str, Any]:
    """Parse one tool result into structured facts (no LLM)."""
    tool = str(tool_result.get("tool") or "unknown")
    facts = _empty_facts()
    blob_parts: list[str] = []
    _walk_strings(tool_result.get("data"), blob_parts)
    if tool_result.get("raw_output"):
        blob_parts.append(str(tool_result["raw_output"])[:8000])
    blob = "\n".join(blob_parts)

    for url in _URL_RE.findall(blob):
        facts["urls"].append(url[:500])

    if not tool_result.get("success"):
        err = str(tool_result.get("error") or "tool failed")
        facts["errors"].append(f"{tool}: {err}")

    data = tool_result.get("data") or []
    if not isinstance(data, list):
        data = [data]

    for row in data:
        if not isinstance(row, dict):
            continue
        platform = str(row.get("platform") or row.get("site") or row.get("source") or "")
        handle = str(row.get("handle") or row.get("username") or row.get("user") or "")
        url = str(row.get("url") or row.get("link") or "")
        title = str(row.get("title") or row.get("name") or "")
        snippet = str(row.get("snippet") or row.get("description") or row.get("bio") or row.get("biography") or "")

        if platform or handle:
            facts["accounts"].append({
                "tool": tool,
                "platform": platform,
                "handle": handle,
                "url": url,
            })
            if handle:
                facts["handles"].append(handle)
            if platform:
                facts["platforms"].append(platform)

        if title:
            facts["titles"].append(title)
        if snippet:
            facts["snippets"].append(snippet[:500])
            if "bio" in row or "biography" in row or "biography" in snippet.lower():
                facts["bios"].append(snippet[:500])

        text = f"{title} {snippet} {url}".lower()
        if _COLLEGE_RE.search(text):
            facts["colleges"].append({"tool": tool, "title": title, "snippet": snippet[:300], "url": url})
        if _HACKATHON_RE.search(text):
            facts["hackathons"].append({"tool": tool, "title": title, "snippet": snippet[:300], "url": url})

        # Samurai-shaped rows
        if row.get("recent_posts") and isinstance(row["recent_posts"], list):
            for post in row["recent_posts"]:
                if isinstance(post, dict):
                    facts["instagram_posts"].append({**post, "tool": tool})
        if row.get("reels") and isinstance(row["reels"], list):
            for reel in row["reels"]:
                if isinstance(reel, dict):
                    facts["instagram_posts"].append({**reel, "tool": tool, "type": "reel"})

        if tool == "samurai" or platform.lower() in ("instagram", "facebook"):
            _extract_samurai_row(row, tool, facts)

    # Dedupe list fields
    for key in ("urls", "handles", "platforms", "titles", "snippets", "bios"):
        if key in facts and isinstance(facts[key], list) and facts[key] and isinstance(facts[key][0], str):
            facts[key] = _dedupe_str(facts[key])

    return {"tool": tool, "success": tool_result.get("success"), "facts": facts, "record_count": len(data)}


def _extract_samurai_row(row: dict[str, Any], tool: str, facts: dict[str, Any]) -> None:
    platform = str(row.get("platform") or "").lower()
    profile = row.get("profile") if isinstance(row.get("profile"), dict) else row

    bio = str(profile.get("biography") or profile.get("bio") or "")
    if bio:
        facts["bios"].append(bio[:500])

    posts = row.get("recent_posts") or profile.get("recent_posts") or []
    reels = row.get("reels") or profile.get("reels") or []
    if isinstance(posts, list):
        for p in posts:
            if isinstance(p, dict):
                facts["instagram_posts"].append({**p, "tool": tool})
    if isinstance(reels, list):
        for p in reels:
            if isinstance(p, dict):
                facts["instagram_posts"].append({**p, "tool": tool, "type": "reel"})

    fb_posts = row.get("timeline_posts") or row.get("posts") or []
    if isinstance(fb_posts, list):
        for p in fb_posts:
            if isinstance(p, dict):
                facts["facebook_posts"].append({**p, "tool": tool})


def merge_facts(into: dict[str, list[Any]], part: dict[str, list[Any]]) -> None:
    for key, items in part.items():
        if key not in into or not isinstance(items, list):
            continue
        into[key].extend(items)


def merge_brief_tool(brief: dict[str, Any], tool_result: dict[str, Any]) -> dict[str, Any]:
    extracted = extract_tool_facts(tool_result)
    tool = extracted["tool"]
    brief["by_tool"][tool] = extracted
    if tool not in brief["tools_done"]:
        brief["tools_done"].append(tool)
    merge_facts(brief["facts"], extracted["facts"])
    brief["updated_at"] = datetime.now(timezone.utc).isoformat()
    return brief


def finalize_brief_from_result(brief: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Add fusion, identity, evidence layers after full investigation."""
    evidence = result.get("evidence_extraction") or {}
    if isinstance(evidence, dict):
        gsi = evidence.get("google_search_intel")
        if gsi:
            brief["by_tool"]["google_search_intel"] = {"tool": "google_search_intel", "facts": _empty_facts(), "payload": gsi}
            _extract_evidence_hits(gsi, brief["facts"])

        samurai_intel = evidence.get("samurai_social_intel")
        if samurai_intel:
            brief["by_tool"]["samurai_social_intel"] = {
                "tool": "samurai_social_intel",
                "facts": _empty_facts(),
                "payload": samurai_intel,
            }
            _extract_samurai_intel(samurai_intel, brief["facts"])

        linguistic = evidence.get("linguistic_analysis")
        if isinstance(linguistic, dict):
            brief["linguistic_analysis"] = linguistic
            _extract_linguistic_intel(linguistic, brief["facts"])
            mode = linguistic.get("engine_mode")
            if mode:
                brief["facts"]["snippets"].append(f"[linguistic] engine: {mode}")

    identity = result.get("identity_profile")
    if identity:
        brief["identity_profile"] = identity

    fusion = result.get("fusion")
    if fusion:
        brief["fusion"] = fusion
        for ent in (fusion.get("deduplicated_entities") or [])[:50]:
            if isinstance(ent, dict):
                handle = ent.get("handle") or ent.get("username")
                platform = ent.get("platform") or ent.get("type")
                if handle:
                    brief["facts"]["handles"].append(str(handle))
                if platform:
                    brief["facts"]["platforms"].append(str(platform))

    correlation = result.get("correlation")
    if correlation:
        brief["correlation_summary"] = {
            "total_clusters": correlation.get("total_clusters"),
            "clusters": (correlation.get("clusters") or [])[:5],
        }
        for cluster in correlation.get("clusters") or []:
            if not isinstance(cluster, dict):
                continue
            for acct in cluster.get("linked_accounts") or []:
                if isinstance(acct, dict):
                    brief["facts"]["accounts"].append({
                        "tool": "correlation",
                        "platform": acct.get("platform"),
                        "handle": acct.get("handle"),
                        "url": acct.get("url"),
                    })

    brief["status"] = "ready"
    brief["updated_at"] = datetime.now(timezone.utc).isoformat()
    return brief


def _extract_evidence_hits(gsi: Any, facts: dict[str, list[Any]]) -> None:
    hits = []
    if isinstance(gsi, dict):
        hits = gsi.get("hits") or gsi.get("dork_hits") or []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "")
        snippet = str(hit.get("snippet") or "")
        url = str(hit.get("url") or "")
        text = f"{title} {snippet}"
        if title:
            facts["titles"].append(title)
        if snippet:
            facts["snippets"].append(snippet[:500])
        if url:
            facts["urls"].append(url)
        if _COLLEGE_RE.search(text):
            facts["colleges"].append({"title": title, "snippet": snippet[:300], "url": url})
        if _HACKATHON_RE.search(text):
            facts["hackathons"].append({"title": title, "snippet": snippet[:300], "url": url})


def _extract_samurai_intel(intel: Any, facts: dict[str, list[Any]]) -> None:
    if not isinstance(intel, dict):
        return
    ig = intel.get("instagram")
    if isinstance(ig, dict):
        _extract_samurai_row({**ig, "platform": "instagram"}, "samurai", facts)
    fb = intel.get("facebook")
    if isinstance(fb, dict):
        _extract_samurai_row({**fb, "platform": "facebook"}, "samurai", facts)


def _extract_linguistic_intel(linguistic: dict[str, Any], facts: dict[str, list[Any]]) -> None:
    """Index linguistic signals into brief facts for copilot search."""
    if not isinstance(linguistic, dict):
        return
    lp = linguistic.get("language_profile") or {}
    primary = lp.get("primary")
    if primary:
        facts["snippets"].append(f"[linguistic] primary language: {primary}")
    for topic in linguistic.get("topics") or []:
        if isinstance(topic, dict) and topic.get("topic"):
            label = str(topic["topic"])
            score = topic.get("score")
            facts["snippets"].append(f"[linguistic] topic {label} (score {score})")
            for snip in (topic.get("evidence_snippets") or [])[:2]:
                if isinstance(snip, str) and snip.strip():
                    facts["snippets"].append(snip[:300])
    for ent in linguistic.get("named_entities") or []:
        if not isinstance(ent, dict):
            continue
        kind = str(ent.get("kind") or "")
        text = str(ent.get("text") or "")
        if not text:
            continue
        if kind == "url" and text.startswith("http"):
            facts["urls"].append(text)
        elif kind in ("email", "handle", "hashtag"):
            facts["handles"].append(text)
    for link in linguistic.get("cross_links") or []:
        if isinstance(link, dict) and link.get("detail"):
            facts["snippets"].append(f"[linguistic] {link.get('kind', 'link')}: {link['detail'][:200]}")
    for contra in linguistic.get("contradictions") or []:
        if isinstance(contra, dict) and contra.get("detail"):
            facts["snippets"].append(f"[linguistic] contradiction: {contra['detail'][:200]}")


def brief_to_text(brief: dict[str, Any]) -> str:
    """Compact text for optional single LLM synthesis call."""
    import json

    slim = {
        "query": brief.get("query"),
        "status": brief.get("status"),
        "tools_done": brief.get("tools_done"),
        "facts": brief.get("facts"),
        "by_tool": brief.get("by_tool"),
        "fusion_score": (brief.get("fusion") or {}).get("fusion_score"),
        "identity_profile": brief.get("identity_profile"),
        "correlation_summary": brief.get("correlation_summary"),
        "linguistic_analysis": brief.get("linguistic_analysis"),
    }
    return json.dumps(slim, ensure_ascii=False, separators=(",", ":"))[:22000]


_STOP_WORDS = frozenset({
    "the", "and", "for", "are", "was", "were", "what", "when", "where", "which",
    "who", "how", "why", "this", "that", "with", "from", "about", "have", "has",
    "had", "can", "you", "your", "our", "any", "all", "did", "does", "tell", "show",
    "give", "find", "get", "me", "we", "they", "them", "their", "there", "into",
})


def _question_tokens(message: str) -> list[str]:
    tokens = [
        w for w in re.findall(r"[a-z0-9]+", message.lower())
        if len(w) > 2 and w not in _STOP_WORDS
    ]
    # Hinglish / Hindi intent helpers (roman)
    for word in ("instagram", "insta", "facebook", "github", "linkedin", "pinterest", "account", "college", "hackathon"):
        if word in message.lower():
            tokens.append(word)
    if "instagram" in message.lower() or "insta" in message.lower() or "इंस्टाग्राम" in message:
        tokens.extend(["instagram", "samurai"])
    if "facebook" in message.lower() or "fb" in message.lower():
        tokens.extend(["facebook", "samurai"])
    return list(dict.fromkeys(tokens))


def _question_intents(message: str) -> set[str]:
    lower = message.lower()
    intents: set[str] = set()
    if any(k in lower for k in ("instagram", "insta", " ig ", "इंस्टाग्राम")):
        intents.add("instagram")
    if any(k in lower for k in ("facebook", " fb ", "फेसबुक")):
        intents.add("facebook")
    if any(k in lower for k in ("account", "linked", "platform", "खाता")):
        intents.add("accounts")
    if any(k in lower for k in ("college", "school", "university", "कॉलेज")):
        intents.add("college")
    if "hackathon" in lower:
        intents.add("hackathon")
    if any(k in lower for k in ("hindi", "language", "bhasha", "भाषा", "english")):
        intents.add("meta")
    return intents


def _score_text(text: str, tokens: list[str]) -> int:
    if not text or not tokens:
        return 0
    lower = text.lower()
    return sum(2 if t in lower else 0 for t in tokens)


def _is_overview_question(message: str, tokens: list[str]) -> bool:
    lower = message.lower()
    if any(
        w in lower
        for w in (
            "summarize", "summary", "overview", "everything", "full picture",
            "poora", "sab kuch", "full case", "complete overview",
        )
    ):
        return True
    if any(p in lower for p in ("evidence breakdown", "suspect activity", "linked accounts")):
        return True
    return False


def _format_brief_overview(brief: dict[str, Any]) -> str:
    facts = brief.get("facts") or {}
    query = brief.get("query") or "target"
    tools = brief.get("tools_done") or []
    fusion = brief.get("fusion") or {}
    score = fusion.get("fusion_score")

    lines = [f"Investigation overview for **{query}**:"]
    lines.append(f"• Tools completed: {', '.join(tools) if tools else 'none'}")
    lines.append(f"• Accounts indexed: {len(facts.get('accounts') or [])}")
    lines.append(f"• URLs: {len(facts.get('urls') or [])}")
    lines.append(f"• Colleges: {len(facts.get('colleges') or [])}")
    lines.append(f"• Hackathons: {len(facts.get('hackathons') or [])}")
    lines.append(f"• Instagram posts: {len(facts.get('instagram_posts') or [])}")
    lines.append(f"• Facebook posts: {len(facts.get('facebook_posts') or [])}")
    if score is not None:
        lines.append(f"• Fusion confidence: {float(score) * 100:.0f}%")

    for a in (facts.get("accounts") or [])[:12]:
        if isinstance(a, dict):
            line = format_account_line(a, str(query))
            if line:
                lines.append(f"  {line}")
    return "\n".join(lines)


def _iter_search_records(brief: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Yield (category, tool, text) records from the brief."""
    facts = brief.get("facts") or {}
    records: list[tuple[str, str, str]] = []

    q = str(brief.get("query") or "")
    for a in facts.get("accounts") or []:
        if isinstance(a, dict):
            tool = str(a.get("tool") or "")
            line = format_account_line(a, q)
            if line:
                records.append(("account", tool, line.lstrip("• ").strip()))
            else:
                text = f"{a.get('platform', '')} {a.get('handle', '')}"
                if text.strip() and not is_template_text(text):
                    records.append(("account", tool, text.strip()))

    for key, label in (
        ("bios", "bio"),
        ("titles", "title"),
        ("snippets", "snippet"),
        ("handles", "handle"),
        ("platforms", "platform"),
        ("urls", "url"),
    ):
        for item in facts.get(key) or []:
            if not isinstance(item, str) or not item.strip() or is_template_text(item):
                continue
            if key == "urls":
                resolved = resolve_investigation_url(item, q)
                if resolved:
                    records.append((label, "", resolved))
            else:
                records.append((label, "", item.strip()))

    for c in facts.get("colleges") or []:
        if isinstance(c, dict):
            tool = str(c.get("tool") or "google_dorking")
            text = f"{c.get('title', '')} {c.get('snippet', '')} {c.get('url', '')}"
            records.append(("college", tool, text.strip()))

    for h in facts.get("hackathons") or []:
        if isinstance(h, dict):
            tool = str(h.get("tool") or "google_dorking")
            text = f"{h.get('title', '')} {h.get('snippet', '')} {h.get('url', '')}"
            records.append(("hackathon", tool, text.strip()))

    for p in facts.get("instagram_posts") or []:
        if isinstance(p, dict):
            tool = str(p.get("tool") or "samurai")
            cap = str(p.get("caption") or "")
            url = str(p.get("url") or p.get("live_url") or "")
            records.append(("instagram_post", tool, f"{cap} {url}".strip()))

    for p in facts.get("facebook_posts") or []:
        if isinstance(p, dict):
            tool = str(p.get("tool") or "samurai")
            text = f"{p.get('title') or p.get('caption') or ''} {p.get('url') or ''}"
            records.append(("facebook_post", tool, text.strip()))

    for err in facts.get("errors") or []:
        if isinstance(err, str):
            records.append(("error", "", err))

    for tool_name in brief.get("tools_done") or []:
        records.append(("tool", str(tool_name), f"tool {tool_name} completed"))

    fusion = brief.get("fusion")
    if isinstance(fusion, dict):
        score = fusion.get("fusion_score")
        if score is not None:
            records.append(("fusion", "fusion", f"fusion confidence {float(score) * 100:.0f}%"))

    identity = brief.get("identity_profile")
    if isinstance(identity, dict):
        blob: list[str] = []
        _walk_strings(identity, blob)
        clean_urls = [
            u for s in blob
            for u in _URL_RE.findall(s)
            if not is_template_text(u) and resolve_investigation_url(u, q)
        ]
        if clean_urls:
            records.append(("identity", "fusion", " ".join(_dedupe_str(clean_urls)[:8])))

    return records


def search_brief_answer(message: str, brief: dict[str, Any]) -> str:
    answer, _ = search_brief_with_match(message, brief)
    return answer


def search_brief_with_match(message: str, brief: dict[str, Any]) -> tuple[str, bool]:
    """
    Answer any analyst question by searching indexed investigation facts.
    Returns (answer, matched) where matched=False means no relevant facts found.
    """
    query = brief.get("query") or "target"
    tokens = _question_tokens(message)
    msg_lower = message.lower()

    if _is_overview_question(message, tokens):
        return _format_brief_overview(brief), True

    # Tool-name match (e.g. "what did samurai find", "maigret results")
    tool_hits: list[str] = []
    for tool in brief.get("tools_done") or []:
        t = str(tool).lower()
        if t in msg_lower or t.replace("_", " ") in msg_lower:
            entry = (brief.get("by_tool") or {}).get(tool) or {}
            facts = entry.get("facts") or brief.get("facts") or {}
            count = entry.get("record_count")
            if count is None and isinstance(facts, dict):
                count = len(facts.get("accounts") or facts.get("snippets") or [])
            tool_hits.append(f"• **{tool}**: {count or 0} records indexed")
            for a in (facts.get("accounts") if isinstance(facts, dict) else []) or []:
                if isinstance(a, dict):
                    line = format_account_line(a, str(query))
                    if line:
                        tool_hits.append(f"  {line}")
            for s in (facts.get("snippets") if isinstance(facts, dict) else []) or []:
                if isinstance(s, str):
                    tool_hits.append(f"  - {s[:120]}")
    if tool_hits:
        return f"Findings from matched tools for **{query}**:\n" + "\n".join(tool_hits[:30]), True

    records = _iter_search_records(brief)
    if not records:
        tools = brief.get("tools_done") or []
        if tools:
            return (
                f"Investigation on **{query}** is still indexing ({', '.join(tools)} done so far). "
                "Try again in a moment or ask for an overview."
            ), False
        return f"No investigation data indexed yet for **{query}**.", False

    scored: list[tuple[int, str, str, str]] = []
    for category, tool, text in records:
        score = _score_text(text, tokens)
        score += _score_text(category, tokens)
        if score > 0:
            scored.append((score, category, tool, text))

    if not scored:
        if _is_overview_question(message, tokens):
            return _format_brief_overview(brief), True
        return (
            f"No answer for this question was found in the investigation data for **{query}**.\n"
            f"Question: {message.strip()}"
        ), False

    scored.sort(key=lambda x: (-x[0], x[1]))
    top_score = scored[0][0]
    if top_score < 2 and not _question_intents(message):
        return (
            f"No answer for this question was found in the investigation data for **{query}**.\n"
            f"Question: {message.strip()}"
        ), False

    lines: list[str] = []
    seen: set[str] = set()
    for score, category, tool, text in scored[:12]:
        if is_template_text(text):
            continue
        key = text[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        if text.startswith("**") or text.startswith("["):
            lines.append(f"• {text[:320]}")
        else:
            prefix = f"[{tool}] " if tool else ""
            lines.append(f"• {prefix}{text[:320]}")

    if not lines:
        return f"No verified links found in the data for **{query}**.", False

    return "\n".join(lines), True


def focused_brief_context(message: str, brief: dict[str, Any], *, max_chars: int = 6000) -> str:
    """Small context slice — only facts relevant to the analyst's question."""
    import json

    intents = _question_intents(message)
    tokens = _question_tokens(message)
    records = _iter_search_records(brief)
    scored = [
        (_score_text(text, tokens) + _score_text(cat, tokens), cat, tool, text)
        for cat, tool, text in records
    ]

    if intents and "meta" not in intents:
        filtered = []
        for score, cat, tool, text in scored:
            blob = f"{cat} {tool} {text}".lower()
            if "instagram" in intents and any(k in blob for k in ("instagram", "samurai", "insta")):
                filtered.append((score + 5, cat, tool, text))
            elif "facebook" in intents and any(k in blob for k in ("facebook", "fb")):
                filtered.append((score + 5, cat, tool, text))
            elif "accounts" in intents and cat in ("account", "platform", "handle"):
                filtered.append((score + 3, cat, tool, text))
            elif "college" in intents and cat == "college":
                filtered.append((score + 5, cat, tool, text))
            elif "hackathon" in intents and cat == "hackathon":
                filtered.append((score + 5, cat, tool, text))
        if filtered:
            scored = filtered

    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda x: -x[0])

    if not scored and intents:
        # Narrow fallback — still only intent-related records
        for cat, tool, text in records:
            blob = f"{cat} {tool} {text}".lower()
            if "instagram" in intents and "instagram" in blob:
                scored.append((1, cat, tool, text))
            elif "facebook" in intents and "facebook" in blob:
                scored.append((1, cat, tool, text))

    if not scored:
        if not intents:
            return json.dumps(
                {
                    "query": brief.get("query"),
                    "question": message,
                    "relevant_facts": [],
                    "note": "No facts match this question — say so briefly if data is irrelevant",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )[:max_chars]
        q = str(brief.get("query") or "")
        verified = []
        for a in (brief.get("facts") or {}).get("accounts", [])[:12]:
            if isinstance(a, dict):
                line = format_account_line(a, q)
                if line:
                    verified.append(line.lstrip("• ").strip())
        slim = {
            "query": brief.get("query"),
            "question": message,
            "intents": list(intents),
            "note": "Only use verified accounts below — never invent URL templates",
            "verified_accounts": verified[:8],
        }
        return json.dumps(slim, ensure_ascii=False, separators=(",", ":"))[:max_chars]

    body = {
        "query": brief.get("query"),
        "question": message,
        "intents": list(intents),
        "matched_facts": [
            {"category": c, "tool": t, "text": x[:400]}
            for _, c, t, x in scored[:20]
        ],
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))[:max_chars]
