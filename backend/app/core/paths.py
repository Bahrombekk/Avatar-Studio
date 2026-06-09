"""Loyiha yo'llari — bitta joyda.

MuseTalk modellari va madina_lp avatar artefakti MT_DIR ichida.
Runtime ma'lumotlar (data/, static/, checkpoints/) backend/ ostida.
"""
import os
import sys
import tempfile
from pathlib import Path

from app.core.config import BACKEND_DIR

# Loyiha ildizi (backend/ ning ota-papkasi) — barcha standart yo'llar shunga nisbatan.
_PROJECT_ROOT = BACKEND_DIR.parent

# ── MuseTalk modellari (standart: loyiha ichidagi models/MuseTalk) ──
# MT_DIR env bilan bekor qilsa bo'ladi; aks holda loyiha o'zini-o'zi ta'minlaydi.
MT_DIR = Path(os.environ.get("MT_DIR", str(_PROJECT_ROOT / "models" / "MuseTalk")))
AVATAR_ID = "madina_lp"
AVATAR_DIR = MT_DIR / f"results/v15/avatars/{AVATAR_ID}"

# ── LivePortrait (idle/harakat generatsiya, alohida conda muhitida ishlaydi) ──
# Standart: loyiha ichidagi models/LivePortrait; LP_DIR env bilan bekor qilsa bo'ladi.
LP_DIR = Path(os.environ.get("LP_DIR", str(_PROJECT_ROOT / "models" / "LivePortrait")))
# gen_idle.py — bizning maxsus skriptimiz (idle + bosh-harakat primitivlari). U
# ASOSIY repoda (backend/scripts/) saqlanadi — submodule'da emas (qayta o'rnatishda
# yo'qolmasligi uchun). LivePortrait kutubxonasi PYTHONPATH=LP_DIR orqali topiladi.
LP_GEN_IDLE = BACKEND_DIR / "scripts" / "gen_idle.py"

AVATAR_LATENTS = AVATAR_DIR / "latents.pt"
AVATAR_COORDS = AVATAR_DIR / "coords.pkl"
AVATAR_MASK_COORD = AVATAR_DIR / "mask_coords.pkl"
AVATAR_MASK_DIR = AVATAR_DIR / "mask"
AVATAR_IMGS_DIR = AVATAR_DIR / "full_imgs"

# ── Runtime ma'lumotlar (standart: backend/data; DATA_DIR env bilan bekor qilsa bo'ladi) ──
# Env override asosan test izolatsiyasi uchun (tmp papkaga yo'naltirish), shuningdek
# bir necha instansiya/deploy stsenariylarida foydali.
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BACKEND_DIR / "data")))
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

# ── Video Studiya (offline HD render kutubxonasi, HeyGen uslubi) ──
#   data/renders/index.json          → render meta ro'yxati (eng yangi birinchi)
#   data/renders/<render_id>.mp4      → tayyor video
RENDERS_DIR = DATA_DIR / "renders"
RENDERS_INDEX = RENDERS_DIR / "index.json"


def render_file(render_id: str) -> Path:
    return RENDERS_DIR / f"{render_id}.mp4"


# ── Tayyor javoblar (pre-rendered Q&A — real-time'da savol mosligi bo'yicha o'ynaladi) ──
#   data/canned/index.json       → tayyor javoblar meta (savol variantlari + javob)
#   data/canned/<id>.mp4         → tayyor javob videosi
CANNED_DIR = DATA_DIR / "canned"
CANNED_INDEX = CANNED_DIR / "index.json"


def canned_file(canned_id: str) -> Path:
    return CANNED_DIR / f"{canned_id}.mp4"

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


def avatar_motion_dir(avatar_id: str) -> Path:
    """Harakat primitivlari papkasi (nod/tilt/.../neutral klip + artefaktlari)."""
    return avatar_dir(avatar_id) / "motion"


def avatar_motion_clip(avatar_id: str, mtype: str) -> Path:
    """Primitiv harakat klipi (LivePortrait chiqishi): motion/<type>.mp4."""
    return avatar_motion_dir(avatar_id) / f"{mtype}.mp4"


def avatar_motion_artifact(avatar_id: str, mtype: str) -> Path:
    """Primitiv MuseTalk artefakti: motion/<type>/ (latents/coords/mask/full_imgs)."""
    return avatar_motion_dir(avatar_id) / mtype


def avatar_knowledge_dir(avatar_id: str) -> Path:
    """Per-avatar bilim bazasi (RAG) papkasi: knowledge/index.json + sources/."""
    return avatar_dir(avatar_id) / "knowledge"


def avatar_knowledge_index(avatar_id: str) -> Path:
    return avatar_knowledge_dir(avatar_id) / "index.json"


def avatar_knowledge_sources_dir(avatar_id: str) -> Path:
    return avatar_knowledge_dir(avatar_id) / "sources"


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


# ── Vaqtinchalik (Linux tmpfs; Windows/test'da OS temp papkasi) ──
# Production WSL'da /tmp tmpfs tez. Windows yoki testda OS temp ishlatiladi
# (C:\tmp yaratib qo'ymaslik uchun). TEMP_DIR/VID_OUT_DIR env bilan bekor qilsa bo'ladi.
_TMP_ROOT = "/tmp" if os.name == "posix" else tempfile.gettempdir()
TEMP_DIR = Path(os.environ.get("TEMP_DIR", os.path.join(_TMP_ROOT, "lp_avatar_temp")))
VID_OUT_DIR = Path(os.environ.get("VID_OUT_DIR", os.path.join(_TMP_ROOT, "lp_avatar_videos")))

# ── Frontend (Vite build natijasi) ──
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

for _d in (DATA_DIR, AVATARS_DIR, CHECKPOINTS_DIR, TEMP_DIR, VID_OUT_DIR, RENDERS_DIR, CANNED_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# MuseTalk paketini import qilish uchun sys.path ga qo'shamiz.
if str(MT_DIR) not in sys.path:
    sys.path.insert(0, str(MT_DIR))
