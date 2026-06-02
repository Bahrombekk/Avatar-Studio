"""Loyiha yo'llari — bitta joyda.

MuseTalk modellari va madina_lp avatar artefakti MT_DIR ichida.
Runtime ma'lumotlar (data/, static/, checkpoints/) backend/ ostida.
"""
import os
import sys
from pathlib import Path

from app.core.config import BACKEND_DIR

# Loyiha ildizi (backend/ ning ota-papkasi) — barcha standart yo'llar shunga nisbatan.
_PROJECT_ROOT = BACKEND_DIR.parent

# ── MuseTalk modellari (standart: loyiha ichidagi models/MuseTalk) ──
# MT_DIR env bilan bekor qilsa bo'ladi; aks holda loyiha o'zini-o'zi ta'minlaydi.
MT_DIR = Path(os.environ.get("MT_DIR", str(_PROJECT_ROOT / "models" / "MuseTalk")))
AVATAR_ID = "madina_lp"
AVATAR_DIR = MT_DIR / f"results/v15/avatars/{AVATAR_ID}"

# ── LivePortrait (idle generatsiya, alohida conda muhitida ishlaydi) ──
# Standart: loyiha ichidagi models/LivePortrait; LP_DIR env bilan bekor qilsa bo'ladi.
LP_DIR = Path(os.environ.get("LP_DIR", str(_PROJECT_ROOT / "models" / "LivePortrait")))
LP_GEN_IDLE = LP_DIR / "gen_idle.py"

AVATAR_LATENTS = AVATAR_DIR / "latents.pt"
AVATAR_COORDS = AVATAR_DIR / "coords.pkl"
AVATAR_MASK_COORD = AVATAR_DIR / "mask_coords.pkl"
AVATAR_MASK_DIR = AVATAR_DIR / "mask"
AVATAR_IMGS_DIR = AVATAR_DIR / "full_imgs"

# ── Runtime ma'lumotlar (backend/ ostida) ──
DATA_DIR = BACKEND_DIR / "data"
STATIC_DIR = BACKEND_DIR / "static"
CHECKPOINTS_DIR = BACKEND_DIR / "checkpoints"
IDLE_IMAGE = STATIC_DIR / "idle.jpg"

# ── insightface (yuz validatsiyasi, buffalo_l) — loyiha ichida bundle qilingan ──
# insightface modelni <root>/models/<name> sifatida qidiradi, ya'ni
# checkpoints/insightface/models/buffalo_l. INSIGHTFACE_ROOT env bilan bekor qilsa bo'ladi.
INSIGHTFACE_ROOT = Path(
    os.environ.get("INSIGHTFACE_ROOT", str(CHECKPOINTS_DIR / "insightface"))
)

# ── Per-avatar / per-voice saqlash tuzilmasi ──
#   data/registry.json                                  → avatar id'lar ro'yxati (tartib)
#   data/avatars/<id>/avatar.json                       → to'liq konfiguratsiya
#   data/avatars/<id>/stats.json                        → jonli statistika
#   data/avatars/<id>/events.jsonl                      → shu avatar suhbat loglari
#   data/avatars/<id>/voices/<voice>/cache.json         → shu avatar+ovoz kesh indeksi
#   data/avatars/<id>/voices/<voice>/videos/<eid>.mp4   → kesh videolari
REGISTRY_FILE = DATA_DIR / "registry.json"
AVATARS_DIR = DATA_DIR / "avatars"

# Avatar tanlanmagan (default) so'rovlar uchun psevdo-avatar papkasi.
DEFAULT_SCOPE = "_default"


def avatar_dir(avatar_id: str) -> Path:
    return AVATARS_DIR / avatar_id


def avatar_config_file(avatar_id: str) -> Path:
    return avatar_dir(avatar_id) / "avatar.json"


def avatar_stats_file(avatar_id: str) -> Path:
    return avatar_dir(avatar_id) / "stats.json"


def avatar_events_file(avatar_id: str) -> Path:
    return avatar_dir(avatar_id) / "events.jsonl"


def voice_dir(avatar_id: str, voice: str) -> Path:
    return avatar_dir(avatar_id) / "voices" / voice


def voice_cache_file(avatar_id: str, voice: str) -> Path:
    return voice_dir(avatar_id, voice) / "cache.json"


def voice_videos_dir(avatar_id: str, voice: str) -> Path:
    return voice_dir(avatar_id, voice) / "videos"


def avatar_source_dir(avatar_id: str) -> Path:
    """Foydalanuvchi yuklagan xom materiallar (portret rasm) papkasi."""
    return avatar_dir(avatar_id) / "source"


def avatar_portrait_file(avatar_id: str) -> Path:
    """Avatar manba portreti (yuz validatsiyasidan o'tgan, idle generatsiya kirishi)."""
    return avatar_source_dir(avatar_id) / "portrait.jpg"


def avatar_idle_file(avatar_id: str) -> Path:
    """LivePortrait generatsiya qilgan idle (blink) video — MuseTalk preprocessing kirishi."""
    return avatar_dir(avatar_id) / "idle.mp4"


def avatar_artifact_dir(avatar_id: str) -> Path:
    """MuseTalk preprocessing natijasi (latents.pt, coords.pkl, mask/, full_imgs/, ...).

    Bu artefakt real-time inference kirishi — har avatar uchun alohida.
    """
    return avatar_dir(avatar_id) / "artifact"


def avatar_artifact_paths(avatar_id: str) -> dict:
    """Artefakt ichidagi barcha fayl/papka yo'llari (preprocessing + inference uchun)."""
    d = avatar_artifact_dir(avatar_id)
    return {
        "dir": d,
        "latents": d / "latents.pt",
        "coords": d / "coords.pkl",
        "mask_coords": d / "mask_coords.pkl",
        "mask_dir": d / "mask",
        "imgs_dir": d / "full_imgs",
        "info": d / "avator_info.json",
    }


# ── Vaqtinchalik (Linux tmpfs) ──
TEMP_DIR = Path("/tmp/lp_avatar_temp")
VID_OUT_DIR = Path("/tmp/lp_avatar_videos")

# ── Frontend (Vite build natijasi) ──
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

for _d in (DATA_DIR, AVATARS_DIR, CHECKPOINTS_DIR, TEMP_DIR, VID_OUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# MuseTalk paketini import qilish uchun sys.path ga qo'shamiz.
if str(MT_DIR) not in sys.path:
    sys.path.insert(0, str(MT_DIR))
