"""Authentication API — login, logout, refresh, enterprise password reset."""

from fastapi import APIRouter, Depends, HTTPException, Request

from api.deps import client_ip, get_current_user
from schemas.enterprise import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetWorkflowDecision,
    PasswordResetWorkflowRequest,
    RefreshRequest,
    TokenResponse,
    UserPublic,
)
from services.enterprise.audit import log_audit
from services.enterprise.db import enterprise_enabled
from services.enterprise.password_reset_workflow import (
    admin_decide_password_reset,
    list_password_reset_requests,
    submit_password_reset_request,
    supervisor_decide_password_reset,
    ADMIN_ROLES,
    SUPERVISOR_ROLES,
)
from services.enterprise.security import check_rate_limit
from services.enterprise.users import (
    confirm_password_reset,
    login_user,
    logout_user,
    refresh_access_token,
    request_password_reset,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    ip = client_ip(request)
    if not check_rate_limit(ip, "/api/auth/login"):
        raise HTTPException(status_code=429, detail="Too many login attempts — try again later")
    result = login_user(
        username=body.username,
        password=body.password,
        ip=ip,
        user_agent=request.headers.get("user-agent", ""),
        request=request,
    )
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials or account locked")
    return TokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        expires_in=result["expires_in"],
        user=UserPublic(**result["user"]),
    )


@router.post("/logout")
async def logout(body: RefreshRequest, request: Request):
    """Revoke refresh token — does not require a valid access token."""
    ip = client_ip(request)
    logout_user(refresh_token=body.refresh_token, ip=ip)
    return {"ok": True}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request):
    ip = client_ip(request)
    result = refresh_access_token(body.refresh_token, ip=ip)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return TokenResponse(
        access_token=result["access_token"],
        refresh_token=body.refresh_token,
        expires_in=result["expires_in"],
        user=UserPublic(**result["user"]),
    )


@router.post("/password-reset/request")
async def password_reset_request(body: PasswordResetRequest, request: Request):
    """Legacy email-based reset (dev). Prefer /password-reset/workflow for CID operations."""
    token = request_password_reset(body.email)
    if not token:
        return {"ok": True, "message": "If the email exists, a reset link was generated"}
    return {"ok": True, "reset_token": token, "message": "Dev mode: reset token returned in response"}


@router.post("/password-reset/workflow")
async def password_reset_workflow(body: PasswordResetWorkflowRequest, request: Request):
    """CID workflow — employee ID verified, supervisor + admin approval required."""
    ip = client_ip(request)
    if not check_rate_limit(ip, "/api/auth/password-reset/workflow"):
        raise HTTPException(status_code=429, detail="Too many reset requests — try again later")
    return submit_password_reset_request(
        employee_id=body.employee_id,
        reason=body.reason,
        ip=ip,
        request=request,
    )


@router.get("/password-reset/requests")
async def password_reset_requests(status: str = "", user=Depends(get_current_user)):
    if user.role not in SUPERVISOR_ROLES | ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Supervisor or administrator role required")
    return {"requests": list_password_reset_requests(status=status)}


@router.post("/password-reset/requests/{request_id}/supervisor")
async def password_reset_supervisor(request_id: str, body: PasswordResetWorkflowDecision, request: Request, user=Depends(get_current_user)):
    if user.role not in SUPERVISOR_ROLES:
        raise HTTPException(status_code=403, detail="Supervisor role required")
    try:
        row = supervisor_decide_password_reset(
            request_id=request_id,
            actor_id=user.user_id,
            actor_username=user.username,
            actor_role=user.role,
            approve=body.approve,
            notes=body.notes,
            ip=client_ip(request),
            request=request,
        )
        return row
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/password-reset/requests/{request_id}/admin")
async def password_reset_admin(request_id: str, body: PasswordResetWorkflowDecision, request: Request, user=Depends(get_current_user)):
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Administrator role required")
    try:
        row = admin_decide_password_reset(
            request_id=request_id,
            actor_id=user.user_id,
            actor_username=user.username,
            actor_role=user.role,
            approve=body.approve,
            notes=body.notes,
            ip=client_ip(request),
            request=request,
        )
        return row
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/password-reset/confirm")
async def password_reset_confirm(body: PasswordResetConfirm):
    try:
        if not confirm_password_reset(body.token, body.new_password):
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
async def me(user=Depends(get_current_user)):
    from services.enterprise.users import get_user_by_id, _user_public

    row = get_user_by_id(user.user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPublic(**_user_public(row))


@router.get("/demo-accounts")
async def demo_accounts():
    """Dev helper — lists seeded role accounts (password omitted in production)."""
    import json
    import os
    from pathlib import Path

    if os.getenv("SEED_DEMO_USERS", "true").lower() not in {"1", "true", "yes"}:
        return {"accounts": [], "note": "Demo seeding disabled"}
    path = Path(__file__).resolve().parents[1] / "config" / "demo_users.json"
    if not path.exists():
        return {"accounts": []}
    with open(path) as f:
        cfg = json.load(f)
    password = os.getenv("DEMO_USER_PASSWORD_TEMPLATE", cfg.get("password_template", "Socmint@CID2026!{rank}"))
    show_password = os.getenv("SHOW_DEMO_PASSWORDS", "true").lower() in {"1", "true", "yes"}
    accounts = [
        {
            "username": u["username"],
            "role": u["role"],
            "name": u.get("name", ""),
            "password_hint": password.replace("{rank}", u.get("role", "")),
        }
        for u in cfg.get("users", [])
    ]
    out: dict = {
        "accounts": accounts,
        "admin_username": os.getenv("ADMIN_USERNAME", "admin"),
        "password_template": password,
    }
    if show_password:
        out["admin_password_hint"] = "Set ADMIN_PASSWORD in .env (default Socmint@CID2026!Admin)"
    return out


@router.get("/status")
async def auth_status():
    from services.enterprise.password_policy import MIN_LENGTH

    return {
        "enterprise_auth": enterprise_enabled(),
        "password_policy": {
            "min_length": MIN_LENGTH,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_digit": True,
            "require_special": True,
        },
    }
