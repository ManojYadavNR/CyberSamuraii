"""FastAPI dependencies for enterprise auth."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.enterprise.auth_tokens import decode_access_token
from services.enterprise.db import enterprise_enabled
from services.enterprise.rbac import can_on_case, has_permission, is_case_scoped_permission, role_permissions

_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, user_id: str, username: str, role: str, name: str = ""):
        self.user_id = user_id
        self.username = username
        self.role = role
        self.name = name

    def can(self, permission: str, *, case_id: str | None = None) -> bool:
        if "*" in role_permissions(self.role):
            return True
        if case_id:
            return self.can_on_case(case_id, permission)
        return has_permission(self.role, permission)

    def can_on_case(self, case_id: str, permission: str) -> bool:
        from services.enterprise.case_assignments import get_user_case_relationships
        from services.enterprise.cases import get_case

        if "*" in role_permissions(self.role):
            return True

        case = get_case(case_id)
        if not case:
            return False

        relationships = get_user_case_relationships(self.user_id, case_id)
        is_creator = case.get("created_by") == self.user_id
        is_legacy_assignee = case.get("assigned_to") == self.user_id

        if can_on_case(
            self.role,
            permission,
            relationships=relationships,
            is_creator=is_creator,
            is_legacy_assignee=is_legacy_assignee,
        ):
            return True

        if not is_case_scoped_permission(permission):
            return has_permission(self.role, permission)
        return False


async def get_optional_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser | None:
    if not enterprise_enabled():
        return None
    token = None
    if creds and creds.credentials:
        token = creds.credentials
    elif request.query_params.get("token"):
        token = request.query_params.get("token")
    if not token:
        return None
    data = decode_access_token(token)
    if not data:
        return None
    return CurrentUser(
        user_id=data.get("sub", ""),
        username=data.get("username", ""),
        role=data.get("role", "PC"),
        name=data.get("name", ""),
    )


async def get_current_user(
    user: Annotated[CurrentUser | None, Depends(get_optional_user)],
) -> CurrentUser:
    if not enterprise_enabled():
        return CurrentUser("anonymous", "anonymous", "SUPER_ADMIN", "Anonymous")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_permission(permission: str):
    async def _check(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not user.can(permission):
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return user

    return _check


def require_case_permission(permission: str, case_id_param: str = "case_id"):
    async def _check(
        request: Request,
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        case_id = request.path_params.get(case_id_param, "")
        if not case_id:
            if not user.can(permission):
                raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
            return user
        from services.enterprise.case_assignments import user_has_case_access

        if not user_has_case_access(user.user_id, case_id) and "*" not in role_permissions(user.role):
            raise HTTPException(status_code=403, detail="No access to this case")
        if not user.can_on_case(case_id, permission):
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return user

    return _check


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""
