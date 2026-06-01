"""Loyiha yo'llari — bitta joyda.

MuseTalk modellari va madina_lp avatar artefakti MT_DIR ichida.
Runtime ma'lumotlar (data/, static/, checkpoints/) backend/ ostida.
"""
import os
import sys
from pathlib import Path

from app.core.config import BACKEND_DIR

# ── Modellar (tashqi, MT_DIR env bilan moslashuvchan) ──
MT_DIR = Path(os.environ.get("MT_DIR", "/home/user/avatar_project/MuseTalk"))
AVATAR_ID = "madina_lp"
AVATAR_DIR = MT_DIR / f"results/v15/avatars/{AVATAR_ID}"

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
