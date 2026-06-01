"""Chat so'rovi sxemasi."""
from typing import Optional

from pydantic import BaseModel

from app.services.tts import DEFAULT_VOICE


class ChatRequest(BaseModel):
    message: str
    voice: str = DEFAULT_VOICE
    avatar_id: Optional[str] = None
