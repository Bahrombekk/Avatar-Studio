"""Analitika endpointi (/api/analytics) — admin himoyasi bilan."""
from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.services import avatar_store

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics")
def analytics(_: bool = Depends(require_admin)):
    return avatar_store.analytics()
