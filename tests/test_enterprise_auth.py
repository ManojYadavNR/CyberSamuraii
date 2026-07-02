"""Enterprise auth and RBAC tests."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ["ENTERPRISE_AUTH"] = "true"
os.environ["ENTERPRISE_DATABASE_URL"] = f"sqlite:///{os.path.abspath('data/test_enterprise.db')}"
os.environ["ADMIN_USERNAME"] = "testadmin"
os.environ["ADMIN_PASSWORD"] = "Socmint@Admin2026!"
os.environ["DISABLE_RATE_LIMIT"] = "true"

from services.enterprise.db import init_enterprise_db
from services.enterprise.rbac import has_permission
from services.enterprise.users import seed_admin_user, seed_demo_users


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_enterprise_db()
    seed_admin_user()
    seed_demo_users()


def test_super_admin_has_all_permissions():
    assert has_permission("SUPER_ADMIN", "start_investigation")
    assert has_permission("SUPER_ADMIN", "manage_users")
    assert has_permission("SUPER_ADMIN", "delete_case")


def test_viewer_cannot_start_investigation():
    assert not has_permission("VIEWER", "start_investigation")
    assert has_permission("VIEWER", "view_cases")


def test_login_and_protected_route():
    from main import app

    client = TestClient(app)
    bad = client.post("/api/auth/login", json={"username": "testadmin", "password": "wrong"})
    assert bad.status_code == 401

    good = client.post("/api/auth/login", json={"username": "testadmin", "password": "Socmint@Admin2026!"})
    assert good.status_code == 200
    token = good.json()["access_token"]

  # Investigation engines unchanged — dashboard requires auth
    unauth = client.get("/api/dashboard/investigations/fake-id")
    assert unauth.status_code == 401

    authed = client.get(
        "/api/dashboard/investigations/fake-id",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert authed.status_code == 404  # auth passed, not found


def test_admin_can_create_case():
    from main import app

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "testadmin", "password": "Socmint@Admin2026!"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    case = client.post(
        "/api/enterprise/cases",
        headers=headers,
        json={"title": "Test Case", "description": "Unit test", "priority": "HIGH"},
    )
    assert case.status_code == 200
    body = case.json()
    assert body["title"] == "Test Case"
    assert body["case_number"].startswith("CASE-")


def test_health_unauthenticated():
    from main import app

    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
