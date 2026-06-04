"""MuseTalk preprocessing — video (idle yoki harakat primitivi) dan artefakt yasash.

Backend `musetalk` muhitida ishlaydi, og'ir modellar (VAE, FaceParsing) `musetalk.py`
da yuklangan — qayta ishlatamiz. Bu MuseTalk `Avatar.prepare_material` mantiqi,
interaktiv input()siz, per-avatar yo'l bilan.

Ikki ishlatilishi:
  - preprocess_avatar(id)        — idle.mp4 → asosiy artefakt (lip-sync poydevori)
  - preprocess_motion(id, type)  — motion/<type>.mp4 → primitiv artefakti (2-faza:
    bosh harakati dvigateli — render'da segment trigger'iga ulanadi)

Artefakt (sikl = FAQAT oldinga, palindromsiz; harakat davriy/enveloped → silliq):
    latents.pt, coords.pkl, mask_coords.pkl, mask/, full_imgs/, avator_info.json
"""
import glob
import json
import os
import pickle
import shutil
import subprocess
import sys

from app.core.paths import (
    BACKEND_DIR, MT_DIR, avatar_artifact_dir, avatar_idle_file,
    avatar_motion_artifact, avatar_motion_clip,
)
from app.services import avatar_store, musetalk

PREP_TIMEOUT_SEC = 1800   # 30 daqiqa

# v15: bbox_shift har doim 0; faqat extra_margin va parsing_mode ta'sir qiladi.
BBOX_SHIFT = 0
PARSING_MODE = "jaw"
DEFAULT_EXTRA_MARGIN = 10
_COORD_PLACEHOLDER = (0.0, 0.0, 0.0, 0.0)

# 2-faza harakat primitivlari (neutral = filler).
MOTION_TYPES = ["neutral", "nod", "tilt_left", "tilt_right",
                "turn_left", "turn_right", "lean_forward"]


def _video2imgs(vid_path: str, save_dir: str) -> int:
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


def _video_to_artifact_dir(video: str, dest_dir, extra_margin: int, meta_extra: dict = None):
    """Videodan MuseTalk artefakt yasab, dest_dir ga ATOMIK joylaydi (forward-only sikl).

    Idle va harakat primitivlari uchun umumiy yadro. Xato → RuntimeError."""
    musetalk.ensure_loaded()
    import torch
    import cv2
    from musetalk.utils.preprocessing import get_landmark_and_bbox
    from musetalk.utils.blending import get_image_prepare_material

    vae = musetalk._vae
    fp = musetalk._fp
    if vae is None or fp is None:
        raise RuntimeError("MuseTalk modellari yuklanmadi (vae/fp yo'q)")

    tmp = dest_dir.parent / (dest_dir.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    full_imgs = tmp / "full_imgs"
    mask_dir = tmp / "mask"
    full_imgs.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)

    n = _video2imgs(str(video), str(full_imgs))
    if n == 0:
        raise RuntimeError("Videodan kadr o'qilmadi")
    img_list = sorted(glob.glob(os.path.join(str(full_imgs), "*.png")))

    coord_list, frame_list = get_landmark_and_bbox(img_list, BBOX_SHIFT)

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
        raise RuntimeError("Videoda yuz aniqlanmadi")

    # Sikl = faqat oldinga (palindromsiz) — idle harakati davriy, primitiv enveloped.
    frame_cycle = list(frame_list)
    coord_cycle = list(coord_list)
    latent_cycle = list(input_latent_list)

    mask_coords = []
    for i, frame in enumerate(frame_cycle):
        cv2.imwrite(os.path.join(str(full_imgs), f"{i:08d}.png"), frame)
        x1, y1, x2, y2 = coord_cycle[i]
        mask, crop_box = get_image_prepare_material(
            frame, [x1, y1, x2, y2], fp=fp, mode=PARSING_MODE)
        cv2.imwrite(os.path.join(str(mask_dir), f"{i:08d}.png"), mask)
        mask_coords.append(crop_box)

    with open(tmp / "coords.pkl", "wb") as f:
        pickle.dump(coord_cycle, f)
    with open(tmp / "mask_coords.pkl", "wb") as f:
        pickle.dump(mask_coords, f)
    torch.save(latent_cycle, str(tmp / "latents.pt"))
    info = {"frames": len(frame_cycle), "bbox_shift": BBOX_SHIFT,
            "extra_margin": extra_margin, "version": "v15"}
    if meta_extra:
        info.update(meta_extra)
    with open(tmp / "avator_info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False)

    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    tmp.rename(dest_dir)
    return len(frame_cycle)


def preprocess_avatar(avatar_id: str) -> str:
    """Avatar idle videosidan asosiy MuseTalk artefakt yasaydi."""
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise RuntimeError("Avatar topilmadi")
    idle = avatar_idle_file(avatar_id)
    if not idle.is_file():
        raise RuntimeError("Idle video topilmadi — avval idle yarating")
    extra_margin = int(av.get("extraMargin", DEFAULT_EXTRA_MARGIN))
    art = avatar_artifact_dir(avatar_id)
    n = _video_to_artifact_dir(str(idle), art, extra_margin,
                               meta_extra={"avatar_id": avatar_id, "kind": "idle"})
    musetalk.invalidate(avatar_id)
    avatar_store.set_ready(avatar_id, True)
    print(f"PREPROCESS-OK ({n} kadr)")
    return str(art)


def preprocess_motion(avatar_id: str, mtype: str) -> str:
    """Harakat primitivi klipidan (motion/<type>.mp4) artefakt yasaydi (2-faza)."""
    if mtype not in MOTION_TYPES:
        raise RuntimeError(f"Noma'lum harakat turi: {mtype}")
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise RuntimeError("Avatar topilmadi")
    clip = avatar_motion_clip(avatar_id, mtype)
    if not clip.is_file():
        raise RuntimeError(f"Harakat klipi topilmadi: {clip}")
    extra_margin = int(av.get("extraMargin", DEFAULT_EXTRA_MARGIN))
    dest = avatar_motion_artifact(avatar_id, mtype)
    n = _video_to_artifact_dir(str(clip), dest, extra_margin,
                               meta_extra={"avatar_id": avatar_id, "kind": "motion",
                                           "motion_type": mtype})
    print(f"MOTION-PREP-OK {mtype} ({n} kadr)")
    return str(dest)


def preprocess_motion_all(avatar_id: str) -> list:
    """Avatar uchun BARCHA mavjud harakat kliplarini preprocess qiladi (bir musetalk
    yuklash). neutral majburiy. Yaratilgan turlar ro'yxatini qaytaradi."""
    musetalk.ensure_loaded()
    done = []
    for mt in MOTION_TYPES:
        if not avatar_motion_clip(avatar_id, mt).is_file():
            print(f"[motion] {mt} klip yo'q — o'tkazildi")
            continue
        preprocess_motion(avatar_id, mt)
        done.append(mt)
    if "neutral" not in done:
        raise RuntimeError("neutral primitiv preprocess qilinmadi (klip yo'qmi?)")
    print(f"ALL-MOTION-PREP-OK ({len(done)}: {','.join(done)})")
    return done


def preprocess_motion_all_subprocess(avatar_id: str) -> list:
    """preprocess_motion_all ni alohida jarayonda (PIL/thread muammosi yo'q)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(MT_DIR), str(BACKEND_DIR)])
    cmd = [sys.executable, "-m", "app.services.preprocess", avatar_id, "--all-motion"]
    proc = subprocess.run(cmd, cwd=str(BACKEND_DIR), capture_output=True,
                          text=True, timeout=PREP_TIMEOUT_SEC, env=env)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-800:]
        raise RuntimeError(f"Harakat preprocessing xato (kod {proc.returncode}): {tail}")
    from app.core.paths import avatar_motion_artifact
    if not (avatar_motion_artifact(avatar_id, "neutral") / "latents.pt").is_file():
        raise RuntimeError("Harakat artefaktlari yaratilmadi (neutral yo'q)")
    return MOTION_TYPES


def preprocess_avatar_subprocess(avatar_id: str) -> str:
    """preprocess_avatar ni ALOHIDA jarayonda (subprocess) ishga tushiradi.

    Sabab: jobs.start() fon thread'ida ishlaydi; PIL/FaceParsing asosiy bo'lmagan
    thread'da 'ImagingCore' xatosini beradi. Toza jarayonning asosiy thread'ida ishonchli."""
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise RuntimeError("Avatar topilmadi")
    if not avatar_idle_file(avatar_id).is_file():
        raise RuntimeError("Idle video topilmadi — avval idle yarating")
    env = os.environ.copy()
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
    # python -m app.services.preprocess <avatar_id> [--motion <type>]
    if len(sys.argv) < 2:
        print("Foydalanish: python -m app.services.preprocess <avatar_id> [--motion <type>]",
              file=sys.stderr)
        sys.exit(2)
    aid = sys.argv[1]
    if len(sys.argv) >= 3 and sys.argv[2] == "--all-motion":
        preprocess_motion_all(aid)
    elif len(sys.argv) >= 4 and sys.argv[2] == "--motion":
        preprocess_motion(aid, sys.argv[3])
    else:
        preprocess_avatar(aid)
