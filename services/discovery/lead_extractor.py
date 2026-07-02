"""Entity-aware intelligence expansion — delegates to generic pivot processors."""

from __future__ import annotations

from schemas.common import FeatureResult
from schemas.discovery import DiscoveryLead
from schemas.fusion import Entity
from services.pivot.processors import process_entity, process_result


def extract_leads_from_entity(
    entity: Entity,
    *,
    source_query: str,
    depth: int,
    max_leads: int = 20,
) -> list[DiscoveryLead]:
    return process_entity(entity, source_query=source_query, depth=depth, max_leads=max_leads).generated_leads


def extract_leads_from_result(
    result: FeatureResult,
    *,
    source_query: str,
    depth: int,
    max_leads: int = 20,
) -> list[DiscoveryLead]:
    return process_result(result, source_query=source_query, depth=depth, max_leads=max_leads).generated_leads
