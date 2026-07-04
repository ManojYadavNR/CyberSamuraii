"""IAM user provisioning — employee ID, badge, update."""

from __future__ import annotations

import pytest

from services.enterprise.db import get_session, init_enterprise_db
from services.enterprise.users import create_user, list_users, preview_next_user_ids, update_user


@pytest.fixture(scope="module", autouse=True)
def _db():
    assert init_enterprise_db()
    yield


def test_preview_next_user_ids_format():
    ids = preview_next_user_ids()
    assert ids["employee_id"].startswith("CID-")
    assert ids["badge_number"].startswith("BG-")


def test_create_user_assigns_employee_and_badge():
    import uuid

    suffix = uuid.uuid4().hex[:8]
    row = create_user(
        username=f"test_{suffix}",
        password="TestPass123!@#",
        name="Test User",
        email=f"test_{suffix}@example.com",
        role="HC",
        department="Headquarters",
        actor_username="admin",
    )
    assert row["employee_id"]
    assert row["badge_number"]
    assert row["employee_id"].startswith("CID-")


def test_update_user_role():
    users = list_users()
    target = next((u for u in users if u["role"] == "HC"), None)
    if not target:
        pytest.skip("No HC user to test")
    updated = update_user(
        user_id=target["user_id"],
        role="PC",
        actor_id="admin",
        actor_username="admin",
        actor_role="SUPER_ADMIN",
    )
    assert updated is not None
    assert updated["role"] == "PC"
    # restore
    update_user(
        user_id=target["user_id"],
        role="HC",
        actor_id="admin",
        actor_username="admin",
        actor_role="SUPER_ADMIN",
    )
