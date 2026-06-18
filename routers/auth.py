"""Authentication endpoints for optional LAN admin protection."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from services.security import (
    auth_configured,
    auth_enabled,
    clear_admin_cookie,
    is_admin_request,
    set_admin_cookie,
    verify_admin_token,
)


router = APIRouter()


class LoginRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=500)


@router.get("/status")
def auth_status(request: Request):
    return {
        "enabled": auth_enabled(),
        "configured": auth_configured(),
        "authenticated": is_admin_request(request),
    }


@router.post("/login")
def login(data: LoginRequest, response: Response):
    if not auth_enabled():
        return {"success": True, "enabled": False, "authenticated": True}
    if not auth_configured():
        raise HTTPException(status_code=503, detail="FACAI_ADMIN_TOKEN is not configured")
    if not verify_admin_token(data.token):
        raise HTTPException(status_code=401, detail="管理员口令不正确")
    set_admin_cookie(response, data.token)
    return {"success": True, "enabled": True, "authenticated": True}


@router.post("/logout")
def logout(response: Response):
    clear_admin_cookie(response)
    return {"success": True}
