"""Route yordamchilari — so'rovdan avatar + ovozni aniqlash, admin himoyasi."""
from fastapi import Header, HTTPException

from app.core.auth import verify_token
from app.services import avatar_store
from app.services.tts import DEFAULT_VOICE


def require_admin(authorization: str = Header(default="")):
    """Admin endpointlari uchun: Authorization: Bearer <token> tekshiriladi.

    Public (user) endpointlarda ishlatilmaydi. Token noto'g'ri → 401.
    """
    token = authorization[7:] if authorization.lower().startswith("bearer ") else authorization
    if not verify_token(token):
        raise HTTPException(401, "Avtorizatsiya talab qilinadi")
    return True


def resolve(req):
    """ChatRequest'dan (avatar, voice) ni aniqlaydi.

    Avatar tanlangan-u, ovoz aniq berilmagan bo'lsa — avatarning o'z ovozi.
    """
    avatar = avatar_store.get_avatar(req.avatar_id) if req.avatar_id else None
    voice = req.voice
    if avatar and req.voice == DEFAULT_VOICE and avatar.get("voice"):
        voice = avatar["voice"]
    return avatar, voice
