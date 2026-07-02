"""Pivot opportunity definitions per evidence type — not a hardcoded workflow."""

from __future__ import annotations

from schemas.pivot import PivotOpportunity

PIVOT_OPPORTUNITIES: dict[str, list[PivotOpportunity]] = {
    "account": [
        PivotOpportunity(field="email", lead_type="email", feature="email_intel", strategy="account_email_pivot", description="Investigate email for linked accounts", priority_boost=0.05),
        PivotOpportunity(field="website", lead_type="domain", feature="domain_intel", strategy="account_website_pivot", description="Enrich personal or org website"),
        PivotOpportunity(field="avatar_url", lead_type="image", feature="image_intel", strategy="account_image_pivot", description="Reverse image / similarity investigation"),
        PivotOpportunity(field="organization", lead_type="domain", feature="domain_intel", strategy="account_org_pivot", description="Investigate organization domain"),
        PivotOpportunity(field="handle", lead_type="username", feature="username_search", strategy="account_handle_pivot", description="Cross-platform username search", priority_boost=0.02),
    ],
    "email": [
        PivotOpportunity(field="email", lead_type="email", feature="email_intel", strategy="email_account_pivot", description="Account discovery and Gravatar lookup", priority_boost=0.08),
    ],
    "domain": [
        PivotOpportunity(field="domain", lead_type="domain", feature="domain_intel", strategy="domain_enrichment_pivot", description="Extract contacts, social links, org references"),
        PivotOpportunity(field="email", lead_type="email", feature="email_intel", strategy="domain_email_pivot", description="Investigate email found on website"),
    ],
    "image": [
        PivotOpportunity(field="image", lead_type="image", feature="image_intel", strategy="image_similarity_pivot", description="Image similarity and linked profile search"),
    ],
    "phone": [
        PivotOpportunity(field="phone", lead_type="phone", feature="infra_intel", strategy="phone_reference_pivot", description="Public references and linked profiles"),
    ],
    "name": [
        PivotOpportunity(field="name", lead_type="name", feature="", strategy="name_reference", description="Public mentions — evidence only, no auto-hop"),
    ],
    "organization": [
        PivotOpportunity(field="organization", lead_type="domain", feature="domain_intel", strategy="org_domain_pivot", description="Investigate organization web presence"),
    ],
}


def opportunities_for(entity_type: str) -> list[PivotOpportunity]:
    return list(PIVOT_OPPORTUNITIES.get(entity_type, []))
