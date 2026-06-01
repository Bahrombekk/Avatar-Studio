"""Analitika endpointi (/api/analytics)."""
from fastapi import APIRouter

from app.services import avatar_store

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics")
def analytics():
    return avatar_store.analytics()
