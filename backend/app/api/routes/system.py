"""Tizim endpointlari — ovozlar reestri, idle rasm, health, cache admin, video."""
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import require_admin
from app.core.config import load_env_var
from app.core.paths import AVATAR_ID, AVATARS_DIR, IDLE_IMAGE, voice_videos_dir
from app.services.cache import aggregate_stats, clear_all
from app.services.tts import VOICES, DEFAULT_VOICE

# DIQQAT: `app.services.musetalk` (torch) `health()` ICHIDA import qilinadi.

router = APIRouter(tags=["system"])


@router.get("/voices")
def voices():
    return {
        "default": DEFAULT_VOICE,
        "voices": [{"id": k, "label": v.get("label", k), "provider": v["provider"]}
                   for k, v in VOICES.items()],
    }


@router.get("/voices/{voice_id}/preview")
def voice_preview(voice_id: str):
    """Ovoz namunasi (o'z tilida bir gap) — editorda eshitib tanlash uchun.
    Keshlangan; birinchi so'rovda generatsiya qilinadi. Public (oddiy namuna)."""
    if "/" in voice_id or "\\" in voice_id:
        raise HTTPException(404, "Topilmadi")
    from app.services import tts as _tts
    try:
        p = _tts.ensure_preview(voice_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Namuna yaratilmadi: {e}")
    return FileResponse(str(p), media_type="audio/wav", filename=f"{voice_id}.wav")


@router.get("/idle.jpg")
def idle_image():
    if not IDLE_IMAGE.exists():
        raise HTTPException(404, "Idle rasm topilmadi")
    return FileResponse(str(IDLE_IMAGE), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/health")
def health():
    yx = (load_env_var("YX_API_KEY") or load_env_var("YX_IAM_TOKEN")) and load_env_var("YX_FOLDER_ID")
    try:
        from app.services import musetalk
        model_state = "loaded" if musetalk.is_loaded() else "loading"
    except Exception:
        # Og'ir ML bog'liqliklari mavjud bo'lmagan yengil muhit (test/CI).
        model_state = "unavailable"
    return {
        "status": "ok",
        "model": model_state,
        "avatar": AVATAR_ID,
        "api_key": "set ✓" if os.environ.get("OPENAI_API_KEY") else "NOT SET",
        "yandex": "set ✓" if yx else "NOT SET",
        "cache": aggregate_stats(),
    }


@router.get("/metrics")
def metrics():
    """Process-level metrikalar (so'rov soni, xato, p50/p95 latency, kesh, uptime)."""
    from app.core.middleware import metrics as _m
    snap = _m.snapshot()
    snap["cache"] = aggregate_stats()
    try:
        from app.services import musetalk
        snap["model_loaded"] = musetalk.is_loaded()
    except Exception:
        snap["model_loaded"] = None
    return snap


@router.get("/cache/stats")
def cache_stats():
    return aggregate_stats()


@router.post("/cache/clear")
def cache_clear(_: bool = Depends(require_admin)):
    # Jonli temir yo'l kesh ham tozalanadi (yengil import — torch'siz).
    try:
        from app.services import railway
        railway.clear_cache()
    except Exception:  # noqa: BLE001
        pass
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
