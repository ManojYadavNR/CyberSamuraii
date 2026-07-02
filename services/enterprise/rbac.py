"""RBAC — configuration-driven role permissions."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

RBAC_PATH = Path(__file__).resolve().parents[2] / "config" / "rbac.json"


@lru_cache(maxsize=1)
def load_rbac() -> dict:
    with open(RBAC_PATH) as f:
        return json.load(f)


def role_permissions(role: str) -> set[str]:
    roles = load_rbac().get("roles", {})
    perms = set(roles.get(role, []))
    if "*" in perms:
        all_perms = set(load_rbac().get("permissions", []))
        all_perms.add("*")
        return all_perms
    return perms


def has_permission(role: str, permission: str) -> bool:
    perms = role_permissions(role)
    return "*" in perms or permission in perms


def all_roles() -> list[str]:
    return list(load_rbac().get("roles", {}).keys())
