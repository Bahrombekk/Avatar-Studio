"""Admin login endpointlari — bitta parol (env ADMIN_PASSWORD)."""
import hmac

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import require_admin
from app.core.auth import admin_password, admin_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(req: LoginRequest):
    """Parol to'g'ri bo'lsa sessiya tokenini qaytaradi."""
    if not hmac.compare_digest(req.password, admin_password()):
        raise HTTPException(401, "Parol noto'g'ri")
    return {"token": admin_token()}


@router.get("/check")
def check(_: bool = Depends(require_admin)):
    """Token amal qiladimi (frontend yuklanganda tekshiradi)."""
    return {"ok": True}
