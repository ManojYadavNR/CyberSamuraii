"""RBAC matrix and case assignment authorization tests."""

import os

import pytest

os.environ["ENTERPRISE_AUTH"] = "true"
os.environ["ENTERPRISE_DATABASE_URL"] = f"sqlite:///{os.path.abspath('data/test_rbac_matrix.db')}"
os.environ["ADMIN_USERNAME"] = "testadmin"
os.environ["ADMIN_PASSWORD"] = "Socmint@Admin2026!"
os.environ["DISABLE_RATE_LIMIT"] = "true"

from services.enterprise.rbac import (
    can_on_case,
    clear_rbac_cache,
    has_case_permission,
    has_permission,
    resolve_rank,
)
from services.enterprise.db import init_enterprise_db
from services.enterprise.case_assignments import add_case_assignment, migrate_legacy_assignments
from services.enterprise.cases import create_case
from services.enterprise.users import seed_admin_user


@pytest.fixture(autouse=True)
def setup_db():
    clear_rbac_cache()
    init_enterprise_db()
    seed_admin_user()
    migrate_legacy_assignments()


def test_psi_assistant_can_upload_not_close():
    assert resolve_rank("PSI") == "PSI"
    assert has_case_permission("PSI", "assistant_investigator", "upload_evidence")
    assert has_case_permission("PSI", "assistant_investigator", "run_intelligence_collection")
    assert not has_case_permission("PSI", "assistant_investigator", "close_case")
    assert not has_case_permission("PSI", "assistant_investigator", "approve_reports")


def test_legacy_role_maps_to_rank():
    assert resolve_rank("SUB_INSPECTOR") == "PSI"
    assert has_permission("SUB_INSPECTOR", "create_case")
    assert has_permission("ANALYST", "start_investigation")


def test_global_permission_by_rank():
    assert not has_permission("PC", "create_case")
    assert has_permission("PSI", "create_case")


def test_can_on_case_with_relationship():
    assert can_on_case("PSI", "upload_evidence", relationships=["assistant_investigator"])
    assert not can_on_case("PSI", "close_case", relationships=["assistant_investigator"])


def test_case_assignment_and_access():
    from services.enterprise.users import get_user_by_username

    admin = get_user_by_username(os.environ.get("ADMIN_USERNAME", "testadmin"))
    assert admin is not None
    case = create_case(
        title="RBAC matrix case",
        description="",
        priority="LOW",
        created_by=admin.user_id,
    )
    assert case is not None
    add_case_assignment(
        case["case_id"],
        user_id=admin.user_id,
        relationship="supervisor",
        assigned_by=admin.user_id,
    )
    assert can_on_case(
        admin.role,
        "assign_case",
        relationships=["supervisor"],
        is_creator=True,
    )
