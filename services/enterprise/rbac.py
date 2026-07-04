"""RBAC — configuration-driven role permissions and case relationship matrix."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

RBAC_PATH = Path(__file__).resolve().parents[2] / "config" / "rbac.json"


@lru_cache(maxsize=1)
def load_rbac() -> dict:
    with open(RBAC_PATH, encoding="utf-8") as f:
        return json.load(f)


def clear_rbac_cache() -> None:
    load_rbac.cache_clear()


def all_permissions() -> list[str]:
    return list(load_rbac().get("permissions", []))


def all_roles() -> list[str]:
    return list(load_rbac().get("roles", {}).keys())


def organizational_ranks() -> list[dict]:
    return list(load_rbac().get("organizational_ranks", []))


def case_relationships() -> list[dict]:
    return list(load_rbac().get("case_relationships", []))


def assignment_templates() -> list[dict]:
    return list(load_rbac().get("assignment_templates", []))


def workflow_config() -> dict:
    return dict(load_rbac().get("workflow", {}))


def _rank_codes() -> set[str]:
    return {r["code"] for r in organizational_ranks()}


def legacy_role_map() -> dict[str, str]:
    return dict(load_rbac().get("legacy_role_map", {}))


def resolve_rank(role: str) -> str:
    """Map application role to organizational rank code (ranks are primary roles)."""
    if role in _rank_codes():
        return role
    legacy = legacy_role_map()
    if role in legacy:
        return legacy[role]
    return role


def normalize_role(role: str) -> str:
    """Resolve legacy role names to current rank-based role codes."""
    rank = resolve_rank(role)
    if rank in _rank_codes():
        return rank
    if role in load_rbac().get("roles", {}):
        return role
    return rank


def _normalize_permission(permission: str) -> str:
    aliases = load_rbac().get("permission_aliases", {})
    return aliases.get(permission, permission)


def role_permissions(role: str) -> set[str]:
    """Global role permissions — keyed by organizational rank or SUPER_ADMIN."""
    roles = load_rbac().get("roles", {})
    normalized = normalize_role(role)
    perms = set(roles.get(normalized, roles.get(role, [])))
    if "*" in perms:
        all_perms = set(load_rbac().get("permissions", []))
        all_perms.add("*")
        return all_perms
    expanded: set[str] = set()
    for perm in perms:
        expanded.add(perm)
        expanded.add(_normalize_permission(perm))
    return expanded


def has_permission(role: str, permission: str) -> bool:
    """Global permission check — unchanged for backward compatibility."""
    perm = _normalize_permission(permission)
    perms = role_permissions(role)
    if "*" in perms:
        return True
    return perm in perms or permission in perms


def matrix_permissions(rank: str, relationship: str) -> set[str]:
    """Permissions granted by organizational rank × case relationship."""
    matrix = load_rbac().get("permission_matrix", {})
    rank_row = matrix.get(rank) or matrix.get(resolve_rank(rank)) or {}
    rel_perms = rank_row.get(relationship, [])
    if "*" in rel_perms:
        return set(load_rbac().get("permissions", [])) | {"*"}
    expanded: set[str] = set()
    for perm in rel_perms:
        expanded.add(perm)
        expanded.add(_normalize_permission(perm))
    return expanded


def is_case_scoped_permission(permission: str) -> bool:
    perm = _normalize_permission(permission)
    scoped = set(load_rbac().get("case_scoped_permissions", []))
    return perm in scoped or permission in scoped


def has_case_permission(role: str, relationship: str, permission: str) -> bool:
    """Check permission for a specific case relationship."""
    perm = _normalize_permission(permission)
    rank = resolve_rank(role)
    perms = matrix_permissions(rank, relationship)
    if "*" in perms:
        return True
    if perm in perms or permission in perms:
        return True
    # Legacy aliases: start_investigation ↔ run_intelligence_collection
    if permission == "start_investigation" and "run_intelligence_collection" in perms:
        return True
    if permission == "export_evidence" and "generate_reports" in perms:
        return True
    return False


def resolve_case_permissions(role: str, relationships: list[str]) -> set[str]:
    """Union of permissions across all active case relationships for a user."""
    rank = resolve_rank(role)
    combined: set[str] = set()
    for rel in relationships:
        combined |= matrix_permissions(rank, rel)
    if "*" in combined:
        return set(load_rbac().get("permissions", [])) | {"*"}
    return combined


def can_on_case(
    role: str,
    permission: str,
    *,
    relationships: list[str] | None = None,
    is_creator: bool = False,
    is_legacy_assignee: bool = False,
) -> bool:
    """
    Case-aware authorization.
    - Global-only permissions use role_permissions.
    - Case-scoped permissions require a relationship (or legacy assignee/creator fallback).
    """
    perm = _normalize_permission(permission)
    if has_permission(role, permission) and not is_case_scoped_permission(permission):
        return True
    if "*" in role_permissions(role):
        return True

    rels = list(relationships or [])
    workflow = workflow_config()
    if is_creator and workflow.get("creator_default_relationship"):
        rels.append(workflow["creator_default_relationship"])
    if is_legacy_assignee and workflow.get("legacy_io_relationship"):
        rels.append(workflow["legacy_io_relationship"])

    if not rels:
        return False

    if has_case_permission(role, rels[0], permission):
        return True
    for rel in rels[1:]:
        if has_case_permission(role, rel, permission):
            return True
    return False


def effective_permissions_summary(role: str, relationships: list[str] | None = None) -> dict:
    """Human-readable permission summary for UI."""
    rank = resolve_rank(role)
    rels = relationships or []
    global_perms = sorted(role_permissions(role) - {"*"})
    case_perms = sorted(resolve_case_permissions(role, rels)) if rels else []
    return {
        "role": role,
        "rank": rank,
        "relationships": rels,
        "global_permissions": global_perms,
        "case_permissions": case_perms,
        "effective_on_case": sorted(set(global_perms) | set(case_perms)),
    }


def rbac_config_payload() -> dict:
    """Full RBAC configuration for admin UI and frontend."""
    cfg = load_rbac()
    return {
        "permissions": cfg.get("permissions", []),
        "roles": cfg.get("roles", {}),
        "organizational_ranks": cfg.get("organizational_ranks", []),
        "legacy_role_map": cfg.get("legacy_role_map", {}),
        "case_relationships": cfg.get("case_relationships", []),
        "permission_matrix": cfg.get("permission_matrix", {}),
        "workflow": cfg.get("workflow", {}),
        "assignment_templates": cfg.get("assignment_templates", []),
        "case_scoped_permissions": cfg.get("case_scoped_permissions", []),
        "global_only_permissions": cfg.get("global_only_permissions", []),
    }


def default_relationship_for_rank(rank: str, *, sensitive: bool = False) -> str:
    workflow = workflow_config()
    rank_code = normalize_role(rank)
    if sensitive and rank_code in workflow.get("sensitive_case_io_ranks", []):
        return "investigating_officer"
    if rank_code in workflow.get("default_io_eligible_ranks", []):
        return "investigating_officer"
    if rank_code in workflow.get("default_supervisor_ranks", []):
        return "supervisor"
    if rank_code in workflow.get("default_assistant_ranks", []):
        return "assistant_investigator"
    return "case_observer"
