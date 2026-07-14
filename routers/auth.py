"""Authentication endpoints for role-scoped LAN sessions."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from services.security import (
    auth_configured,
    auth_enabled,
    clear_admin_cookie,
    principal_from_request,
    principal_from_token,
    set_session_cookie,
)

router = APIRouter()


class LoginRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=500)


@router.get("/status")
def auth_status(request: Request):
    principal = principal_from_request(request) if auth_enabled() else None
    return {
        "enabled": auth_enabled(),
        "configured": auth_configured(),
        "authenticated": not auth_enabled() or principal is not None,
        "role": principal.role if principal else ("admin" if not auth_enabled() else None),
    }


@router.post("/login")
def login(data: LoginRequest, response: Response):
    if not auth_enabled():
        return {
            "success": True,
            "enabled": False,
            "authenticated": True,
            "role": "admin",
        }
    if not auth_configured():
        raise HTTPException(status_code=503, detail="FACAI_ADMIN_TOKEN is not configured")
    principal = principal_from_token(data.token, source="cookie")
    if principal is None:
        raise HTTPException(status_code=401, detail="访问口令不正确")
    set_session_cookie(response, principal)
    return {
        "success": True,
        "enabled": True,
        "authenticated": True,
        "role": principal.role,
    }


@router.post("/logout")
def logout(response: Response):
    clear_admin_cookie(response)
    return {"success": True}
