"""Ishlash preseti — "heavy" (og'ir, 5090/kuchli GPU) yoki "light" (yengil, zaif GPU /
DGX Spark kabi past-bandwidth qurilmalar).

Sifat-modelni O'ZGARTIRMAYDI — faqat resolution va batch kabi YUK knoblarini sozlaydi:
  • heavy: avatar maxDim (1280/1920) to'liq, batch katta — eng yuqori sifat.
  • light: resolution past darajaga cheklanadi + kichik batch — zaif GPU'da ravon.

Runtime'da almashtiriladi (set_preset) — yangi so'rovlar darrov yangi presetda ishlaydi.
Standart: PERF_PRESET env (yo'q bo'lsa "heavy", ya'ni hozirgi xulq saqlanadi).
"""
import os
import threading

_lock = threading.Lock()


def _norm(p: str) -> str:
    p = (p or "").strip().lower()
    return p if p in ("light", "heavy") else "heavy"


_preset = _norm(os.environ.get("PERF_PRESET", "heavy"))

# Yengil rejimda resolution shifti (uzun tomon, px). env bilan sozlanadi.
_LIGHT_DIM = int(os.environ.get("PERF_LIGHT_DIM", "960"))
_LIGHT_BATCH = int(os.environ.get("PERF_LIGHT_BATCH", "8"))
_HEAVY_BATCH = int(os.environ.get("MT_BATCH", "16"))


def get_preset() -> str:
    return _preset


def set_preset(p: str) -> bool:
    """Presetni almashtiradi (light/heavy). Muvaffaqiyatli bo'lsa True."""
    global _preset
    p = (p or "").strip().lower()
    if p not in ("light", "heavy"):
        return False
    with _lock:
        _preset = p
    return True


def max_dim_cap() -> int:
    """Joriy presetda ruxsat etilgan eng katta chiqish o'lchami (uzun tomon)."""
    return _LIGHT_DIM if _preset == "light" else 1920


def batch_size() -> int:
    """Joriy presetga mos inference batch hajmi."""
    return _LIGHT_BATCH if _preset == "light" else _HEAVY_BATCH


def info() -> dict:
    return {"preset": _preset, "max_dim_cap": max_dim_cap(),
            "batch_size": batch_size(), "light_dim": _LIGHT_DIM}
