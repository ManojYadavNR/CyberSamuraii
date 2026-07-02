"""Audit log taxonomy — categories, risk levels, suspicious heuristics."""

from __future__ import annotations

AUDIT_CATEGORIES = (
    "authentication",
    "investigation",
    "evidence",
    "report",
    "export",
    "user_management",
    "permission",
    "administration",
    "copilot",
    "external_api",
    "system",
)

ACTION_CATEGORY: dict[str, str] = {
    "login": "authentication",
    "logout": "authentication",
    "token_refresh": "authentication",
    "password_change": "authentication",
    "password_reset_request": "authentication",
    "password_reset_confirm": "authentication",
    "password_reset_workflow_request": "authentication",
    "password_reset_supervisor_approve": "authentication",
    "password_reset_supervisor_deny": "authentication",
    "password_reset_admin_approve": "authentication",
    "password_reset_admin_deny": "authentication",
    "password_reset_complete": "authentication",
    "mfa_enroll": "authentication",
    "mfa_verify": "authentication",
    "start_investigation": "investigation",
    "cancel_investigation": "investigation",
    "link_investigation": "investigation",
    "review_cluster": "investigation",
    "evidence_view": "evidence",
    "record_evidence": "evidence",
    "archive_evidence": "evidence",
    "export_evidence": "export",
    "export_case_report": "report",
    "export_audit_report": "export",
    "create_user": "user_management",
    "update_user": "user_management",
    "deactivate_user": "user_management",
    "create_case": "administration",
    "edit_case": "administration",
    "assign_case": "administration",
    "transfer_case": "administration",
    "submit_review": "administration",
    "approval_approved": "administration",
    "approval_rejected": "administration",
    "copilot_query": "copilot",
    "external_api_call": "external_api",
}

ACTION_RISK: dict[str, str] = {
    "login": "low",
    "logout": "low",
    "password_change": "medium",
    "password_reset_workflow_request": "medium",
    "password_reset_admin_approve": "high",
    "password_reset_admin_deny": "medium",
    "start_investigation": "medium",
    "cancel_investigation": "medium",
    "export_evidence": "high",
    "export_case_report": "high",
    "export_audit_report": "critical",
    "create_user": "high",
    "update_user": "high",
    "deactivate_user": "critical",
    "record_evidence": "medium",
    "archive_evidence": "high",
    "copilot_query": "medium",
}

HIGH_RISK_ACTIONS = frozenset({"export_evidence", "export_case_report", "export_audit_report", "deactivate_user"})


def category_for_action(action: str) -> str:
    if action.startswith("approval_"):
        return "administration"
    if action.startswith("password_reset"):
        return "authentication"
    return ACTION_CATEGORY.get(action, "system")


def risk_for_action(action: str, *, result: str = "success") -> str:
    if result in ("failed", "denied", "locked"):
        return "medium" if action == "login" else "high"
    return ACTION_RISK.get(action, "low")


def is_suspicious(entry: dict) -> bool:
    action = str(entry.get("action") or "")
    result = str(entry.get("result") or "")
    risk = str(entry.get("risk_level") or "")
    if result in ("failed", "denied", "locked"):
        return True
    if risk in ("high", "critical"):
        return True
    if action in HIGH_RISK_ACTIONS:
        return True
    ts = str(entry.get("timestamp") or "")
    if ts and action.startswith("export"):
        try:
            hour = int(ts[11:13])
            if hour < 6 or hour >= 22:
                return True
        except ValueError:
            pass
    return False
