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
    avatar_motion_dir,
    avatar_portrait_file,
)
from app.services import avatar_store

IDLE_DURATION = 8.0     # sekund — uzunroq klip → harakat kamroq takrorlanadi
                        # (MuseTalk forward+backward loop qiladi; artefakt kattaroq)
TIMEOUT_SEC = 600       # 10 daqiqa — generatsiya bundan oshmasligi kerak


def _python_bin() -> str:
    """Idle generatsiya uchun Python interpretatori.

    Portativ rejim: bundle qilingan muhit (backend o'zi ishlayotgan python =
    sys.executable) gen_idle.py ni ishlata oladi. Eski alohida conda muhiti
    kerak bo'lsa LP_PYTHON env bilan bekor qilinadi.
    """
    return os.environ.get("LP_PYTHON") or sys.executable


# Build HAR DOIM 1080p (1920) bazada quriladi — bu eng yuqori sifatli manba.
# Ishlatishda (real-time / Studio) avatar.maxDim bo'yicha 720p (1280)'ga BIR ZUMDA
# kichraytiriladi (musetalk._downscale_artifact). Shunda 720↔1080 almashtirish
# QAYTA QURISHNI talab qilmaydi — bitta og'ir GPU build ikkala rezolyutsiyaga xizmat.
BUILD_MAX_DIM = 1920


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

    # Admin "Bosh harakati" slideri (0..1) → gradus amplitudalari. 0 = qotgan,
    # 1 = sezilarli (lekin sifat/identiklik buzilmaydigan xavfsiz chegara).
    # 0.45 (default) ≈ yaw 2.8° / pitch 1.6° / roll 1.1° (tabiiy "tirik" tebranish).
    head = max(0.0, min(1.0, float(av.get("headMotion", 0.45))))
    head_yaw = round(head * 6.2, 2)
    head_pitch = round(head * 3.5, 2)
    head_roll = round(head * 2.4, 2)

    cmd = [
        _python_bin(), str(LP_GEN_IDLE),
        "--source", str(src),
        "--out", str(out),
        "--fps", str(fps),
        "--blink-every", str(blink_every),
        "--duration", str(IDLE_DURATION),
        "--head-yaw", str(head_yaw),
        "--head-pitch", str(head_pitch),
        "--head-roll", str(head_roll),
    ]
    # Toza PYTHONPATH: backend MT_DIR (MuseTalk) ni PYTHONPATH'ga qo'yadi, lekin
    # MuseTalk va LivePortrait ikkalasida ham `src` paketi bor — to'qnashuv
    # segfault (kod -11) keltiradi. Subprocess uchun faqat LP_DIR qoldiramiz.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(LP_DIR)
    env["RT_SOURCE_MAX_DIM"] = str(BUILD_MAX_DIM)   # har doim 1080p baza (kichraytirish runtime'da)
    proc = subprocess.run(cmd, cwd=str(LP_DIR), capture_output=True,
                          text=True, timeout=TIMEOUT_SEC, env=env)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-600:]
        raise RuntimeError(f"Idle generatsiya xato (kod {proc.returncode}): {tail}")
    if not (out.is_file() and out.stat().st_size > 0):
        raise RuntimeError("Idle video yaratilmadi (chiqish fayli yo'q)")
    return str(out)


def generate_motion_clips(avatar_id: str) -> str:
    """Avatar uchun BARCHA bosh-harakat primitiv kliplarini yaratadi (2-faza).

    gen_idle.py --all-motion (bitta LivePortrait yuklash) → motion/<type>.mp4 lar.
    Keyin preprocess_motion_all artefaktlarni quradi."""
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise RuntimeError("Avatar topilmadi")
    src = avatar_portrait_file(avatar_id)
    if not src.is_file():
        raise RuntimeError("Portret yuklanmagan — avval rasm yuklang")
    if not LP_GEN_IDLE.is_file():
        raise RuntimeError(f"gen_idle.py topilmadi: {LP_GEN_IDLE}")

    out_dir = avatar_motion_dir(avatar_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    fps = int(av.get("fps", 25))
    cmd = [
        _python_bin(), str(LP_GEN_IDLE),
        "--source", str(src), "--all-motion", "--out-dir", str(out_dir),
        "--fps", str(fps),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(LP_DIR)
    env["RT_SOURCE_MAX_DIM"] = str(BUILD_MAX_DIM)   # har doim 1080p baza (kichraytirish runtime'da)
    proc = subprocess.run(cmd, cwd=str(LP_DIR), capture_output=True,
                          text=True, timeout=TIMEOUT_SEC, env=env)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-600:]
        raise RuntimeError(f"Harakat klip generatsiya xato (kod {proc.returncode}): {tail}")
    neutral = out_dir / "neutral.mp4"
    if not (neutral.is_file() and neutral.stat().st_size > 0):
        raise RuntimeError("Harakat kliplari yaratilmadi (neutral.mp4 yo'q)")
    return str(out_dir)
