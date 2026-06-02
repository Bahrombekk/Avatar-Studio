"""Idle (blink) video generatsiya xizmati — LivePortrait subprocess orqali.

LivePortrait alohida conda muhitida (`liveportrait`) ishlaydi, backend esa
`musetalk` muhitida. Shuning uchun import emas, `conda run` bilan subprocess:
yuklangan portretdan gen_idle.py idle.mp4 yasaydi.

Bu funksiya jobs.start() ichida fon thread'ida chaqiriladi (uzoq, ~10-20s GPU).
"""
import os
import sys
import subprocess

from app.core.paths import (
    LP_DIR,
    LP_GEN_IDLE,
    avatar_idle_file,
    avatar_portrait_file,
)
from app.services import avatar_store

IDLE_DURATION = 4.0     # sekund (MuseTalk forward+backward loop qiladi)
TIMEOUT_SEC = 600       # 10 daqiqa — generatsiya bundan oshmasligi kerak


def _python_bin() -> str:
    """Idle generatsiya uchun Python interpretatori.

    Portativ rejim: bundle qilingan muhit (backend o'zi ishlayotgan python =
    sys.executable) gen_idle.py ni ishlata oladi. Eski alohida conda muhiti
    kerak bo'lsa LP_PYTHON env bilan bekor qilinadi.
    """
    return os.environ.get("LP_PYTHON") or sys.executable


def generate_idle(avatar_id: str) -> str:
    """Avatar portretidan idle.mp4 yasaydi. Xato bo'lsa RuntimeError ko'taradi."""
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise RuntimeError("Avatar topilmadi")

    src = avatar_portrait_file(avatar_id)
    if not src.is_file():
        raise RuntimeError("Portret yuklanmagan — avval rasm yuklang")

    if not LP_GEN_IDLE.is_file():
        raise RuntimeError(f"gen_idle.py topilmadi: {LP_GEN_IDLE}")

    out = avatar_idle_file(avatar_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    fps = int(av.get("fps", 25))
    blink_every = float(av.get("blinkRate", 4))

    cmd = [
        _python_bin(), str(LP_GEN_IDLE),
        "--source", str(src),
        "--out", str(out),
        "--fps", str(fps),
        "--blink-every", str(blink_every),
        "--duration", str(IDLE_DURATION),
    ]
    # Toza PYTHONPATH: backend MT_DIR (MuseTalk) ni PYTHONPATH'ga qo'yadi, lekin
    # MuseTalk va LivePortrait ikkalasida ham `src` paketi bor — to'qnashuv
    # segfault (kod -11) keltiradi. Subprocess uchun faqat LP_DIR qoldiramiz.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(LP_DIR)
    proc = subprocess.run(cmd, cwd=str(LP_DIR), capture_output=True,
                          text=True, timeout=TIMEOUT_SEC, env=env)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-600:]
        raise RuntimeError(f"Idle generatsiya xato (kod {proc.returncode}): {tail}")
    if not (out.is_file() and out.stat().st_size > 0):
        raise RuntimeError("Idle video yaratilmadi (chiqish fayli yo'q)")
    return str(out)
