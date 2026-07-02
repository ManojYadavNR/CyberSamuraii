"""FastAPI dependencies for enterprise auth."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.enterprise.auth_tokens import decode_access_token
from services.enterprise.db import enterprise_enabled
from services.enterprise.rbac import has_permission

_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, user_id: str, username: str, role: str, name: str = ""):
        self.user_id = user_id
        self.username = username
        self.role = role
        self.name = name

    def can(self, permission: str) -> bool:
        return has_permission(self.role, permission)


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
        role=data.get("role", "VIEWER"),
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


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""
