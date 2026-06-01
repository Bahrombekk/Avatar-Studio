"""Route yordamchilari — so'rovdan avatar + ovozni aniqlash."""
from app.services import avatar_store
from app.services.tts import DEFAULT_VOICE


def resolve(req):
    """ChatRequest'dan (avatar, voice) ni aniqlaydi.

    Avatar tanlangan-u, ovoz aniq berilmagan bo'lsa — avatarning o'z ovozi.
    """
    avatar = avatar_store.get_avatar(req.avatar_id) if req.avatar_id else None
    voice = req.voice
    if avatar and req.voice == DEFAULT_VOICE and avatar.get("voice"):
        voice = avatar["voice"]
    return avatar, voice
