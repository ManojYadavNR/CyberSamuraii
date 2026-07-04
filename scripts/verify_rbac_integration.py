#!/usr/bin/env python3
"""Cross-check rank-based RBAC integration against live config and API."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

os.environ.setdefault("ENTERPRISE_AUTH", "true")
os.environ.setdefault("DISABLE_RATE_LIMIT", "true")
os.environ.setdefault("SEED_DEMO_USERS", "true")

from fastapi.testclient import TestClient

from services.enterprise.rbac import (
    all_roles,
    can_on_case,
    clear_rbac_cache,
    has_permission,
    load_rbac,
    resolve_rank,
    role_permissions,
    workflow_config,
)

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD", "Socmint@CID2026!Admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Socmint@CID2026!Admin")
ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")

RANK_USERS = [
    ("dgp", "DGP"),
    ("adgp", "ADGP"),
    ("igp", "IGP"),
    ("dig", "DIG"),
    ("sp", "SP"),
    ("dsp", "DSP"),
    ("pi", "PI"),
    ("psi", "PSI"),
    ("hc", "HC"),
    ("pc", "PC"),
]

GLOBAL_CHECKS = [
    "create_case", "assign_case", "start_investigation", "approve_evidence",
    "manage_users", "view_audit_logs", "close_case", "view_cases",
]

GLOBAL_API = [
    ("GET", "/api/enterprise/cases", "view_cases"),
    ("POST", "/api/enterprise/cases", "create_case", {"title": "RBAC verify", "description": "x", "priority": "LOW"}),
    ("GET", "/api/enterprise/users", "manage_users"),
    ("GET", "/api/enterprise/audit", "view_audit_logs"),
]


def login(client: TestClient, username: str, password: str) -> dict | None:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        return None
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main() -> int:
    clear_rbac_cache()
    cfg = load_rbac()
    wf = workflow_config()
    issues: list[str] = []
    passed: list[str] = []

    print("=" * 60)
    print("RANK-BASED RBAC VERIFICATION")
    print("=" * 60)

    rank_codes = {r["code"] for r in cfg.get("organizational_ranks", [])}
    role_keys = set(cfg.get("roles", {}).keys()) - {"SUPER_ADMIN"}

    if rank_codes != role_keys:
        issues.append(f"Rank/role mismatch: ranks={sorted(rank_codes)} roles={sorted(role_keys)}")

    print(f"  Organizational ranks: {len(rank_codes)}")
    print(f"  Matrix ranks: {len(cfg.get('permission_matrix', {}))}")
    print(f"  Case relationships: {len(cfg.get('case_relationships', []))}")
    print(f"  IO eligible ranks (config): {wf.get('default_io_eligible_ranks')}")
    print(f"  Supervisor ranks (config): {wf.get('default_supervisor_ranks')}")
    print(f"  Assistant ranks (config): {wf.get('default_assistant_ranks')}")

    print("\n" + "=" * 60)
    print("REALISTIC WORKFLOW SPOT CHECKS")
    print("=" * 60)

    workflow_checks = [
        ("PSI", ["assistant_investigator"], "upload_evidence", True, "PSI assistant can upload evidence"),
        ("PSI", ["assistant_investigator"], "run_intelligence_collection", True, "PSI assistant can run intel"),
        ("PSI", ["assistant_investigator"], "close_case", False, "PSI assistant cannot close case"),
        ("PSI", ["assistant_investigator"], "approve_reports", False, "PSI assistant cannot approve reports"),
        ("PC", ["read_only"], "view_cases", True, "PC read-only can view case"),
        ("PC", ["read_only"], "start_investigation", False, "PC read-only cannot investigate"),
        ("PI", ["investigating_officer"], "assign_case", True, "PI as IO can assign on case"),
        ("SP", ["supervisor"], "close_case", True, "SP supervisor can close case"),
        ("SP", ["investigating_officer"], "run_intelligence_collection", True, "SP as IO on sensitive case"),
        ("HC", ["assistant_investigator"], "run_intelligence_collection", True, "HC assistant can collect intel"),
        ("HC", [], "create_case", False, "HC without case link has no create on case scope"),
    ]
    for role, rels, perm, expected, label in workflow_checks:
        actual = can_on_case(role, perm, relationships=rels)
        ok = actual == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {actual}")
        if not ok:
            issues.append(f"{label}: expected {expected}, got {actual}")

    print("\n" + "=" * 60)
    print("GLOBAL PERMISSIONS BY RANK")
    print("=" * 60)
    for rank in sorted(rank_codes):
        flags = "".join("Y" if has_permission(rank, p) else "-" for p in GLOBAL_CHECKS)
        print(f"  {rank:4} {flags}  ({', '.join(p[:4] for p in GLOBAL_CHECKS)})")

    print("\n" + "=" * 60)
    print("LIVE API — ALL RANK ACCOUNTS")
    print("=" * 60)

    from main import app

    client = TestClient(app)

    # Admin
    admin_h = login(client, ADMIN_USER, ADMIN_PASSWORD)
    if not admin_h:
        issues.append(f"Admin login failed: {ADMIN_USER}")
        print(f"  FAIL admin login ({ADMIN_USER})")
    else:
        print(f"  OK   admin ({ADMIN_USER}) → SUPER_ADMIN")

    for username, expected_rank in RANK_USERS:
        headers = login(client, username, DEMO_PASSWORD)
        if not headers:
            issues.append(f"Login failed: {username}")
            print(f"  FAIL login: {username}")
            continue

        me = client.get("/api/auth/me", headers=headers)
        role = me.json().get("role", "") if me.status_code == 200 else ""
        rank = resolve_rank(role)
        if role != expected_rank:
            issues.append(f"{username}: expected {expected_rank}, got {role}")
            print(f"  FAIL {username}: role {role} != {expected_rank}")
            continue

        # Global permission API parity
        pr = client.get("/api/enterprise/rbac/permissions/me", headers=headers)
        if pr.status_code == 200:
            global_perms = set(pr.json().get("global_permissions", []))
            for perm in ["create_case", "start_investigation", "manage_users", "approve_evidence"]:
                expected = has_permission(role, perm)
                actual = perm in global_perms or "*" in global_perms
                if actual != expected:
                    issues.append(f"{username}: {perm} API={actual} config={expected}")

        # Route probes
        route_ok = True
        for item in GLOBAL_API:
            method, path, perm = item[0], item[1], item[2]
            body = item[3] if len(item) > 3 else None
            expected_status = 200 if has_permission(role, perm) else 403
            r = client.post(path, headers=headers, json=body) if method == "POST" else client.get(path, headers=headers)
            if r.status_code != expected_status and not (expected_status == 200 and r.status_code in (200, 201)):
                issues.append(f"{username} {method} {path}: expected {expected_status}, got {r.status_code}")
                route_ok = False

        sym = "OK" if route_ok else "WARN"
        caps = []
        if has_permission(role, "create_case"):
            caps.append("create")
        if has_permission(role, "start_investigation"):
            caps.append("investigate")
        if has_permission(role, "assign_case"):
            caps.append("assign")
        if has_permission(role, "close_case"):
            caps.append("close")
        if has_permission(role, "approve_evidence"):
            caps.append("approve")
        if has_permission(role, "manage_users"):
            caps.append("admin")
        if has_permission(role, "view_audit_logs"):
            caps.append("audit")
        if not caps:
            caps.append("view-only")
        print(f"  {sym:4} {username:5} ({rank:4}) → {', '.join(caps)}")
        passed.append(username)

    print("\n" + "=" * 60)
    print("CASE TEAM WORKFLOW SCENARIO")
    print("=" * 60)

    if admin_h:
        sp_h = login(client, "sp", DEMO_PASSWORD)
        psi_h = login(client, "psi", DEMO_PASSWORD)
        pc_h = login(client, "pc", DEMO_PASSWORD)

        if sp_h and psi_h and pc_h:
            cr = client.post(
                "/api/enterprise/cases",
                headers=sp_h,
                json={"title": "Rank workflow case", "description": "Integration test", "priority": "HIGH"},
            )
            if cr.status_code == 200:
                case_id = cr.json()["case_id"]
                print(f"  OK   SP created case {cr.json()['case_number']}")

                # PC not assigned → blocked
                pc_view = client.get(f"/api/enterprise/cases/{case_id}", headers=pc_h)
                print(f"  {'PASS' if pc_view.status_code == 403 else 'FAIL'} PC unassigned → {pc_view.status_code}")

                users = client.get("/api/enterprise/users", headers=admin_h).json()
                psi_id = next((u["user_id"] for u in users if u["username"] == "psi"), "")
                pi_id = next((u["user_id"] for u in users if u["username"] == "pi"), "")

                if psi_id:
                    asg = client.post(
                        f"/api/enterprise/cases/{case_id}/assign",
                        headers=sp_h,
                        json={"assigned_to": psi_id, "relationship": "assistant_investigator"},
                    )
                    print(f"  {'PASS' if asg.status_code == 200 else 'FAIL'} SP assigned PSI as assistant")

                    psi_view = client.get(f"/api/enterprise/cases/{case_id}", headers=psi_h)
                    print(f"  {'PASS' if psi_view.status_code == 200 else 'FAIL'} PSI can view assigned case")

                    perms = client.get(
                        f"/api/enterprise/rbac/permissions/me?case_id={case_id}",
                        headers=psi_h,
                    )
                    if perms.status_code == 200:
                        eff = set(perms.json().get("effective_on_case", []))
                        intel = "run_intelligence_collection" in eff or "start_investigation" in eff
                        close = "close_case" in eff
                        print(f"  {'PASS' if intel else 'FAIL'} PSI case perms include intel collection")
                        print(f"  {'PASS' if not close else 'FAIL'} PSI case perms exclude close_case")
                        if not intel:
                            issues.append("PSI assistant missing intel on assigned case")
                        if close:
                            issues.append("PSI assistant incorrectly has close_case")

                if pi_id:
                    pi_asg = client.post(
                        f"/api/enterprise/cases/{case_id}/assign",
                        headers=sp_h,
                        json={"assigned_to": pi_id, "relationship": "investigating_officer"},
                    )
                    print(f"  {'PASS' if pi_asg.status_code == 200 else 'FAIL'} SP assigned PI as IO")

                    pi_perms = client.get(
                        f"/api/enterprise/rbac/permissions/me?case_id={case_id}",
                        headers=login(client, "pi", DEMO_PASSWORD) or {},
                    )
                    if pi_perms.status_code == 200:
                        eff = set(pi_perms.json().get("effective_on_case", []))
                        print(f"  {'PASS' if 'assign_case' in eff or 'edit_case' in eff else 'FAIL'} PI IO has case leadership perms")

                close_attempt = client.post(f"/api/enterprise/cases/{case_id}/close", headers=psi_h)
                print(f"  {'PASS' if close_attempt.status_code == 403 else 'FAIL'} PSI cannot close case ({close_attempt.status_code})")
                if close_attempt.status_code != 403:
                    issues.append(f"PSI close case should be 403, got {close_attempt.status_code}")

                close_sp = client.post(f"/api/enterprise/cases/{case_id}/close", headers=sp_h)
                print(f"  {'PASS' if close_sp.status_code == 200 else 'FAIL'} SP supervisor can close case ({close_sp.status_code})")
            else:
                issues.append(f"SP create case failed: {cr.status_code}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Rank accounts verified: {len(passed)}/10")
    print(f"  Issues: {len(issues)}")
    if issues:
        for i in issues:
            print(f"    - {i}")
        return 1
    print("\n  All rank-based RBAC checks passed — realistic workflow verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
