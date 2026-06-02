"""MuseTalk preprocessing — idle.mp4 dan per-avatar artefakt yasash.

Backend `musetalk` muhitida ishlaydi, shuning uchun og'ir modellar (VAE,
FaceParsing) allaqachon `musetalk.py` da yuklangan — ularni QAYTA ISHLATAMIZ
(subprocess emas, bir xil muhit). Bu MuseTalk'ning `Avatar.prepare_material`
mantiqi, lekin interaktiv `input()` so'rovlarisiz va per-avatar yo'l bilan.

Natija (data/avatars/<id>/artifact/):
    latents.pt        — UNet uchun VAE latentlari (forward+backward sikl)
    coords.pkl        — yuz bbox koordinatalari (sikl)
    mask_coords.pkl   — blending mask qutilari (sikl)
    mask/             — har kadr uchun parsing mask PNG
    full_imgs/        — sikl kadrlari PNG
    avator_info.json  — meta

jobs.start() ichida fon thread'ida chaqiriladi (uzoq, GPU).
"""
import glob
import json
import os
import pickle
import shutil
import subprocess
import sys

from app.core.paths import BACKEND_DIR, MT_DIR, avatar_artifact_dir, avatar_idle_file
from app.services import avatar_store, musetalk

PREP_TIMEOUT_SEC = 1800   # 30 daqiqa — preprocessing bundan oshmasligi kerak

# v15: bbox_shift har doim 0; faqat extra_margin va parsing_mode ta'sir qiladi.
BBOX_SHIFT = 0
PARSING_MODE = "jaw"
DEFAULT_EXTRA_MARGIN = 10
_COORD_PLACEHOLDER = (0.0, 0.0, 0.0, 0.0)


def _video2imgs(vid_path: str, save_dir: str) -> int:
    """Videoni ketma-ket PNG kadrlarga ajratadi. Yozilgan kadr sonini qaytaradi."""
    import cv2
    cap = cv2.VideoCapture(vid_path)
    count = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            cv2.imwrite(os.path.join(save_dir, f"{count:08d}.png"), frame)
            count += 1
    finally:
        cap.release()
    return count


def preprocess_avatar(avatar_id: str) -> str:
    """Avatar idle videosidan MuseTalk artefakt yasaydi. Xato → RuntimeError."""
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise RuntimeError("Avatar topilmadi")

    idle = avatar_idle_file(avatar_id)
    if not idle.is_file():
        raise RuntimeError("Idle video topilmadi — avval idle yarating")

    # Modellar (VAE, FaceParsing) yuklanganini kafolatlash. cwd → MT_DIR bo'ladi,
    # shu sababli MuseTalk'ning nisbiy model yo'llari ham ishlaydi.
    musetalk.ensure_loaded()

    import cv2
    import torch
    from musetalk.utils.preprocessing import get_landmark_and_bbox
    from musetalk.utils.blending import get_image_prepare_material

    vae = musetalk._vae
    fp = musetalk._fp
    if vae is None or fp is None:
        raise RuntimeError("MuseTalk modellari yuklanmadi (vae/fp yo'q)")

    extra_margin = int(av.get("extraMargin", DEFAULT_EXTRA_MARGIN))

    art = avatar_artifact_dir(avatar_id)
    tmp = art.parent / "artifact.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    full_imgs = tmp / "full_imgs"
    mask_dir = tmp / "mask"
    full_imgs.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)

    # 1. Video → kadrlar.
    n = _video2imgs(str(idle), str(full_imgs))
    if n == 0:
        raise RuntimeError("Idle videodan kadr o'qilmadi")

    img_list = sorted(glob.glob(os.path.join(str(full_imgs), "*.png")))

    # 2. Landmark + bbox.
    coord_list, frame_list = get_landmark_and_bbox(img_list, BBOX_SHIFT)

    # 3. Har kadr uchun yuzni kesib, VAE latentlariga aylantirish.
    input_latent_list = []
    for idx, (bbox, frame) in enumerate(zip(coord_list, frame_list)):
        if bbox == _COORD_PLACEHOLDER:
            continue
        x1, y1, x2, y2 = bbox
        y2 = min(y2 + extra_margin, frame.shape[0])
        coord_list[idx] = [x1, y1, x2, y2]
        crop = frame[y1:y2, x1:x2]
        resized = cv2.resize(crop, (256, 256), interpolation=cv2.INTER_LANCZOS4)
        input_latent_list.append(vae.get_latents_for_unet(resized))

    if not input_latent_list:
        raise RuntimeError("Idle videoda yuz aniqlanmadi — boshqa portret tanlang")

    # 4. Forward+backward sikl (uzluksiz loop uchun).
    frame_cycle = frame_list + frame_list[::-1]
    coord_cycle = coord_list + coord_list[::-1]
    latent_cycle = input_latent_list + input_latent_list[::-1]

    # 5. Sikl kadrlarini qayta yozish + blending mask yasash.
    mask_coords = []
    for i, frame in enumerate(frame_cycle):
        cv2.imwrite(os.path.join(str(full_imgs), f"{i:08d}.png"), frame)
        x1, y1, x2, y2 = coord_cycle[i]
        mask, crop_box = get_image_prepare_material(
            frame, [x1, y1, x2, y2], fp=fp, mode=PARSING_MODE
        )
        cv2.imwrite(os.path.join(str(mask_dir), f"{i:08d}.png"), mask)
        mask_coords.append(crop_box)

    # 6. Artefaktni saqlash.
    with open(tmp / "coords.pkl", "wb") as f:
        pickle.dump(coord_cycle, f)
    with open(tmp / "mask_coords.pkl", "wb") as f:
        pickle.dump(mask_coords, f)
    torch.save(latent_cycle, str(tmp / "latents.pt"))
    with open(tmp / "avator_info.json", "w", encoding="utf-8") as f:
        json.dump({
            "avatar_id": avatar_id,
            "video_path": str(idle),
            "bbox_shift": BBOX_SHIFT,
            "extra_margin": extra_margin,
            "version": "v15",
            "frames": len(frame_cycle),
        }, f, ensure_ascii=False)

    # 7. Atomik almashtirish (eski artefaktni o'chirib, tmp'ni o'rniga qo'yamiz).
    if art.exists():
        shutil.rmtree(art)
    tmp.rename(art)

    # Eski keshlangan artefaktni bo'shatamiz (qayta yasalgan bo'lishi mumkin).
    musetalk.invalidate(avatar_id)
    # Avatar endi o'z yuzi bilan lip-sync qila oladi → real/live.
    avatar_store.set_ready(avatar_id, True)
    return str(art)


def preprocess_avatar_subprocess(avatar_id: str) -> str:
    """preprocess_avatar ni ALOHIDA jarayonda (subprocess) ishga tushiradi.

    Sabab: jobs.start() fon thread'ida ishlaydi; MuseTalk preprocessing'dagi PIL/
    FaceParsing asosiy bo'lmagan thread'da 'ImagingCore' xatosini beradi. Toza
    jarayonning asosiy thread'ida ishonchli ishlaydi (idle generatsiya bilan bir xil
    uslub). Artefakt va ready holatini bola jarayon avatar.json'ga yozadi.
    """
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise RuntimeError("Avatar topilmadi")
    if not avatar_idle_file(avatar_id).is_file():
        raise RuntimeError("Idle video topilmadi — avval idle yarating")

    env = os.environ.copy()
    # Bola jarayon `app` (cwd=BACKEND_DIR) va MuseTalk (MT_DIR) modullarini topsin.
    env["PYTHONPATH"] = os.pathsep.join([str(MT_DIR), str(BACKEND_DIR)])
    cmd = [sys.executable, "-m", "app.services.preprocess", avatar_id]
    proc = subprocess.run(cmd, cwd=str(BACKEND_DIR), capture_output=True,
                          text=True, timeout=PREP_TIMEOUT_SEC, env=env)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-800:]
        raise RuntimeError(f"MuseTalk preprocessing xato (kod {proc.returncode}): {tail}")

    art = avatar_artifact_dir(avatar_id)
    if not (art.is_dir() and (art / "latents.pt").is_file()):
        raise RuntimeError("Artefakt yaratilmadi (latents.pt yo'q)")
    return str(art)


if __name__ == "__main__":
    # Subprocess kirish nuqtasi: python -m app.services.preprocess <avatar_id>
    if len(sys.argv) < 2:
        print("Foydalanish: python -m app.services.preprocess <avatar_id>", file=sys.stderr)
        sys.exit(2)
    preprocess_avatar(sys.argv[1])
    print("PREPROCESS-OK")
