"""Suhbatlar endpointlari (/api/conversations) — admin himoyasi bilan."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_admin
from app.services import conversations

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
Admin = Depends(require_admin)


@router.get("")
def list_conversations(limit: int = 100, _: bool = Admin):
    return {"conversations": conversations.list_conversations(min(max(limit, 1), 500))}


@router.get("/{conv_id}")
def get_conversation(conv_id: int, _: bool = Admin):
    data = conversations.get_conversation(conv_id)
    if not data:
        raise HTTPException(404, "Suhbat topilmadi")
    return data
