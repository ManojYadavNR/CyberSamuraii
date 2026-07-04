"""Google dorking — web search + SERP-style intelligence extraction for usernames."""

from __future__ import annotations

import asyncio
import re
import time

from adapters.base import BaseAdapter
from adapters.scan_summary import scan_summary_entry
from schemas.common import ToolResult
from services.discovery.attribution import email_attributed_to_username, phone_attributed_to_username
from services.discovery.validators import normalize_domain
from services.evidence.platform_deep import is_enrichable_profile_url
from services.google_dorking.client import run_dork_queries
from services.google_dorking.dynamic_queries import (
    build_college_instagram_queries,
    build_display_name_seed_queries,
    build_dynamic_dork_queries,
    build_fallback_social_queries,
)
from services.google_dorking.keyword_discovery import extract_keywords_from_serp
from services.google_dorking.queries import build_dork_queries
from services.google_dorking.serp_parser import process_search_hit
from services.query_detector import detect_query_type


class GoogleDorkingAdapter(BaseAdapter):
    name = "google_dorking"
    default_timeout = 150.0
    max_retries = 0

    def __init__(self) -> None:
        super().__init__()
        self._accumulated_hits: list[dict] = []
        self._partial_results: list[dict] = []
        self._last_query = ""
        self._last_query_type = ""

    def verify_tool(self) -> tuple[bool, str | None]:
        return True, None

    async def run(self, query: str, timeout: float | None = None, on_progress=None) -> ToolResult:
        """Internal deadline — return partial dork hits instead of hard timeout failure."""
        start = time.monotonic()
        self._on_progress = on_progress
        self._accumulated_hits = []
        self._partial_results = []
        self._last_query = query
        budget = float(timeout or self.default_timeout)
        try:
            result = await self._execute(query, budget_sec=budget)
            result.execution_time_ms = (time.monotonic() - start) * 1000
            return result
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            partial = self._partial_tool_result()
            if partial:
                partial.execution_time_ms = (time.monotonic() - start) * 1000
                return partial
            if isinstance(exc, asyncio.CancelledError):
                raise
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Tool '{self.name}' timed out after {budget:.0f}s",
                execution_time_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as exc:
            partial = self._partial_tool_result()
            if partial:
                partial.execution_time_ms = (time.monotonic() - start) * 1000
                return partial
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Tool '{self.name}' failed: {type(exc).__name__}: {exc}",
                execution_time_ms=(time.monotonic() - start) * 1000,
            )

    def _partial_tool_result(self) -> ToolResult | None:
        if not self._partial_results and self._accumulated_hits:
            self._refresh_partial_results()
        if not self._partial_results:
            return None
        summary = scan_summary_entry(
            self.name,
            sites_checked=len(self._accumulated_hits),
            sites_found=len(self._partial_results),
            note="Partial dork results preserved after time budget",
        )
        return ToolResult(
            tool=self.name,
            success=True,
            data=[*self._partial_results, summary],
            raw_output=f"{len(self._accumulated_hits)} SERP hit(s), {len(self._partial_results)} row(s) (partial)",
        )

    def _record_hits(self, hits: list[dict]) -> None:
        if not hits:
            return
        self._accumulated_hits.extend(hits)
        self._refresh_partial_results()

    def _refresh_partial_results(self) -> None:
        if not self._accumulated_hits or not self._last_query:
            return
        query = self._last_query
        query_type = self._last_query_type or detect_query_type(query)
        results: list[dict] = []
        for hit in self._accumulated_hits:
            processed = process_search_hit(hit, seed_query=query, query_type=query_type)
            if not processed:
                continue
            self._append_document(results, processed, query_type)
            if query_type == "email":
                self._append_email_derived(results, processed=processed, query=query)
        self._partial_results = results

    def _append_document(self, results: list[dict], processed: dict, query_type: str) -> None:
        url = str(processed.get("url") or "")
        title = str(processed.get("title") or "")
        snippet = str(processed.get("snippet") or "")
        dork = str(processed.get("dork_query") or "")
        category = str(processed.get("dork_category") or "general")
        platform = str(processed.get("platform") or "google_search")
        structured = processed.get("structured_intelligence") or {}
        text_blob = str(processed.get("serp_text_blob") or f"{title} {snippet}").strip()

        entry = self._normalize_entry(
            platform=platform,
            url=url,
            extra={
                "title": title,
                "snippet": snippet,
                "content": text_blob,
                "dork_query": dork,
                "dork_category": category,
                "check_type": "google_dork",
                "verified": False,
                "status": "search_reference",
                "query_type": query_type,
                "username_attributed": processed.get("username_attributed"),
                "deep_fetch": is_enrichable_profile_url(url),
                "serp_hit_type": processed.get("hit_type"),
                "serp_display_link": processed.get("serp_display_link"),
                "serp_source_engine": processed.get("serp_source_engine"),
                "structured_intelligence": structured,
                "parsed_fields": processed.get("parsed_fields") or [],
                "serp_phase": processed.get("serp_phase"),
                "trigger_keyword": processed.get("trigger_keyword"),
            },
        )
        results.append(entry)

    def _append_attributed_contacts(
        self,
        results: list[dict],
        *,
        processed: dict,
        query: str,
        title: str,
        snippet: str,
        url: str,
        dork: str,
        category: str,
    ) -> None:
        structured = processed.get("structured_intelligence") or {}
        emails = list(structured.get("emails") or [])
        phones = list(structured.get("phones") or [])

        for email in emails:
            if not email_attributed_to_username(
                email, query, source_url=url, title=title, snippet=snippet,
            ):
                continue
            results.append(
                self._normalize_entry(
                    platform="google_search",
                    extra={
                        "email": email,
                        "dork_query": dork,
                        "dork_category": category,
                        "check_type": "google_dork",
                        "verified": False,
                        "status": "username_attributed",
                        "username_attributed": True,
                        "source_url": url,
                        "discovery_source": "username_search",
                        "serp_hit_type": processed.get("hit_type"),
                    },
                )
            )

        for phone in phones:
            if not phone_attributed_to_username(
                phone, query, source_url=url, title=title, snippet=snippet,
            ):
                continue
            results.append(
                self._normalize_entry(
                    platform="google_search",
                    extra={
                        "phone_hint": phone,
                        "dork_query": dork,
                        "dork_category": category,
                        "check_type": "google_dork",
                        "verified": False,
                        "status": "username_attributed",
                        "username_attributed": True,
                        "source_url": url,
                        "discovery_source": "username_search",
                        "serp_hit_type": processed.get("hit_type"),
                    },
                )
            )

    def _append_images(self, results: list[dict], *, processed: dict, query: str) -> None:
        structured = processed.get("structured_intelligence") or {}
        dork = str(processed.get("dork_query") or "")
        category = str(processed.get("dork_category") or "general")
        source_url = str(processed.get("url") or "")

        for img_url in structured.get("images") or []:
            if not img_url.startswith("http"):
                continue
            results.append(
                self._normalize_entry(
                    platform=normalize_domain(img_url) or "google_search",
                    url=img_url,
                    extra={
                        "dork_query": dork,
                        "dork_category": category,
                        "check_type": "google_dork",
                        "verified": False,
                        "status": "search_reference",
                        "username_attributed": True,
                        "discovery_source": "username_search",
                        "source_url": source_url,
                        "serp_hit_type": "image",
                        "image_attributed": True,
                        "field": "images",
                    },
                )
            )

    def _append_embedded_links(self, results: list[dict], *, processed: dict, query: str) -> None:
        title = str(processed.get("title") or "")
        snippet = str(processed.get("snippet") or "")
        text_blob = f"{title} {snippet}"
        url = str(processed.get("url") or "")
        platform = str(processed.get("platform") or "")
        dork = str(processed.get("dork_query") or "")
        category = str(processed.get("dork_category") or "general")

        from services.discovery.attribution import dork_hit_attributed

        for match in re.findall(r"https?://[^\s<>\"']+", text_blob, flags=re.IGNORECASE):
            if not url or match == url:
                continue
            if not dork_hit_attributed(url=match, title=title, snippet=snippet, seed_query=query):
                continue
            domain = normalize_domain(match)
            if domain and domain != platform:
                results.append(
                    self._normalize_entry(
                        platform=domain,
                        url=match,
                        extra={
                            "dork_query": dork,
                            "dork_category": category,
                            "check_type": "google_dork",
                            "verified": False,
                            "status": "search_reference",
                            "reference_url": url,
                            "discovery_source": "username_search",
                            "username_attributed": True,
                            "serp_hit_type": processed.get("hit_type"),
                        },
                    )
                )

    def _append_email_derived(self, results: list[dict], *, processed: dict, query: str) -> None:
        """Extract usernames / linked emails from email-targeted SERP hits."""
        structured = processed.get("structured_intelligence") or {}
        title = str(processed.get("title") or "")
        snippet = str(processed.get("snippet") or "")
        url = str(processed.get("url") or "")
        dork = str(processed.get("dork_query") or "")
        category = str(processed.get("dork_category") or "general")
        email_lower = query.strip().lower()

        for email in structured.get("emails") or []:
            if str(email).lower() == email_lower:
                continue
            results.append(
                self._normalize_entry(
                    platform="google_search",
                    extra={
                        "email": email,
                        "dork_query": dork,
                        "dork_category": category,
                        "check_type": "google_dork",
                        "verified": False,
                        "status": "email_derived",
                        "query_type": "email",
                        "source_url": url,
                    },
                )
            )

        import re

        text_blob = f"{title} {snippet}".lower()
        if email_lower not in text_blob and email_lower.split("@", 1)[0] not in text_blob:
            return

        for handle in re.findall(r"@([\w.-]{3,30})\b", f"{title} {snippet}"):
            if handle.lower() in email_lower:
                continue
            results.append(
                self._normalize_entry(
                    platform="google_search",
                    extra={
                        "username": handle,
                        "dork_query": dork,
                        "dork_category": category,
                        "check_type": "google_dork",
                        "verified": False,
                        "status": "email_derived",
                        "query_type": "email",
                        "email_attributed": True,
                        "source_url": url,
                    },
                )
            )

    async def _run_dorks(self, *args, **kwargs) -> list[dict]:
        hits = await run_dork_queries(*args, **kwargs)
        self._record_hits(hits)
        return hits

    async def _execute(self, query: str, *, budget_sec: float = 120.0) -> ToolResult:
        query_type = detect_query_type(query)
        self._last_query = query
        self._last_query_type = query_type
        max_queries = 20 if query_type == "email" else (6 if query_type == "phone" else 28)
        base_dorks = build_dork_queries(query, query_type, max_queries=max_queries)
        if not base_dorks:
            return ToolResult(tool=self.name, success=False, error="No dork queries generated")

        results_per = 8 if query_type == "username" else 6
        deadline = time.monotonic() + max(20.0, budget_sec - 3.0)
        dork_categories = {d.query: d.category for d in base_dorks}

        seed_dorks = [d for d in base_dorks if d.category in ("google_plain", "profile_exact")]
        name_seeds = build_display_name_seed_queries(query)
        if name_seeds:
            seed_dorks = name_seeds + seed_dorks
        seed_queries = {d.query for d in seed_dorks}
        discovery_meta: dict = {}
        trigger_map: dict[str, str] = {}

        seed_hits: list[dict] = []
        social_hits: list[dict] = []
        if query_type == "username" and seed_dorks:
            seed_hits = await self._run_dorks(
                [d.query for d in seed_dorks],
                results_per_dork=max(10, results_per),
                max_concurrency=4,
                dork_categories=dork_categories,
                deadline_monotonic=deadline,
            )
            for hit in seed_hits:
                hit["serp_phase"] = "seed"

            # Pass 1 — Facebook/Instagram with display name + hackathon/college terms.
            fallback = build_fallback_social_queries(query)
            fallback_queries = [d.query for d in fallback]
            for d in fallback:
                dork_categories[d.query] = d.category
            if fallback_queries and time.monotonic() < deadline - 8:
                pass1 = await self._run_dorks(
                    fallback_queries,
                    results_per_dork=max(10, results_per),
                    max_concurrency=6,
                    dork_categories=dork_categories,
                    deadline_monotonic=deadline,
                )
                for hit in pass1:
                    hit["serp_phase"] = "social_pass1"
                social_hits.extend(pass1)

            college_ig = build_college_instagram_queries(query, seed_hits + social_hits)
            for d in college_ig:
                dork_categories[d.query] = d.category
            college_ig_queries = [d.query for d in college_ig]
            if college_ig_queries and time.monotonic() < deadline - 8:
                pass_college = await self._run_dorks(
                    college_ig_queries,
                    results_per_dork=max(10, results_per),
                    max_concurrency=4,
                    dork_categories=dork_categories,
                    deadline_monotonic=deadline,
                )
                for hit in pass_college:
                    hit["serp_phase"] = "social_college_ig"
                social_hits.extend(pass_college)

            # Extract hackathon/college terms from seed + social posts, then search again.
            keywords = extract_keywords_from_serp(seed_hits + social_hits, seed_query=query)
            dynamic = build_dynamic_dork_queries(query, keywords)
            seen_q = set(fallback_queries)
            round2_social = [
                d.query for d in dynamic
                if d.category == "social_post_search" and d.query not in seen_q
            ]
            for d in dynamic:
                dork_categories[d.query] = d.category
                for kw in keywords:
                    if kw.phrase and kw.phrase.lower() in d.query.lower():
                        trigger_map[d.query] = kw.phrase
                        break

            if round2_social and time.monotonic() < deadline - 8:
                pass2 = await self._run_dorks(
                    round2_social,
                    results_per_dork=max(10, results_per),
                    max_concurrency=6,
                    dork_categories=dork_categories,
                    deadline_monotonic=deadline,
                )
                for hit in pass2:
                    hit["serp_phase"] = "social_pass2"
                    hit["trigger_keyword"] = trigger_map.get(str(hit.get("dork_query") or ""), "")
                social_hits.extend(pass2)

            from services.evidence.college_enrichment import (
                build_college_campus_search_queries,
                prefetch_college_targets,
            )

            if time.monotonic() < deadline - 10:
                campus_targets = await prefetch_college_targets(query, seed_hits + social_hits)
                campus_dorks = build_college_campus_search_queries(query, campus_targets)
                for d in campus_dorks:
                    dork_categories[d.query] = d.category
                campus_queries = [d.query for d in campus_dorks]
                if campus_queries:
                    pass_campus = await self._run_dorks(
                        campus_queries,
                        results_per_dork=max(10, results_per),
                        max_concurrency=4,
                        dork_categories=dork_categories,
                        deadline_monotonic=deadline,
                    )
                    for hit in pass_campus:
                        hit["serp_phase"] = "social_campus_pass"
                    social_hits.extend(pass_campus)

            # Tier 2/3 — entity pivots + recursive keyword hop from enriched SERP.
            from services.google_dorking.pivot_queries import (
                build_pivot_dork_queries,
                extract_entity_pivots,
            )

            all_hits_so_far = seed_hits + social_hits
            pivots = extract_entity_pivots(all_hits_so_far, seed_query=query)
            pivot_dorks = build_pivot_dork_queries(query, pivots)
            round3_queries: list[str] = []
            seen_round3 = set(fallback_queries) | {d.query for d in dynamic}

            for d in pivot_dorks:
                dork_categories[d.query] = d.category
                if d.query not in seen_round3:
                    round3_queries.append(d.query)
                    seen_round3.add(d.query)

            hop_keywords = extract_keywords_from_serp(all_hits_so_far, seed_query=query)
            for d in build_dynamic_dork_queries(query, hop_keywords):
                dork_categories[d.query] = d.category
                if d.category == "social_post_search" and d.query not in seen_round3:
                    round3_queries.append(d.query)
                    seen_round3.add(d.query)

            if round3_queries and time.monotonic() < deadline - 5:
                pass3 = await self._run_dorks(
                    round3_queries[:14],
                    results_per_dork=max(10, results_per),
                    max_concurrency=5,
                    dork_categories=dork_categories,
                    deadline_monotonic=deadline,
                )
                for hit in pass3:
                    hit["serp_phase"] = "social_pass3"
                social_hits.extend(pass3)

            keywords = extract_keywords_from_serp(seed_hits + social_hits, seed_query=query)
            all_dynamic = build_dynamic_dork_queries(query, keywords)
            seen_dynamic = {d.query for d in fallback}
            for d in all_dynamic:
                if d.query not in seen_dynamic:
                    dynamic.append(d)
                    seen_dynamic.add(d.query)
                    dork_categories[d.query] = d.category

            discovery_meta = {
                "discovered_keywords": [k.to_dict() for k in keywords],
                "follow_up_queries": [d.query for d in dynamic],
                "seed_queries": list(seed_queries),
                "social_pass_hits": len(social_hits),
            }

            extra_dorks = [d for d in dynamic if d.query not in seed_queries and d.category != "social_post_search"]
            extra_texts = {x.query for x in extra_dorks}
            follow_dorks = [d for d in base_dorks if d.query not in seed_queries and d.query not in extra_texts]
            dorks = seed_dorks + extra_dorks + follow_dorks
        else:
            dorks = base_dorks

        remaining = [d.query for d in dorks if d.query not in seed_queries and dork_categories.get(d.query) != "social_post_search"]
        follow_hits: list[dict] = []
        if remaining:
            general_remaining = remaining

            if general_remaining:
                general_hits = await self._run_dorks(
                    general_remaining,
                    results_per_dork=results_per,
                    max_concurrency=8,
                    dork_categories=dork_categories,
                    deadline_monotonic=deadline,
                )
                for hit in general_hits:
                    hit.setdefault("serp_phase", "follow_up")
                    hit["trigger_keyword"] = trigger_map.get(str(hit.get("dork_query") or ""), "")
                follow_hits.extend(general_hits)

        if query_type == "username":
            hits = seed_hits + social_hits + follow_hits
        else:
            hits = await self._run_dorks(
                [d.query for d in dorks],
                results_per_dork=results_per,
                max_concurrency=8,
                dork_categories=dork_categories,
                deadline_monotonic=deadline,
            )

        if not hits:
            if query_type in ("phone", "email", "domain"):
                summary = scan_summary_entry(
                    self.name,
                    sites_checked=len(dorks),
                    sites_found=0,
                    note="No web mentions found for this target",
                )
                return ToolResult(
                    tool=self.name,
                    success=True,
                    data=[summary],
                    raw_output=f"0 SERP hit(s) for {query_type} target",
                )
            return ToolResult(
                tool=self.name,
                success=False,
                error="No dork results (search engines returned empty — try again or check network)",
            )

        results: list[dict] = []
        for hit in hits:
            dork_q = str(hit.get("dork_query") or "")
            hit["trigger_keyword"] = trigger_map.get(dork_q, hit.get("trigger_keyword", ""))
            processed = process_search_hit(hit, seed_query=query, query_type=query_type)
            if not processed:
                continue
            processed["serp_phase"] = hit.get("serp_phase")
            processed["trigger_keyword"] = hit.get("trigger_keyword")

            self._append_document(results, processed, query_type)

            if query_type == "email":
                self._append_email_derived(results, processed=processed, query=query)
                continue

            if query_type != "username":
                continue

            title = str(processed.get("title") or "")
            snippet = str(processed.get("snippet") or "")
            url = str(processed.get("url") or "")
            dork = str(processed.get("dork_query") or "")
            category = str(processed.get("dork_category") or "general")

            self._append_attributed_contacts(
                results,
                processed=processed,
                query=query,
                title=title,
                snippet=snippet,
                url=url,
                dork=dork,
                category=category,
            )
            self._append_images(results, processed=processed, query=query)
            self._append_embedded_links(results, processed=processed, query=query)

        if discovery_meta:
            results.append(
                self._normalize_entry(
                    platform="google_search",
                    url=f"serp-discovery:{query.split('|')[0].strip()[:48]}",
                    extra={
                        "check_type": "google_search_discovery",
                        "google_search_discovery": discovery_meta,
                        "verified": False,
                        "status": "metadata",
                    },
                )
            )

        if not results:
            summary = scan_summary_entry(
                self.name,
                sites_checked=len(dorks),
                sites_found=0,
                note=f"{len(hits)} raw SERP hit(s) filtered — none attributed to target",
            )
            return ToolResult(
                tool=self.name,
                success=True,
                data=[summary],
                raw_output=f"{len(dorks)} dork(s), {len(hits)} raw hit(s), 0 attributed row(s)",
            )

        summary = scan_summary_entry(
            self.name,
            sites_checked=len(dorks),
            sites_found=len(results),
            note=f"{len(hits)} SERP hits · {len(discovery_meta.get('discovered_keywords', []))} keyword(s) discovered",
        )
        if discovery_meta:
            summary["google_search_discovery"] = discovery_meta
        return ToolResult(
            tool=self.name,
            success=True,
            data=[*results, summary],
            raw_output=f"{len(dorks)} dork(s), {len(hits)} SERP hit(s), {len(results)} intelligence row(s)",
        )
