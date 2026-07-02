"""CID audit log and password reset workflow tests."""

import os

import pytest

os.environ["ENTERPRISE_AUTH"] = "true"
os.environ["ENTERPRISE_DATABASE_URL"] = f"sqlite:///{os.path.abspath('data/test_audit.db')}"
os.environ["ADMIN_USERNAME"] = "auditadmin"
os.environ["ADMIN_PASSWORD"] = "Socmint@Admin2026!"
os.environ["DISABLE_RATE_LIMIT"] = "true"

from services.enterprise.audit import export_audit_csv, list_audit_logs, log_audit, verify_hash_chain
from services.enterprise.db import get_session, init_enterprise_db
from services.enterprise.password_reset_workflow import (
    admin_decide_password_reset,
    list_password_reset_requests,
    submit_password_reset_request,
    supervisor_decide_password_reset,
)
from services.enterprise.users import get_user_by_username, seed_admin_user, seed_demo_users


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    db_path = os.path.abspath("data/test_audit.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    init_enterprise_db()
    seed_admin_user()
    seed_demo_users()


def test_rich_audit_log_fields():
    log_id = log_audit(
        user_id="u1",
        username="inspector1",
        role="INSPECTOR",
        action="export_evidence",
        entity="case-123",
        entity_type="case",
        entity_id="case-123",
        case_id="case-123",
        investigation_id="inv-456",
        ip="10.0.0.5",
        device="Laptop",
        browser="Chrome",
        os="Linux",
        risk_level="high",
        result="success",
    )
    assert log_id
    data = list_audit_logs(action="export_evidence", limit=5)
    assert data["total"] >= 1
    entry = data["logs"][0]
    assert entry["audit_id"] == log_id
    assert entry["category"] == "export"
    assert entry["case_id"] == "case-123"
    assert entry["digital_signature"]
    assert entry["hash_chain"]


def test_audit_filters_and_export():
    log_audit(username="filteruser", action="login", entity="auth", result="failed")
    failed = list_audit_logs(result="failed", username="filteruser")
    assert any(l["action"] == "login" for l in failed["logs"])
    csv_data = export_audit_csv(username="filteruser")
    assert "audit_id" in csv_data
    assert "filteruser" in csv_data


def test_rebuild_audit_hash_chain():
    from services.enterprise.audit import ensure_audit_chain_integrity, log_audit, rebuild_audit_hash_chain, verify_hash_chain

    log_audit(username="legacy", action="login", entity="auth", result="success")
    log_audit(username="legacy", action="logout", entity="auth", result="success")
    # Simulate corrupted chain (pre-migration or partial write)
    session = get_session()
    from services.enterprise.db import _MODELS
    AuditLog = _MODELS["AuditLog"]
    row = session.query(AuditLog).first()
    row.hash_chain = "corrupted"
    session.commit()
    session.close()

    assert not verify_hash_chain(limit=10)["valid"]
    rebuilt = rebuild_audit_hash_chain()
    assert rebuilt >= 1
    assert ensure_audit_chain_integrity()["valid"] is True


def test_hash_chain_verification():
    for i in range(3):
        log_audit(username="chainuser", action="login", entity="auth", details={"n": i})
    result = verify_hash_chain(limit=50)
    assert result["valid"] is True
    assert result["checked"] >= 3


def test_password_reset_workflow():
    admin = get_user_by_username("auditadmin")
    target = get_user_by_username("inspector1")
    assert admin and target

    submit = submit_password_reset_request(employee_id="inspector1", reason="locked out", ip="127.0.0.1")
    assert submit["ok"]
    request_id = submit["request_id"]
    assert request_id

    pending = list_password_reset_requests(status="pending_supervisor")
    assert any(r["request_id"] == request_id for r in pending)

    supervisor_decide_password_reset(
        request_id=request_id,
        actor_id=admin.user_id,
        actor_username=admin.username,
        actor_role=admin.role,
        approve=True,
        notes="Identity verified in person",
    )
    pending_admin = list_password_reset_requests(status="pending_admin")
    assert any(r["request_id"] == request_id for r in pending_admin)

    result = admin_decide_password_reset(
        request_id=request_id,
        actor_id=admin.user_id,
        actor_username=admin.username,
        actor_role=admin.role,
        approve=True,
        notes="Admin approved",
    )
    assert result["status"] == "approved"
    assert result.get("temporary_password")


def test_audit_api_endpoints():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "auditadmin", "password": "Socmint@Admin2026!"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    listed = client.get("/api/enterprise/audit?limit=10", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert "logs" in body
    assert "categories" in body

    workflow = client.post(
        "/api/auth/password-reset/workflow",
        json={"employee_id": "inspector1", "reason": "test"},
    )
    assert workflow.status_code == 200
    assert workflow.json()["ok"]
