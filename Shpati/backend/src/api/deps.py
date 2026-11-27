from __future__ import annotations

from fastapi import Header, HTTPException

from core.auth_service import AuthService


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    user = AuthService.resolve_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
