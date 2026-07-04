"""Password policy and role-based demo user tests."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ["ENTERPRISE_AUTH"] = "true"
os.environ["ENTERPRISE_DATABASE_URL"] = f"sqlite:///{os.path.abspath('data/test_enterprise.db')}"
os.environ["ADMIN_USERNAME"] = "testadmin"
os.environ["ADMIN_PASSWORD"] = "Socmint@Admin2026!"
os.environ["DISABLE_RATE_LIMIT"] = "true"
os.environ["SEED_DEMO_USERS"] = "true"
os.environ["DEMO_USER_PASSWORD"] = "Socmint@CID2026!Admin"

from services.enterprise.db import init_enterprise_db
from services.enterprise.password_policy import validate_password
from services.enterprise.rbac import clear_rbac_cache, has_permission
from services.enterprise.users import seed_admin_user, seed_demo_users


def rank_password(_rank: str = "") -> str:
    return "Socmint@CID2026!Admin"


STRONG = rank_password()
WEAK = "abc123"


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    clear_rbac_cache()
    db_path = os.path.abspath("data/test_enterprise.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    init_enterprise_db()
    seed_admin_user()
    seed_demo_users()


def test_password_policy_rejects_weak():
    ok, errors = validate_password(WEAK, username="psi")
    assert not ok
    assert any("12 characters" in e for e in errors)


def test_password_policy_rejects_username_in_password():
    ok, errors = validate_password("Psi@VeryLongPass1", username="psi")
    assert not ok
    assert any("username" in e.lower() for e in errors)


def test_password_policy_accepts_strong():
    ok, errors = validate_password(STRONG, username="psi")
    assert ok
    assert errors == []


def test_wrong_password_rejected():
    from main import app

    client = TestClient(app)
    resp = client.post("/api/auth/login", json={"username": "psi", "password": "wrong-password"})
    assert resp.status_code == 401


def test_all_demo_roles_can_login():
    from main import app

    client = TestClient(app)
    demo = client.get("/api/auth/demo-accounts").json()
    for account in demo["accounts"]:
        resp = client.post(
            "/api/auth/login",
            json={"username": account["username"], "password": rank_password()},
        )
        assert resp.status_code == 200, f"Login failed for {account['username']}: {resp.text}"
        body = resp.json()
        assert body["user"]["role"] == account["role"]


def test_role_permissions_enforced_on_cases():
    from main import app

    client = TestClient(app)

    viewer_login = client.post("/api/auth/login", json={"username": "pc", "password": rank_password()})
    viewer_token = viewer_login.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    denied = client.post(
        "/api/enterprise/cases",
        headers=viewer_headers,
        json={"title": "Should fail", "description": "", "priority": "LOW"},
    )
    assert denied.status_code == 403

    psi_login = client.post("/api/auth/login", json={"username": "psi", "password": rank_password()})
    psi_token = psi_login.json()["access_token"]
    psi_headers = {"Authorization": f"Bearer {psi_token}"}

    allowed = client.post(
        "/api/enterprise/cases",
        headers=psi_headers,
        json={"title": "PSI case", "description": "", "priority": "MEDIUM"},
    )
    assert allowed.status_code == 200


def test_create_user_rejects_weak_password():
    from main import app

    client = TestClient(app)
    admin = client.post("/api/auth/login", json={"username": "testadmin", "password": "Socmint@Admin2026!"})
    headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}

    bad = client.post(
        "/api/enterprise/users",
        headers=headers,
        json={
            "username": "newweak",
            "password": WEAK,
            "name": "Weak User",
            "email": "weak@socmint.local",
            "role": "PSI",
        },
    )
    assert bad.status_code == 400
    assert "12 characters" in bad.json()["detail"] or "uppercase" in bad.json()["detail"]


def test_create_user_accepts_strong_password():
    import uuid
    from main import app

    client = TestClient(app)
    admin = client.post("/api/auth/login", json={"username": "testadmin", "password": "Socmint@Admin2026!"})
    headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    username = f"stronguser_{uuid.uuid4().hex[:8]}"

    good = client.post(
        "/api/enterprise/users",
        headers=headers,
        json={
            "username": username,
            "password": "MyStr0ng!Pass99",
            "name": "Strong User",
            "email": f"{username}@socmint.local",
            "role": "PSI",
        },
    )
    assert good.status_code == 200
    assert good.json()["username"] == username


def test_viewer_cannot_start_investigation():
    assert not has_permission("PC", "start_investigation")
    assert has_permission("PSI", "start_investigation")
