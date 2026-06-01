"""Tizim endpointlari — ovozlar reestri, idle rasm, health, cache admin, video."""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import load_env_var
from app.core.paths import AVATAR_ID, AVATARS_DIR, IDLE_IMAGE, voice_videos_dir
from app.services import musetalk
from app.services.cache import aggregate_stats, clear_all
from app.services.tts import VOICES, DEFAULT_VOICE

router = APIRouter(tags=["system"])


@router.get("/voices")
def voices():
    return {
        "default": DEFAULT_VOICE,
        "voices": [{"id": k, "label": v.get("label", k), "provider": v["provider"]}
                   for k, v in VOICES.items()],
    }


@router.get("/idle.jpg")
def idle_image():
    if not IDLE_IMAGE.exists():
        raise HTTPException(404, "Idle rasm topilmadi")
    return FileResponse(str(IDLE_IMAGE), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/health")
def health():
    yx = (load_env_var("YX_API_KEY") or load_env_var("YX_IAM_TOKEN")) and load_env_var("YX_FOLDER_ID")
    return {
        "status": "ok",
        "model": "loaded" if musetalk.is_loaded() else "loading",
        "avatar": AVATAR_ID,
        "api_key": "set ✓" if os.environ.get("OPENAI_API_KEY") else "NOT SET",
        "yandex": "set ✓" if yx else "NOT SET",
        "cache": aggregate_stats(),
    }


@router.get("/cache/stats")
def cache_stats():
    return aggregate_stats()


@router.post("/cache/clear")
def cache_clear():
    return {"cleared": clear_all()}


def _safe_segment(value: str) -> str:
    """Path-traversal himoyasi: bitta yo'l bo'lagi ekanini tekshiradi."""
    if not value or "/" in value or "\\" in value or value in (".", ".."):
        raise HTTPException(400, "Noto'g'ri yo'l")
    return value


@router.get("/videos/{scope}/{voice}/{filename}")
def serve_video(scope: str, voice: str, filename: str):
    """Kesh videolarini (avatar, ovoz) papkasidan beradi — xavfsiz."""
    _safe_segment(scope)
    _safe_segment(voice)
    _safe_segment(filename)
    if not filename.endswith(".mp4"):
        raise HTTPException(404, "Video topilmadi")
    path = (voice_videos_dir(scope, voice) / filename).resolve()
    # Yakuniy yo'l haqiqatan AVATARS_DIR ostida ekanini tasdiqlaymiz.
    if not str(path).startswith(str(AVATARS_DIR.resolve())) or not path.is_file():
        raise HTTPException(404, "Video topilmadi")
    return FileResponse(str(path), media_type="video/mp4")
