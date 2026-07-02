"""Enterprise governance schemas — auth, cases, audit."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RoleName = Literal[
    "SUPER_ADMIN", "CID_DIRECTOR", "SP", "DSP", "INSPECTOR", "SUB_INSPECTOR",
    "ANALYST", "INTELLIGENCE_OFFICER", "FORENSICS_OFFICER", "VIEWER", "AUDITOR",
]

CaseStatus = Literal["OPEN", "ACTIVE", "UNDER_REVIEW", "ESCALATED", "CLOSED", "ARCHIVED"]
CasePriority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class UserPublic(BaseModel):
    user_id: str
    username: str
    name: str
    email: str
    role: str
    department: str = ""
    designation: str = ""
    employee_id: str = ""
    badge_number: str = ""
    active: bool = True
    last_login: str | None = None
    must_change_password: bool = False
    mfa_enabled: bool = False
    avatar_url: str | None = None


class UserIdsPreview(BaseModel):
    employee_id: str
    badge_number: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetWorkflowRequest(BaseModel):
    employee_id: str
    reason: str = ""


class PasswordResetWorkflowDecision(BaseModel):
    approve: bool
    notes: str = ""


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    email: str
    role: RoleName
    department: str = ""
    designation: str = ""
    employee_id: str = ""
    badge_number: str = ""


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: RoleName | None = None
    department: str | None = None
    designation: str | None = None
    active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class CaseCreate(BaseModel):
    title: str
    description: str = ""
    priority: CasePriority = "MEDIUM"


class CaseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: CasePriority | None = None
    status: CaseStatus | None = None
    assigned_to: str | None = None


class CaseOut(BaseModel):
    case_id: str
    case_number: str
    title: str
    description: str = ""
    priority: str
    status: str
    assigned_to: str | None = None
    created_by: str
    created_at: str
    updated_at: str | None = None


class AuditLogOut(BaseModel):
    audit_id: str = ""
    timestamp: str
    user: str
    user_id: str = ""
    username: str = ""
    role: str = ""
    session_id: str = ""
    category: str = "system"
    action: str
    entity: str
    entity_type: str = ""
    entity_id: str = ""
    case_id: str = ""
    investigation_id: str = ""
    ip: str = ""
    location_approx: str = ""
    device: str = ""
    browser: str = ""
    os: str = ""
    result: str = "success"
    failure_reason: str = ""
    risk_level: str = "low"
    approval_required: bool = False
    supervisor_id: str = ""
    previous_value: str = ""
    new_value: str = ""
    digital_signature: str = ""
    hash_chain: str = ""
    suspicious: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class AuditLogListResponse(BaseModel):
    logs: list[AuditLogOut]
    total: int
    categories: list[str] = Field(default_factory=list)


class WorkspaceNote(BaseModel):
    note_id: str
    case_id: str
    author_id: str
    author_name: str
    content: str
    created_at: str
    pinned: bool = False


class NoteCreate(BaseModel):
    content: str
    pinned: bool = False


class CommentCreate(BaseModel):
    content: str


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    assigned_to: str | None = None


class BookmarkCreate(BaseModel):
    entity_id: str
    entity_label: str = ""
    entity_type: str = ""


class PinCreate(BaseModel):
    finding_key: str
    finding_label: str = ""
    finding_data: dict[str, Any] = Field(default_factory=dict)


class AssignCaseRequest(BaseModel):
    assigned_to: str


class ApprovalSubmit(BaseModel):
    investigation_id: str
    cluster_id: str
    notes: str = ""


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected", "clarification"]
    notes: str = ""


class EvidenceMarkRequest(BaseModel):
    important: bool = True


class ReportRequest(BaseModel):
    format: Literal["json", "html", "docx"] = "json"
