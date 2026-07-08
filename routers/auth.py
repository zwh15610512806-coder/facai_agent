"""Compatibility endpoints for the retired LAN admin login."""
from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from services.security import clear_admin_cookie


router = APIRouter()


class LoginRequest(BaseModel):
    token: str = Field("", max_length=500)


@router.get("/status")
def auth_status():
    return {
        "enabled": False,
        "configured": False,
        "authenticated": True,
    }


@router.post("/login")
def login(_data: LoginRequest):
    return {"success": True, "enabled": False, "authenticated": True}


@router.post("/logout")
def logout(response: Response):
    clear_admin_cookie(response)
    return {"success": True}
