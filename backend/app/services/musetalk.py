"""MuseTalk lip-sync dvigateli — modellarni yuklash + audio→mp4 inference.

Modellar (VAE/UNet/Whisper/FaceParsing) avatardan MUSTAQIL — bir marta yuklanadi.
Avatar artefakti (latents, koordinatalar, full_imgs, mask) esa HAR AVATAR uchun
alohida: avval per-avatar artefakt (data/avatars/<id>/artifact/) qidiriladi, topilmasa
eski madina_lp artefakti (MT_DIR) fallback bo'ladi. Yuklangan artefaktlar keshlanadi.
"""
import glob
import logging
import os
import pickle
import random
import subprocess
import threading
import time
from contextlib import contextmanager

from app.core.paths import (
    MT_DIR, AVATAR_LATENTS, AVATAR_COORDS, AVATAR_MASK_COORD,
    AVATAR_MASK_DIR, AVATAR_IMGS_DIR, VID_OUT_DIR,
    avatar_artifact_paths,
)
from app.core import perf   # yengil/og'ir preset (max_dim cap + batch)

log = logging.getLogger(__name__)

# Og'ir importlarni MODUL yuklanishida (asosiy thread) bajaramiz. diffusers
# lazy-import tizimi bir nechta thread'dan chaqirilsa "object of type 'int' has
# no len()" xatosi beradi — warmup fon thread'i shunga uchragan edi.
try:
    import torch  # noqa: F401
    import diffusers  # noqa: F401
    from diffusers import AutoencoderKL, UNet2DConditionModel  # noqa: F401
    import diffusers.schedulers.scheduling_lms_discrete  # noqa: F401
    # MUHIM: torchvision va musetalk.utils.utils'ni SHU YERDA (modul import — atomik,
    # bir marta) yuklaymiz. Aks holda warmup va foydalanuvchi so'rovi bir vaqtda
    # `from musetalk.utils.utils import datagen` qilsa, torchvision concurrent import
    # poygasiga tushadi ("partially initialized module ... circular import") va model
    # yuklanmaydi. Eager import buni butunlay yo'qotadi.
    import torchvision  # noqa: F401
    from musetalk.utils.utils import datagen, load_all_model  # noqa: F401
except Exception as _imp_err:
    log.warning("eager import ogohlantirish: %s", _imp_err)


def _is_cuda_oom(exc) -> bool:
    """Istisno CUDA xotira yetishmasligi (OOM) ekanini aniqlaydi."""
    try:
        import torch
        if isinstance(exc, torch.cuda.OutOfMemoryError):
            return True
    except Exception:  # noqa: BLE001
        pass
    return "out of memory" in str(exc).lower()


def _reclaim_vram() -> None:
    """OOM'dan keyin keshlangan VRAM'ni bo'shatadi. Aks holda fragmentlangan xotira
    qoladi va KEYINGI so'rovlar ham ketma-ket OOM bo'lib, butun xizmat o'ladi."""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            log.warning("CUDA kesh bo'shatildi (OOM tiklash)")
            log_vram("OOM-tiklashdan keyin", logging.WARNING)
    except Exception as e:  # noqa: BLE001
        log.warning("VRAM bo'shatish xato: %s", e)


def vram_stats() -> dict:
    """Joriy GPU xotira holati (MB). GPU yo'q bo'lsa bo'sh dict. Diagnostika/log uchun."""
    try:
        import torch
        if not torch.cuda.is_available():
            return {}
        free, total = torch.cuda.mem_get_info()
        return {
            "vram_alloc_mb": round(torch.cuda.memory_allocated() / 1048576, 1),
            "vram_reserved_mb": round(torch.cuda.memory_reserved() / 1048576, 1),
            "vram_free_mb": round(free / 1048576, 1),
            "vram_total_mb": round(total / 1048576, 1),
        }
    except Exception:  # noqa: BLE001
        return {}


def log_vram(tag: str = "", level: int = logging.DEBUG) -> None:
    """VRAM holatini strukturali loglaydi (tag bilan). OOM tahlili uchun bebaho.
    Standart DEBUG — RT_PROFILE yoki LOG_LEVEL=DEBUG da ko'rinadi."""
    stats = vram_stats()
    if stats:
        log.log(level, "VRAM %s: alloc=%.0fMB free=%.0fMB", tag,
                stats["vram_alloc_mb"], stats["vram_free_mb"], extra=stats)


# ── Global model holatlari (avatardan mustaqil) ──
_loaded = False
_lock = threading.Lock()
_vae = _unet = _pe = _whisper = _audio_processor = _fp = None
_timesteps = _weight_dtype = _device = None

# Per-avatar artefakt keshi: key → {latents, coords, mask_coords, frames, masks}
_avatars = {}
_avatars_lock = threading.Lock()
_LEGACY_KEY = "_legacy_madina_lp"

# ── GPU bandwidth cheklovi (bir nechta foydalanuvchi) ──
# Bir vaqtda nechta inference GPU'da yurishi mumkin. Cheklov bo'lmasa, ko'p user
# bir vaqtda kelsa VRAM portlaydi va hammaga keskin sekinlashadi. Generatsiya
# BURST-li (user gapiradi → ~2s video → uzoq tinglaydi) bo'lgani uchun bitta GPU
# bir nechta foydalanuvchini navbat bilan bemalol uddalaydi. Slot FAQAT haqiqiy
# GPU hisoblash davomida ushlanadi (ffmpeg/tarmoq slotni band qilmaydi).
# Sozlash: RT_GPU_SLOTS (default 2). RTX 5090 32GB → 2 inference bemalol sig'adi.
_GPU_SLOTS = max(1, int(os.environ.get("RT_GPU_SLOTS", "2")))
_gpu_sem = threading.BoundedSemaphore(_GPU_SLOTS)

# Inference batch hajmi. Kattaroq batch → kamroq kernel launch → GPU to'liqroq
# band → tezroq (sifat O'ZGARMAYDI — faqat guruhlash). RTX 5090 32GB kattasini
# ko'taradi. Sozlash: MT_BATCH (default 16).
_BATCH = max(1, int(os.environ.get("MT_BATCH", "16")))

# Og'iz tiniqligi: MuseTalk og'izni 256x256'da yaratadi, keyin yuz o'lchamiga
# kattalashtiriladi → yumshaydi. Yengil unsharp (nimqilich) + sifatli upscale
# (INTER_CUBIC) buni qisman qoplaydi (tezlikka deyarli ta'sirsiz). 0 = o'chiq.
# Halol: tub yechim emas (256 cheklovi), lekin bepul tiniqlik beradi.
_SHARPEN = max(0.0, float(os.environ.get("RT_SHARPEN", "0.65")))

# Lab↔ovoz vaqt mosligi: doimiy ofset (sekund). MuseTalk drift bermaydi (kadr
# soni = audio×fps aniq), lekin lab biroz oldinda/orqada tuyulsa shu bilan nudge.
# +qiymat → ovoz KECHIKADI (lab oldin harakatlansa); -qiymat → ovoz OLDINGA.
_AUDIO_OFFSET = float(os.environ.get("RT_AUDIO_OFFSET", "0"))


def _audio_offset_args():
    """ffmpeg audio kirishidan oldin -itsoffset (0 bo'lsa bo'sh)."""
    return ["-itsoffset", f"{_AUDIO_OFFSET}"] if _AUDIO_OFFSET else []


def _sharpen_region(img, amount):
    """Yengil unsharp mask (cv2 GIL'ni bo'shatadi → arzon). amount<=0 → o'zgarishsiz."""
    if amount <= 0:
        return img
    import cv2
    blur = cv2.GaussianBlur(img, (0, 0), 1.0)
    return cv2.addWeighted(img, 1.0 + amount, blur, -amount, 0)


def _mouth_correct(rf, bbox, mask_crop_box, dx=None, dy=None, rot=None):
    """QO'LDA STATIK OG'IZ TUZATISH (avatarga xos qiyshiqlikni to'g'rilash).
    dx/dy — og'iz patch'ini piksel bo'yicha siljitadi; rot — gradusda buradi.
    0/0/0 → tegmaydi. Qiymatlar env (RT_MOUTH_DX/DY/ROT) yoki argument bilan.
    Eslatma: siljitish/burilish JOYlashuvni tuzatadi — model chizgan SHAKLni emas."""
    dx = int(os.environ.get("RT_MOUTH_DX", "0")) if dx is None else int(dx)
    dy = int(os.environ.get("RT_MOUTH_DY", "0")) if dy is None else int(dy)
    rot = float(os.environ.get("RT_MOUTH_ROT", "0")) if rot is None else float(rot)
    if not (dx or dy or rot):
        return rf, bbox, mask_crop_box
    import cv2
    if rot:
        h, w = rf.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), rot, 1.0)
        rf = cv2.warpAffine(rf, M, (w, h), flags=cv2.INTER_CUBIC,
                            borderMode=cv2.BORDER_REPLICATE)
    if dx or dy:
        bbox = [bbox[0] + dx, bbox[1] + dy, bbox[2] + dx, bbox[3] + dy]
        mask_crop_box = [mask_crop_box[0] + dx, mask_crop_box[1] + dy,
                         mask_crop_box[2] + dx, mask_crop_box[3] + dy]
    return rf, bbox, mask_crop_box


def _avatar_mouth_correction(avatar_id):
    """Avatarga xos og'iz tuzatishini (mouthDx/mouthDy/mouthRotate) qaytaradi.
    Kalit bo'lmasa None → _mouth_correct env'ga tushadi (test uchun). Xato → (None,)*3."""
    try:
        from app.services import avatar_store
        av = avatar_store.get_avatar(avatar_id) or {}
    except Exception:  # noqa: BLE001
        av = {}
    return (av.get("mouthDx"), av.get("mouthDy"), av.get("mouthRotate"))


# Harakat takrorlanmasin: har generatsiya sikl kadrlarini TASODIFIY nuqtadan
# boshlaydi → har javob boshqa bosh pozasi/harakatdan ochiladi. Barcha massivlar
# (latent/coord/mask/frame) BIR XIL ofsetga aylantiriladi → moslik buzilmaydi.
# RT_VARY_MOTION=0 → o'chiq (har doim 0-kadr).
_VARY_MOTION = os.environ.get("RT_VARY_MOTION", "1") != "0"


def _rotate(seq, start):
    """Ro'yxatni `start` nuqtadan aylantiradi (yangi ro'yxat — kesh buzilmaydi)."""
    if start <= 0:
        return seq
    return seq[start:] + seq[:start]


def _cycle_start(n):
    """Sikl uchun tasodifiy boshlanish indeksi (RT_VARY_MOTION o'chiq bo'lsa 0)."""
    if not _VARY_MOTION or n <= 1:
        return 0
    return random.randint(0, n - 1)


@contextmanager
def _gpu_slot(tag: str = ""):
    """GPU inference uchun bitta slot egallaydi (bandwidthni cheklaydi)."""
    t0 = time.time()
    _gpu_sem.acquire()
    waited = time.time() - t0
    if waited > 0.05:
        log.info("GPU navbatda kutildi %.2fs (%s)", waited, tag,
                 extra={"gpu_wait_s": round(waited, 2), "tag": tag})
    try:
        yield
    finally:
        _gpu_sem.release()


def gpu_slots() -> int:
    """Sozlangan bir vaqtdagi GPU slot soni (kuzatuv/test uchun)."""
    return _GPU_SLOTS


# ── Video kodlovchi tanlash (NVENC GPU-kodlash → CPU ffmpeg bottleneck'ini yo'qotadi) ──
_ENCODER = None


def _encoder_name() -> str:
    """h264_nvenc (GPU) mavjud bo'lsa shuni, aks holda libx264 (CPU) tanlaydi.
    Bir marta aniqlanib keshlanadi. Majburlash: VIDEO_ENCODER env."""
    global _ENCODER
    if _ENCODER is not None:
        return _ENCODER
    forced = os.environ.get("VIDEO_ENCODER")
    if forced:
        _ENCODER = forced
        return _ENCODER
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                             capture_output=True, text=True, timeout=10).stdout
        _ENCODER = "h264_nvenc" if "h264_nvenc" in out else "libx264"
    except Exception:  # noqa: BLE001
        _ENCODER = "libx264"
    log.info("Video kodlovchi: %s", _ENCODER, extra={"encoder": _ENCODER})
    return _ENCODER


def _venc_args(fps: int, hd: bool = False, low_latency: bool = False) -> list:
    """ffmpeg video kodlash argumentlari. hd=True (offline Studio) → yuqoriroq sifat
    (crf 16 + sekinroq preset; NVENC cq 17/p7). hd=False (real-time) → tez (crf 18).
    NVENC ~5x tez, lekin x264 (slow) biroz tiniqroq — offline'da x264 afzal.

    low_latency=True (real-time OQIM) → enkoder buferini MINIMALLASHTIRADI:
    B-kadrlar yo'q (-bf 0, qayta tartiblash buferi yo'q), lookahead yo'q, keyframe
    tez-tez (-g ~0.25s) → birinchi fragment DARROV chiqadi.

    Realtime DOIM libx264 (NVENC EMAS): oqim uzilganda ffmpeg SIGKILL bilan
    o'ldiriladi — NVENC sessiyasi qattiq kill'dan keyin drayverda chala qolib
    KEYINGI enkoderlarni futex'da abadiy osiltirishi kuzatildi (jonli xato:
    ffmpeg'lar futex_wait'da, producer pipe_write'da qotib butun video o'lardi).
    792x960@25fps x264 ultrafast'ga arzimas yuk; offline HD render NVENC'da qoladi."""
    enc = _encoder_name()
    g_ll = max(2, int(fps) // 4)   # ~0.25s keyframe oralig'i (tez birinchi fragment)
    if low_latency:
        return ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-crf", "20", "-bf", "0", "-pix_fmt", "yuv420p", "-g", str(g_ll)]
    if enc == "h264_nvenc":
        cq, pre = ("17", "p7") if hd else ("20", "p5")
        return ["-c:v", "h264_nvenc", "-preset", pre, "-tune", "hq",
                "-rc", "vbr", "-cq", cq, "-b:v", "0",
                "-pix_fmt", "yuv420p", "-g", str(fps)]
    crf, pre = ("16", "slow") if hd else ("18", "veryfast")
    return ["-c:v", "libx264", "-preset", pre, "-crf", crf,
            "-pix_fmt", "yuv420p", "-g", str(fps)]


def is_loaded() -> bool:
    return _loaded


def _load():
    """MuseTalk asosiy modellarini yuklash (bir martalik, avatardan mustaqil)."""
    global _loaded, _vae, _unet, _pe, _whisper, _audio_processor, _fp
    global _timesteps, _weight_dtype, _device

    if _loaded:
        return

    import torch
    from transformers import WhisperModel
    from musetalk.utils.face_parsing import FaceParsing
    from musetalk.utils.utils import load_all_model
    from musetalk.utils.audio_processor import AudioProcessor

    t0 = time.time()
    log.info("Modellar yuklanmoqda...")

    # MuseTalk nisbiy yo'llardan foydalanadi (models/sd-vae, face-parse, ...)
    os.chdir(str(MT_DIR))

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _timesteps = torch.tensor([0], device=_device)

    _vae, _unet, _pe = load_all_model(
        unet_model_path=str(MT_DIR / "models/musetalkV15/unet.pth"),
        vae_type="sd-vae",
        unet_config=str(MT_DIR / "models/musetalkV15/musetalk.json"),
        device=_device,
    )

    # FP16 — Blackwell uchun
    _pe = _pe.half().to(_device)
    _vae.vae = _vae.vae.half().to(_device)
    _unet.model = _unet.model.half().to(_device)

    _audio_processor = AudioProcessor(feature_extractor_path=str(MT_DIR / "models/whisper"))
    _weight_dtype = _unet.model.dtype
    _whisper = WhisperModel.from_pretrained(str(MT_DIR / "models/whisper"))
    _whisper = _whisper.to(device=_device, dtype=_weight_dtype).eval()
    _whisper.requires_grad_(False)

    _fp = FaceParsing(left_cheek_width=90, right_cheek_width=90)

    # torch.compile — SINOVDAN O'TKAZILDI: bu workload (MuseTalk UNet FP16, batch=8)
    # uchun tezlik DEYARLI O'ZGARMADI (~5%), lekin birinchi inference ~7 daqiqa
    # kompilyatsiya qildi (warmup'ni buzadi). Shu sabab STANDART BO'YICHA O'CHIQ.
    # Boshqa GPU/kelajak uchun opt-in: ENABLE_COMPILE=1. (Haqiqiy tezlik — TensorRT.)
    if os.environ.get("ENABLE_COMPILE") == "1":
        try:
            _unet.model = torch.compile(_unet.model, dynamic=True)
            _vae.vae = torch.compile(_vae.vae, dynamic=True)
            log.info("torch.compile yoqildi (UNet + VAE)")
        except Exception as e:  # noqa: BLE001
            log.warning("torch.compile o'tkazib yuborildi: %s", e)

    _loaded = True
    log.info("Asosiy modellar tayyor: %.1fs", time.time() - t0,
             extra={"event": "models_loaded", "dur_s": round(time.time() - t0, 1)})
    log_vram("modellar yuklandi", logging.INFO)


def ensure_loaded():
    if _loaded:
        return
    with _lock:
        if not _loaded:
            _load()


def _resolve_artifact(avatar_id):
    """(kesh_kaliti, yo'llar_dict) qaytaradi. Avval per-avatar artefakt, keyin legacy fallback.

    Topilmasa (None, None). Yangi avatar o'z artefaktiga ega bo'lguncha eski
    madina_lp yuzini ulashadi (joriy demo xulqi saqlanadi)."""
    if avatar_id:
        ap = avatar_artifact_paths(avatar_id)
        if ap["latents"].exists():
            return avatar_id, ap
    if AVATAR_LATENTS.exists():
        return _LEGACY_KEY, {
            "latents": AVATAR_LATENTS, "coords": AVATAR_COORDS,
            "mask_coords": AVATAR_MASK_COORD,
            "mask_dir": AVATAR_MASK_DIR, "imgs_dir": AVATAR_IMGS_DIR,
        }
    return None, None


def _load_artifact_from_paths(paths) -> dict:
    """Berilgan yo'llardan artefakt massivlarini yuklaydi (latents/coords/mask/frames).
    PNG'lar parallel o'qiladi (cv2.imread GIL'ni bo'shatadi → tez)."""
    import torch
    import cv2
    from concurrent.futures import ThreadPoolExecutor

    latents = torch.load(str(paths["latents"]))
    with open(paths["coords"], "rb") as f:
        coords = pickle.load(f)
    with open(paths["mask_coords"], "rb") as f:
        mask_coords = pickle.load(f)
    img_paths = sorted(glob.glob(str(paths["imgs_dir"] / "*.png")))
    mask_paths = sorted(glob.glob(str(paths["mask_dir"] / "*.png")))
    with ThreadPoolExecutor(max_workers=16) as ex:
        frames = list(ex.map(cv2.imread, img_paths))
        masks = list(ex.map(cv2.imread, mask_paths))
    return {"latents": latents, "coords": coords, "mask_coords": mask_coords,
            "frames": frames, "masks": masks}


def use_max_dim(avatar) -> int:
    """Avatar ISHLATISH (output) rezolyutsiyasi: 1280 (tez/720p) yoki 1920 (sifat/1080p).
    avatar.json 'maxDim' bilan boshqariladi — BIR ZUMDA o'zgaradi, qayta qurish SHART
    EMAS. Artefakt har doim 1920 bazada quriladi; bu yerda kerakli o'lchamga
    KICHRAYTIRILADI (latent'lar 256 og'iz — rezolyutsiyadan mustaqil)."""
    try:
        v = int((avatar or {}).get("maxDim", 1280))
    except (TypeError, ValueError):
        v = 1280
    if v not in (1280, 1920):
        v = 1280
    # Yengil/og'ir preset: light rejimda resolution past darajaga cheklanadi
    # (zaif GPU / DGX Spark uchun yengillik). heavy'da avatar qiymati saqlanadi.
    return min(v, perf.max_dim_cap())


def rt_max_dim(avatar) -> int:
    """REAL-TIME (jonli suhbat) chiqish rezolyutsiyasi — studio'dan PAST bo'ladi
    (tezlik uchun; jonli video kichik ekranda ko'rinadi, 256 og'iz latent'i
    rezolyutsiyadan mustaqil, faqat blend+encode kadr o'lchamiga bog'liq).
    RT_MAX_DIM env (default 768) bilan cheklanadi; studio use_max_dim() to'liq
    sifatда qoladi. RT_MAX_DIM=0 → real-time ham to'liq (eski xatti-harakat)."""
    base = use_max_dim(avatar)
    try:
        cap = int(os.environ.get("RT_MAX_DIM", "960"))
    except (TypeError, ValueError):
        cap = 960
    return min(base, cap) if cap and cap > 0 else base


def _target_ratio(art, max_dim) -> float:
    """Artefakt kadrining uzun tomonini max_dim'ga keltirish nisbati (<=1.0).
    max_dim yo'q yoki kadr allaqachon kichik bo'lsa 1.0 (kichraytirish yo'q;
    UPSCALE qilinmaydi — 1280 bazadan 1080 yasab bo'lmaydi)."""
    frames = art.get("frames") or []
    if not max_dim or not frames:
        return 1.0
    h, w = frames[0].shape[:2]
    long = max(h, w)
    if long <= int(max_dim):
        return 1.0
    return int(max_dim) / float(long)


def _downscale_artifact(art, ratio) -> dict:
    """Artefaktni `ratio` (<1) bo'yicha kichraytiradi — full_imgs/mask rasm o'lchami,
    coords/mask_coords koordinatalari proporsional masshtablanadi. LATENT'lar (256
    og'iz) O'ZGARMAYDI. Og'iz inference paytida 256'dan kichikroq bbox'ga tushadi
    → tabiiy tiniqlik + tezroq composite (native-720'ga teng natija)."""
    import cv2
    if ratio >= 0.999:
        return art
    keys = ("latents", "coords", "mask_coords", "frames", "masks")
    n = len(art["frames"])
    frames, masks, coords, mcoords = [], [], [], []
    for i in range(n):
        f = art["frames"][i]
        h, w = f.shape[:2]
        nw, nh = max(2, int(round(w * ratio))), max(2, int(round(h * ratio)))
        frames.append(cv2.resize(f, (nw, nh), interpolation=cv2.INTER_AREA))
        nc = [int(round(float(v) * ratio)) for v in art["coords"][i]]
        nmc = [int(round(float(v) * ratio)) for v in art["mask_coords"][i]]
        coords.append(nc)
        mcoords.append(nmc)
        # Mask o'lchami crop_box (mask_coords) o'lchamiga AYNAN teng bo'lishi shart
        # (PIL paste mask buni talab qiladi) — masshtablangan crop_box'dan hisoblaymiz.
        mw = max(1, nmc[2] - nmc[0])
        mh = max(1, nmc[3] - nmc[1])
        masks.append(cv2.resize(art["masks"][i], (mw, mh), interpolation=cv2.INTER_AREA))
    return {"latents": art["latents"], "coords": coords, "mask_coords": mcoords,
            "frames": frames, "masks": masks}


def _get_artifact(avatar_id, max_dim=None):
    """Avatar artefaktini (keshlangan) qaytaradi. max_dim berilsa — o'sha output
    rezolyutsiyasiga kichraytirilgan variant (alohida keshlanadi). Topilmasa RuntimeError."""
    key, paths = _resolve_artifact(avatar_id)
    if key is None:
        raise RuntimeError(
            "Avatar artefakti topilmadi — avval MuseTalk preprocessing bajaring"
        )
    with _avatars_lock:
        native = _avatars.get(key)
    if native is None:
        t1 = time.time()
        native = _load_artifact_from_paths(paths)
        with _avatars_lock:
            _avatars[key] = native
        log.info("Artefakt '%s': %d kadr (%.1fs)", key, len(native['frames']), time.time() - t1,
                 extra={"avatar": key, "frames": len(native['frames'])})
    if not max_dim:
        return native
    ratio = _target_ratio(native, max_dim)
    if ratio >= 0.999:
        return native   # baza allaqachon shu o'lchamda (yoki kichikroq)
    skey = (key, int(max_dim))
    with _avatars_lock:
        scaled = _avatars.get(skey)
    if scaled is not None:
        return scaled
    t2 = time.time()
    scaled = _downscale_artifact(native, ratio)
    with _avatars_lock:
        _avatars[skey] = scaled
    log.info("Artefakt '%s' @%s (%.3fx): %d kadr (%.1fs)", key, max_dim, ratio,
             len(scaled['frames']), time.time() - t2,
             extra={"avatar": key, "max_dim": max_dim, "ratio": round(ratio, 3)})
    return scaled


# ── 2-faza: harakat primitivlari (nod/tilt/.../neutral) keshi + yig'uvchi ──
_motion = {}   # (avatar_id, mtype) → artefakt


def _get_motion_artifact(avatar_id, mtype):
    """Harakat primitivi artefaktini (keshlangan) yuklaydi (motion/<type>/)."""
    key = (avatar_id, mtype)
    with _avatars_lock:
        c = _motion.get(key)
    if c is not None:
        return c
    from app.core.paths import avatar_motion_artifact
    d = avatar_motion_artifact(avatar_id, mtype)
    if not (d / "latents.pt").is_file():
        raise RuntimeError(f"Harakat artefakti yo'q: {mtype} (avval qayta quring)")
    paths = {"latents": d / "latents.pt", "coords": d / "coords.pkl",
             "mask_coords": d / "mask_coords.pkl", "imgs_dir": d / "full_imgs",
             "mask_dir": d / "mask"}
    art = _load_artifact_from_paths(paths)
    with _avatars_lock:
        _motion[key] = art
    return art


def assemble_motion_artifact(avatar_id, sequence) -> dict:
    """sequence = harakat turlari ro'yxati (masalan ['neutral','nod','neutral']) →
    ularning massivlarini KETMA-KET ulaydi (bitta assembled artefakt). Har primitiv
    neytralda boshlanib-tugagani uchun chegaralar silliq."""
    L, C, MC, F, M = [], [], [], [], []
    for mt in sequence:
        a = _get_motion_artifact(avatar_id, mt)
        L += list(a["latents"]); C += list(a["coords"]); MC += list(a["mask_coords"])
        F += list(a["frames"]); M += list(a["masks"])
    return {"latents": L, "coords": C, "mask_coords": MC, "frames": F, "masks": M}


def _resample_artifact(art, k):
    """Artefakt massivlaridan k kadr tanlaydi (silliq qayta namuna). speed nazorati:
    primitivni kamroq kadrga (tez) yoki ko'proq kadrga (sekin) cho'zish."""
    n = len(art["frames"])
    if k <= 0 or n == 0:
        return {kk: [] for kk in ("latents", "coords", "mask_coords", "frames", "masks")}
    if n == k:
        idxs = range(n)
    else:
        idxs = [min(n - 1, round(i * (n - 1) / max(1, k - 1))) for i in range(k)]
    return {kk: [art[kk][j] for j in idxs]
            for kk in ("latents", "coords", "mask_coords", "frames", "masks")}


def _natural_fill(art, k):
    """Neytral idle'ni 1x (tabiiy) tempda k kadrga to'ldiradi — klipni LOOP qiladi,
    SIQMAYDI. Neytral klip chetlarda neytral (enveloped) bo'lgani uchun loop silliq.
    Resample (siqish) neytralni tezlashtirib, video boshida 'birdaniga tez harakat'
    effektini berardi — buni oldini oladi."""
    n = len(art["frames"])
    keys = ("latents", "coords", "mask_coords", "frames", "masks")
    if k <= 0 or n == 0:
        return {kk: [] for kk in keys}
    idxs = [i % n for i in range(k)]
    return {kk: [art[kk][j] for j in idxs] for kk in keys}


def assemble_motion_timeline(avatar_id, units) -> dict:
    """units = [(mtype, n_frames), ...] → bosh-harakat timeline'i (audio bilan kadr-aniq).
    NEYTRAL → tabiiy tempda loop (siqilmaydi); MOTION primitivlar → resample (gesture
    davomiyligini segmentga moslash uchun tezlik nazorati). Chegaralar neytral."""
    L, C, MC, F, M = [], [], [], [], []
    for mt, k in units:
        if k <= 0:
            continue
        a = _get_motion_artifact(avatar_id, mt)
        r = _natural_fill(a, int(k)) if mt == "neutral" else _resample_artifact(a, int(k))
        L += r["latents"]; C += r["coords"]; MC += r["mask_coords"]
        F += r["frames"]; M += r["masks"]
    return {"latents": L, "coords": C, "mask_coords": MC, "frames": F, "masks": M}


def has_motion(avatar_id, mtype="neutral") -> bool:
    """Avatar uchun harakat primitivi artefakti mavjudmi."""
    from app.core.paths import avatar_motion_artifact
    return (avatar_motion_artifact(avatar_id, mtype) / "latents.pt").is_file()


def invalidate(avatar_id):
    """Avatar artefakt keshini bo'shatadi (preprocessing qayta yasalgach) —
    native + barcha kichraytirilgan (max_dim) variantlar."""
    with _avatars_lock:
        for k in [k for k in _avatars
                  if k == avatar_id or (isinstance(k, tuple) and k[0] == avatar_id)]:
            _avatars.pop(k, None)
        for k in [k for k in _motion if k[0] == avatar_id]:
            _motion.pop(k, None)


def warmup():
    """Birinchi inference sekin — startupda bir marta isitib qo'yish."""
    ensure_loaded()
    key, _ = _resolve_artifact(None)
    if key is None:
        log.info("Warmup o'tkazib yuborildi — hech qanday artefakt yo'q")
        return
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
        "-t", "0.5", "-ar", "16000", "-ac", "1", tmp.name,
    ], capture_output=True)
    t = time.time()
    # Inference kernellarini isitamiz (cudnn autotune — batch va stream bir xil kernellar).
    musetalk_infer(tmp.name, str(VID_OUT_DIR / "_warmup.mp4"))
    for p in (tmp.name, str(VID_OUT_DIR / "_warmup.mp4")):
        try:
            os.remove(p)
        except Exception:
            pass
    log.info("Warmup: %.1fs", time.time() - t, extra={"event": "warmup_done"})


def warmup_stream(avatar_id: str):
    """REAL-TIME stream yo'lini isitadi (low-latency nvenc enkoder + stream oqim
    birinchi JONLI so'rovda JIT bo'lmasin). Kichik jim wav'ni queue orqali o'tkazib,
    chiqishni tashlaymiz. Xato → jim o'tkazib yuboriladi (warmup majburiy emas)."""
    import queue as _q
    import tempfile
    av = None
    try:
        from app.services import avatar_store
        av = avatar_store.get_avatar(avatar_id)
    except Exception:  # noqa: BLE001
        pass
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
            "-t", "0.4", "-ar", "16000", "-ac", "1", tmp.name,
        ], capture_output=True)
        q: _q.Queue = _q.Queue()
        q.put(tmp.name)
        q.put(None)
        t = time.time()
        for _chunk in musetalk_infer_stream_queue(
                q, fps=25, avatar_id=avatar_id, start_frame=0,
                max_dim=rt_max_dim(av)):
            pass
        log.info("Stream warmup: %.1fs", time.time() - t,
                 extra={"event": "stream_warm"})
    except Exception as e:  # noqa: BLE001
        log.warning("stream warmup xato: %s", e)
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


def preload_artifact(avatar_id: str, max_dim=None) -> bool:
    """Avatar artefaktini (200 kadr/mask PNG) keshга oldindan yuklaydi.

    Birinchi so'rov sekin bo'lmasligi uchun startupda chaqiriladi — aks holda
    foydalanuvchining BIRINCHI savolida artefakt diskdan (sekin DrvFs) o'qiladi.
    max_dim berilsa — ishlatiladigan (kichraytirilgan) variant ham isitiladi.
    """
    try:
        ensure_loaded()
        _get_artifact(avatar_id, max_dim)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("preload '%s' ogohlantirish: %s", avatar_id, e)
        return False


def musetalk_infer(wav_path: str, out_mp4: str, fps: int = 25, avatar_id: str = None,
                   hd: bool = False, artifact: dict = None, max_dim=None) -> bool:
    """To'liq video fayl (offline). hd=True → kuchliroq tiniqlik (Video Studiya).
    max_dim — chiqish rezolyutsiyasi (1280/1920); artefakt shunga kichraytiriladi.
    artifact berilsa — o'sha (assembled, bosh harakatli) artefakt ishlatiladi
    (avatar_id keshidan emas) va kerak bo'lsa o'sha ham kichraytiriladi."""
    import torch
    import cv2
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor
    from musetalk.utils.utils import datagen
    from musetalk.utils.blending import get_image_blending

    ensure_loaded()
    # HD'da GFPGAN tiniqlikni o'zi beradi → qo'shimcha sharpen O'CHIRILADI (sharpen
    # 256→kattalashgan og'izdagi shovqinni kuchaytirib, lab "qaltirashi"ni keltirardi).
    _hd_sharpen = 0.0 if hd else _SHARPEN
    _prof = os.environ.get("RT_PROFILE") == "1"
    _pt = time.time()

    def _lap(name):
        nonlocal _pt
        if _prof:
            import torch as _t
            _t.cuda.synchronize()
            log.debug("[PROFILE] %s: %.3fs", name, time.time() - _pt)
            _pt = time.time()

    try:
        # artifact berilsa (assembled, bosh harakatli) — aylantirmaymiz (tartib muhim).
        if artifact is not None:
            art = artifact
            if max_dim:
                _r = _target_ratio(art, max_dim)
                if _r < 0.999:
                    art = _downscale_artifact(art, _r)
        else:
            art = _get_artifact(avatar_id, max_dim)
        _start = 0 if artifact is not None else _cycle_start(len(art["frames"]))
        _input_latent_list_cycle = _rotate(art["latents"], _start)
        _coord_list_cycle = _rotate(art["coords"], _start)
        _mask_coords_list_cycle = _rotate(art["mask_coords"], _start)
        _frame_list_cycle = _rotate(art["frames"], _start)
        _mask_list_cycle = _rotate(art["masks"], _start)
        _lap("artefakt")

        # 1. Whisper audio xususiyatlari
        whisper_input_features, librosa_length = _audio_processor.get_audio_feature(
            wav_path, weight_dtype=_weight_dtype
        )
        whisper_chunks = _audio_processor.get_whisper_chunk(
            whisper_input_features, _device, _weight_dtype, _whisper, librosa_length,
            fps=fps, audio_padding_length_left=2, audio_padding_length_right=2,
        )
        video_num = len(whisper_chunks)
        _lap("whisper")

        # 2. Batch inference (GPU slot bilan cheklangan — multi-user xavfsizligi)
        batch_size = perf.batch_size()
        gen = datagen(whisper_chunks, _input_latent_list_cycle, batch_size)
        res_frame_list = []
        with _gpu_slot("infer"), torch.inference_mode():
            for whisper_batch, latent_batch in gen:
                audio_feature_batch = _pe(whisper_batch.to(_device))
                latent_batch = latent_batch.to(device=_device, dtype=_unet.model.dtype)
                pred_latents = _unet.model(
                    latent_batch, _timesteps, encoder_hidden_states=audio_feature_batch,
                ).sample
                pred_latents = pred_latents.to(device=_device, dtype=_vae.vae.dtype)
                recon = _vae.decode_latents(pred_latents)
                for res_frame in recon:
                    res_frame_list.append(res_frame)
        _lap("GPU (UNet+VAE)")

        # 2.5 TEMPORAL SILLIQLASH (lab titrashini kamaytirish). MuseTalk har og'iz
        #     kadrini MUSTAQIL yaratadi → kadrlararo mayda jitter ("qaltirash").
        #     Yengil EMA: kadr = (1-a)*joriy + a*oldingi → yuqori-chastotali titrash
        #     damp bo'ladi, lab harakati saqlanadi. a (RT_LIP_SMOOTH) 0..0.6;
        #     katta = tinchroq lekin sal laggy. 0 = o'chiq.
        _ls = max(0.0, min(0.6, float(os.environ.get("RT_LIP_SMOOTH", "0.35"))))
        if _ls > 0 and len(res_frame_list) > 1:
            prev = res_frame_list[0].astype(np.float32)
            for _i in range(1, len(res_frame_list)):
                cur = res_frame_list[_i].astype(np.float32)
                prev = _ls * prev + (1.0 - _ls) * cur
                res_frame_list[_i] = prev.copy()
            _lap("temporal smooth")

        # 3. To'liq kadrga composite (parallel)
        n_total = min(len(res_frame_list), video_num)
        _mcorr = _avatar_mouth_correction(avatar_id)

        def _composite_one(idx):
            cycle_idx = idx % len(_frame_list_cycle)
            bbox = _coord_list_cycle[cycle_idx]
            ori_frame = _frame_list_cycle[cycle_idx].copy()
            x1, y1, x2, y2 = bbox
            try:
                rf = cv2.resize(res_frame_list[idx].astype(np.uint8), (x2 - x1, y2 - y1),
                                interpolation=cv2.INTER_LANCZOS4)
                rf = _sharpen_region(rf, _hd_sharpen)
            except Exception:
                return None
            mask = _mask_list_cycle[cycle_idx]
            mask_crop_box = _mask_coords_list_cycle[cycle_idx]
            rf, bbox, mask_crop_box = _mouth_correct(rf, list(bbox), list(mask_crop_box), *_mcorr)
            return get_image_blending(ori_frame, rf, bbox, mask, mask_crop_box)

        with ThreadPoolExecutor(max_workers=12) as ex:
            out_frames = [f for f in ex.map(_composite_one, range(n_total)) if f is not None]
        _lap(f"composite ({n_total} kadr)")

        # Oxirgi 3 kadrni kesish (audio chetidagi g'alati lab)
        if len(out_frames) > 3:
            out_frames = out_frames[:-3]
        if not out_frames:
            return False

        # Yumshoq yopilish: oxirgi nutq kadridan idle (yopiq og'iz) kadriga crossfade.
        n_tail = 7
        last_frame = out_frames[-1]
        base_idx = len(out_frames)
        for k in range(1, n_tail + 1):
            idle_idx = (base_idx + k) % len(_frame_list_cycle)
            idle_frame = _frame_list_cycle[idle_idx]
            alpha = k / (n_tail + 1)
            out_frames.append(
                cv2.addWeighted(last_frame, 1.0 - alpha, idle_frame, alpha, 0)
            )

        # 3.5 HD: GFPGAN yuz tiklash (GPU) — 256 yumshoqligini qoplab, 512 tiniqlik.
        #     Faqat hd=True (offline Studio); xato/vazn yo'q bo'lsa jimgina o'tkaziladi.
        if hd:
            try:
                from app.services import enhance
                if enhance.available():
                    with _gpu_slot("enhance"):
                        # blend 0.6: tiklangan+asl aralashmasi — har-kadr flicker (lab
                        # qaltirashi)ni kamaytiradi, tiniqlikni saqlab.
                        out_frames = [enhance.restore_frame(f, blend=0.6) for f in out_frames]
                    _lap("GFPGAN restore")
            except Exception as e:  # noqa: BLE001
                log.warning("GFPGAN o'tkazildi: %s", e)

        # 4. ffmpeg STDIN orqali mp4
        h, w = out_frames[0].shape[:2]
        proc = subprocess.Popen([
            "ffmpeg", "-y", "-v", "warning",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps),
            "-i", "-", *_audio_offset_args(), "-i", wav_path,
            *_venc_args(fps, hd=hd),
            "-af", "apad", "-c:a", "aac", "-shortest", out_mp4,
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for frame in out_frames:
                proc.stdin.write(frame.astype(np.uint8).tobytes())
            # communicate(): stdin yopiladi, stderr O'QILADI (pipe deadlock yo'q), kutadi.
            _, err = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            log.error("ffmpeg kodlash timeout (out=%s)", out_mp4)
            return False
        except Exception as e:  # noqa: BLE001
            proc.kill()
            log.error("ffmpeg kodlash xato: %s", e)
            return False
        if proc.returncode != 0:
            tail = (err or b"").decode("utf-8", "replace").strip()[-800:]
            log.error("ffmpeg kodlash muvaffaqiyatsiz (rc=%s): %s", proc.returncode, tail)
            return False
        _lap("ffmpeg encode")
        if not os.path.exists(out_mp4):
            log.error("ffmpeg tugadi-yu, natija fayli yo'q: %s", out_mp4)
            return False
        return True

    except Exception as e:
        if _is_cuda_oom(e):
            _reclaim_vram()
            log.error("MuseTalk inference GPU xotira yetishmadi (OOM): %s", e)
        else:
            log.error("MuseTalk inference xato: %s", e, exc_info=True)
        return False


def musetalk_infer_stream(wav_path: str, fps: int = 25, avatar_id: str = None,
                          start_frame=None, max_dim=None):
    """STREAMING variant: kadrlarni generatsiya paytida fragmented-mp4 bayt
    bo'laklari sifatida yieldlaydi (eski musetalk_infer'ga TEGILMAYDI — additiv).

    start_frame: artefakt siklining boshlanish kadri (KADR-SINXRON HANDOFF).
      Frontend jonli idle videosi qaysi kadrda turganini yuboradi → javob aynan
      shu pozadan boshlanadi → idle→javob o'tishida bosh/ko'z SAKRAMAYDI.
      None bo'lsa tasodifiy (RT_VARY_MOTION) — eski xulq.

    ffmpeg fragmented mp4 (frag_keyframe+empty_moov) — brauzer progressive o'ynaydi.
    """
    import torch
    import cv2
    import numpy as np
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from musetalk.utils.utils import datagen
    from musetalk.utils.blending import get_image_blending

    ensure_loaded()
    art = _get_artifact(avatar_id, max_dim)
    # Sikl boshlanishi: frontend bergan kadr (handoff) yoki tasodifiy.
    _n_cycle = len(art["frames"])
    if start_frame is None:
        _start = _cycle_start(_n_cycle)
    else:
        _start = int(start_frame) % _n_cycle if _n_cycle else 0
    latents = _rotate(art["latents"], _start)
    coords = _rotate(art["coords"], _start)
    mask_coords = _rotate(art["mask_coords"], _start)
    frames = _rotate(art["frames"], _start)
    masks = _rotate(art["masks"], _start)

    whisper_input_features, librosa_length = _audio_processor.get_audio_feature(
        wav_path, weight_dtype=_weight_dtype
    )
    whisper_chunks = _audio_processor.get_whisper_chunk(
        whisper_input_features, _device, _weight_dtype, _whisper, librosa_length,
        fps=fps, audio_padding_length_left=2, audio_padding_length_right=2,
    )
    video_num = len(whisper_chunks)
    h, w = frames[0].shape[:2]

    proc = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error",
        # probesize/analyzeduration minimal — ffmpeg rawvideo (pipe) kirishni 5MB
        # "probe" qilib kutmaydi; 1-kadr darrov o'qiladi (start kechikmaydi).
        "-probesize", "32", "-analyzeduration", "0",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0",
        *_audio_offset_args(), "-i", wav_path,
        "-map", "0:v", "-map", "1:a",
        # Video kodlovchi (odatda libx264 crf18; o'lchov: stream'da ffmpeg GPU ostida
        # to'liq yashiringan — bottleneck emas, shuning uchun NVENC kerak emas).
        *_venc_args(fps, low_latency=True), "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1",
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    _mcorr = _avatar_mouth_correction(avatar_id)

    def _composite(idx, res_frame):
        ci = idx % len(frames)
        x1, y1, x2, y2 = coords[ci]
        ori = frames[ci].copy()
        try:
            # Realtime: INTER_LINEAR (LANCZOS4 dan ~2x tez; sifat farqi sezilmaydi).
            rf = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1),
                            interpolation=cv2.INTER_CUBIC)
            rf = _sharpen_region(rf, _SHARPEN)
        except Exception:
            return None
        rf, _bb, _mcb = _mouth_correct(rf, [x1, y1, x2, y2], list(mask_coords[ci]), *_mcorr)
        return get_image_blending(ori, rf, _bb, masks[ci], _mcb)

    # GPU producer (UNet+VAE) → frame_q → BITTA consumer (composite + ffmpeg).
    # MUHIM (o'lchov): composite'ni ko'p threadga bo'lish GPU-dispatch producer
    # thread'idan Python GIL'ni o'g'irlab GPU'ni SEKINLASHTIRDI (8 worker → GPU
    # 1.55s→2.07s). Shu sabab bitta consumer eng tez (batch 16 bilan ~1.81s).
    # Katta navbat: GPU kadrlarni backpressuresiz to'kib slotini tez bo'shatadi.
    import queue as _queue
    frame_q: _queue.Queue = _queue.Queue(maxsize=512)

    _prof = os.environ.get("RT_PROFILE") == "1"
    _stat = {"gpu": 0.0}

    def producer():
        # GPU slotini FAQAT haqiqiy GPU hisoblash davomida ushlaymiz (multi-user).
        with _gpu_slot("stream"):
            try:
                _g0 = time.time()
                gen = datagen(whisper_chunks, latents, perf.batch_size())
                idx = 0
                with torch.inference_mode():
                    for whisper_batch, latent_batch in gen:
                        if idx >= video_num:
                            break
                        audio_feat = _pe(whisper_batch.to(_device))
                        lb = latent_batch.to(device=_device, dtype=_unet.model.dtype)
                        pred = _unet.model(lb, _timesteps, encoder_hidden_states=audio_feat).sample
                        pred = pred.to(device=_device, dtype=_vae.vae.dtype)
                        recon = _vae.decode_latents(pred)
                        for j in range(len(recon)):
                            if idx >= video_num:
                                break
                            frame_q.put((idx, recon[j]))   # GPU kutmaydi (navbat buferli)
                            idx += 1
                if _prof:
                    torch.cuda.synchronize()
                    _stat["gpu"] = time.time() - _g0
            except Exception as e:  # noqa: BLE001
                if _is_cuda_oom(e):
                    _reclaim_vram()
                    log.error("MuseTalk stream GPU xotira yetishmadi (OOM): %s", e)
                else:
                    log.error("MuseTalk stream producer xato: %s", e, exc_info=True)
        # slot bo'shadi — endi consumer/ffmpeg/tarmoq GPU'siz davom etadi
        frame_q.put(None)

    def consumer():
        last_fr = None
        last_idx = -1
        # TEMPORAL SILLIQLASH (real-time lab titrashini kamaytirish). Offline yo'lida
        # res_frame_list ustida EMA bor edi, lekin oqimda kadrlar birma-bir keladi —
        # shu sabab RUNNING EMA: ema = a*ema + (1-a)*joriy. Yuqori-chastotali jitter
        # damp bo'ladi, lab harakati saqlanadi. a=RT_LIP_SMOOTH (0..0.8). 0 = o'chiq.
        _ls = max(0.0, min(0.8, float(os.environ.get("RT_LIP_SMOOTH", "0.35"))))
        _ema = None
        try:
            while True:
                item = frame_q.get()
                if item is None:
                    break
                idx, rf = item
                if _ls > 0:
                    cur = rf.astype(np.float32)
                    _ema = cur if _ema is None else (_ls * _ema + (1.0 - _ls) * cur)
                    rf = _ema
                fr = _composite(idx, rf)
                if fr is not None:
                    proc.stdin.write(fr.astype(np.uint8).tobytes())
                    last_fr = fr
                    last_idx = idx
            # OG'IZ YUMSHOQ YOPILISHI: oxirgi nutq kadridan idle (yopiq og'iz)
            # kadrlariga crossfade — bosh pozasi davom etadi, og'iz tabiiy yopiladi
            # (keskin "pop" o'rniga). idle→handoff frontend'da silliq ulanadi.
            if last_fr is not None and len(frames) > 0:
                n_tail = 7
                ncyc = len(frames)
                for k in range(1, n_tail + 1):
                    idle_fr = frames[(last_idx + k) % ncyc]
                    alpha = k / (n_tail + 1)
                    blended = cv2.addWeighted(last_fr, 1.0 - alpha, idle_fr, alpha, 0)
                    proc.stdin.write(blended.astype(np.uint8).tobytes())
        except Exception as e:  # noqa: BLE001
            log.error("stream consumer xato: %s", e, exc_info=True)
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    _w0 = time.time()
    tp = threading.Thread(target=producer, daemon=True)
    tc = threading.Thread(target=consumer, daemon=True)
    tp.start()
    tc.start()
    try:
        # os.read — BufferedReader.read(n) emas: u aynan n bayt TO'LGUNCHA bloklaydi
        # (birinchi fragment ~0.5-0.9s kechikardi); os.read bori bilan darrov qaytadi.
        _out_fd = proc.stdout.fileno()
        while True:
            chunk = os.read(_out_fd, 65536)
            if not chunk:
                break
            yield chunk
    finally:
        # Mijoz ketgan bo'lsa ffmpeg'ni darrov o'ldiramiz (producer BrokenPipe olib
        # chiqadi, GPU bo'shaydi). Normal tugashda (ffmpeg o'zi chiqqan) zararsiz.
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.wait()
        tp.join(timeout=5)
        tc.join(timeout=5)
        if _prof:
            wall = time.time() - _w0
            log.debug("[PROFILE-STREAM] %d kadr | GPU=%.3fs | jami=%.3fs | overlap=%.3fs",
                      video_num, _stat['gpu'], wall, wall - _stat['gpu'])


def _wav_pcm16(wav_path: str) -> bytes:
    """wav → xom s16le 16kHz mono PCM baytlari (ffmpeg orqali, ishonchli)."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", wav_path,
         "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
        capture_output=True,
    )
    return p.stdout or b""


def _write_wav16(path: str, pcm: bytes):
    """16kHz mono s16 PCM baytlarini WAV faylga yozadi (Whisper kontekst-concat)."""
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)


# Jumla-oqim: oldingi jumlaning oxirgi shuncha KADRI audio dumi Whisper'ga chap
# kontekst bo'lib qo'shiladi. SABAB: har jumla Whisper'i mustaqil hisoblansa,
# chegaradagi kadrlar nol-padding "ko'radi" → lab qaltirashi/sinxron uzilish.
# Dum + jumla birga kodlanadi, dumga to'g'ri kelgan chunk'lar tashlanadi (UNet'ga
# bormaydi — faqat Whisper encode ozgina qimmatlashadi). 0 = o'chiq. 15 ≈ 0.6s.
_CTX_FRAMES = max(0, int(os.environ.get("RT_CTX_FRAMES", "15")))

# Preroll: 1-jumla TTS tayyor bo'lguncha javob videosida IDLE kadrlar real vaqt
# sur'atida oqadi. Video deyarli darrov boshlanadi (NVENC ham birinchi kadrda
# isiydi), avatar "tinglab turgan" ko'rinishda davom etadi, nutq tayyor bo'lishi
# bilan gapira boshlaydi → his qilinadigan kechikish ~2s dan ~0.5s ga tushadi.
# O'chirish: RT_PREROLL=0.
_PREROLL = os.environ.get("RT_PREROLL", "1").lower() not in ("0", "false", "no")
# Preroll BURST: dastlabki shuncha kadr KUTMASDAN (bir zumda) yoziladi — brauzer
# o'ynashni boshlash uchun bufer talab qiladi; kadrlar aynan real-vaqt tezligida
# kelsa bufer hech yig'ilmaydi (kelish = sarflanish) va o'ynash ~1s kechikadi.
# Burst bufer yostig'ini darrov beradi → onPlaying ancha oldin. Nutq vaqti
# o'zgarMAYDI: yostiq baribir qayerdandir kelishi kerak edi (15 ≈ 0.6s @25fps).
_PREROLL_BURST = max(0, int(os.environ.get("RT_PREROLL_BURST", "15")))
# Jumlalar ORASIDAGI kutish chegarasi (s): GPT/TTS shuncha vaqt jim qolsa oqim
# muloyim yakunlanadi (aks holda producer abadiy kutib GPU slotni band qilardi —
# "chala javob berib qotib qoladi" xatosining ildizi). Kutish paytida video
# to'xtamaydi: idle kadrlar oqib turadi ("o'ylab turgan" ko'rinish).
_GAP_MAX = max(5, int(os.environ.get("RT_GAP_MAX", "60")))
# Oqim QOTISH chegarasi (s): prodyuser `proc.stdin.write`da bloklanib qolsa (brauzer
# videoni iste'mol qilishni to'xtatgani/uzilgani → orqa-bosim) `cancel` ni KO'RA OLMAYDI
# va GPU slotni cheksiz band qiladi (faqat keyingi navbat tiklardi). Watchdog: cancel
# o'rnatilса YOKI shuncha soniya BIRORTA kadr yozilmasa (yozuv qotgan) ffmpeg'ni
# o'ldiradi → stdin.write BrokenPipe beradi → prodyuser chiqadi, slot bo'shaydi.
_STALL_MAX = max(5, int(os.environ.get("RT_STALL_MAX", "20")))


def musetalk_infer_stream_queue(chunk_queue, fps: int = 25, avatar_id: str = None,
                                start_frame=None, max_dim=None, cancel=None):
    """SENTENCE-LEVEL streaming: javob JUMLALARI wav bo'laklari sifatida `chunk_queue`'dan
    kelib turadi (None = tugadi). Avatar 1-jumlani gapira boshlaydi, ayni paytda keyingi
    jumla yozilyapti/sintez qilinyapti → kechikish keskin kamayadi.

    CONTINUITY KAFOLATI:
      • Bosh harakati — kadr sikli ofseti (pos) jumladan-jumlaga UZATILADI (sakramaydi).
      • Og'iz yopilishi (tail crossfade) — faqat ENG OXIRIDA (oraliq jumlalarda emas).
      • Bitta uzluksiz ffmpeg (frag-mp4) → brauzer bitta video sifatida o'ynaydi.
      • Audio FIFO orqali jumla PCM'lari ketma-ket muxlanadi (A/V sinxron).
    """
    import torch
    import cv2
    import numpy as np
    import threading
    import os as _os
    import tempfile
    from musetalk.utils.utils import datagen
    from musetalk.utils.blending import get_image_blending

    ensure_loaded()
    art = _get_artifact(avatar_id, max_dim)
    n = len(art["frames"])
    if start_frame is None or not n:
        _start = _cycle_start(n)
    else:
        _start = int(start_frame) % n
    latents = _rotate(art["latents"], _start)
    coords = _rotate(art["coords"], _start)
    mask_coords = _rotate(art["mask_coords"], _start)
    frames = _rotate(art["frames"], _start)
    masks = _rotate(art["masks"], _start)
    h, w = frames[0].shape[:2]

    # Audio uchun ODDIY QUVUR (os.pipe) — FIFO open-rendezvous deadlock'ini yo'qotadi
    # (FIFO'da producer ochilishda, ffmpeg stdin video kutib — o'zaro qulflanardi).
    # ffmpeg `pipe:<fd>` orqali meros olgan o'qish-fd'dan o'qiydi; biz audio_w'ga yozamiz.
    import queue as _q
    audio_r, audio_w = _os.pipe()
    _os.set_inheritable(audio_r, True)

    proc = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error",
        # thread_queue_size — har kirish uchun katta bufer: ffmpeg bitta quvurni o'qiyotganda
        # ikkinchisi to'lib-toshmaydi (ikki-quvur deadlock'ini yo'qotadi).
        # probesize/analyzeduration minimal — ffmpeg rawvideo kirishni "probe" qilish
        # uchun 5MB bufer kutmaydi (aks holda 1-kadr (2.7MB) yozishda DEADLOCK bo'lardi:
        # ffmpeg ko'proq kutadi, producer yozolmaydi, hech narsa o'qilmaydi).
        "-probesize", "32", "-analyzeduration", "0", "-thread_queue_size", "4096",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0",
        "-probesize", "32", "-analyzeduration", "0", "-thread_queue_size", "4096",
        "-f", "s16le", "-ar", "16000", "-ac", "1", "-i", f"pipe:{audio_r}",
        "-map", "0:v", "-map", "1:a",
        *_venc_args(fps, low_latency=True), "-c:a", "aac", "-b:a", "128k",
        # max_interleave_delta 0 — ffmpeg interleave uchun kutmasdan paketlarni darrov
        # muxer'ga beradi (frag'lar tez chiqadi, birinchi kadr bloklanmaydi).
        "-max_interleave_delta", "0",
        # frag_every_frame — HAR KADR alohida fragment: birinchi kadr kodlanishi
        # bilanoq brauzerga chiqadi (frag_keyframe ~7 kadr yig'ilishini kutardi,
        # TTFF -0.3..0.6s). moof sarlavha xarajati kadr boshiga ~1KB — arzimas.
        "-movflags", "empty_moov+default_base_moof+frag_every_frame", "-f", "mp4", "pipe:1",
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
       pass_fds=(audio_r,))
    _os.close(audio_r)   # ota jarayon o'qish uchini yopadi (ffmpeg meros oldi)

    # Audio'ni ALOHIDA thread yozadi — GPU loop'ni quvur to'lib bloklamaydi.
    audio_bq: _q.Queue = _q.Queue()

    # Watchdog holati: oxirgi kadr yozilgan vaqt + prodyuser tugadi bayrog'i.
    _last_prog = [time.time()]
    _wd_done = threading.Event()

    def _watchdog():
        """Oqim qotsa (write bloklangan) yoki barge-in bo'lsa ffmpeg'ni o'ldiradi —
        prodyuser stdin.write'da BrokenPipe olib chiqadi, GPU slot bo'shaydi."""
        while not _wd_done.wait(1.0):
            _stall = (cancel is not None and cancel.is_set()) or \
                     (time.time() - _last_prog[0] > _STALL_MAX)
            if _stall:
                if not (cancel is not None and cancel.is_set()):
                    log.warning("[streamq] oqim %ds yozilmadi (orqa-bosim/uzilish) — "
                                "ffmpeg to'xtatiladi, GPU slot bo'shatiladi", _STALL_MAX)
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
                break

    def audio_writer():
        try:
            while True:
                b = audio_bq.get()
                if b is None:
                    break
                _os.write(audio_w, b)
        except Exception as e:  # noqa: BLE001
            log.error("streamq audio xato: %s", e)
        finally:
            try:
                _os.close(audio_w)
            except Exception:
                pass

    _mcorr = _avatar_mouth_correction(avatar_id)

    def _composite(ci, res_frame):
        x1, y1, x2, y2 = coords[ci]
        ori = frames[ci].copy()
        try:
            # Realtime: INTER_LINEAR (LANCZOS4 dan ~2x tez; realtime'da sifat farqi
            # deyarli sezilmaydi, lekin per-kadr compositing'ni keskin tezlashtiradi).
            rf = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1),
                            interpolation=cv2.INTER_CUBIC)
            rf = _sharpen_region(rf, _SHARPEN)
        except Exception:
            return None
        rf, _bb, _mcb = _mouth_correct(rf, [x1, y1, x2, y2], list(mask_coords[ci]), *_mcorr)
        return get_image_blending(ori, rf, _bb, masks[ci], _mcb)

    def producer():
        pos = 0
        last_fr = None
        # TTFF profiling (RT_STREAM_PROFILE=1) — birinchi jumla bosqich vaqtlari.
        _sp = os.environ.get("RT_STREAM_PROFILE") == "1"
        _sp0 = time.time()
        _sp_first = True
        # Chap kontekst dumi (oldingi jumla PCM oxiri) — jumla chegarasida Whisper
        # uzilishini yo'qotadi. Baytlar KADRga aniq karrali bo'ladi (A/V drift yo'q).
        ctx_pcm = b""
        spf_b = (16000 // int(fps)) * 2 if fps and 16000 % int(fps) == 0 else 0
        # Og'iz EMA silliqlash — bitta-wav stream yo'li bilan BIR XIL (u yerda bor
        # edi, bu yo'lda yo'q edi). Holat jumlalar ORASIDA ham uzluksiz.
        _ls = max(0.0, min(0.8, float(os.environ.get("RT_LIP_SMOOTH", "0.35"))))
        _ema = None
        _preroll_done = not _PREROLL
        try:
            with _gpu_slot("streamq"), torch.inference_mode():
                while True:
                    if not _preroll_done:
                        # ── PREROLL: TTS tayyor bo'lguncha idle kadrlar (real vaqt
                        # sur'atida — video timeline'i haqiqiy vaqt bilan teng yuradi,
                        # shunda nutq o'z o'rnida boshlanadi, keyinga surilmaydi). ──
                        # MUHIM: audio DOIM videodan _A_LEAD kadr OLDINDA yuriladi —
                        # kadr-bakadr teng qadam (lockstep) mp4 muxer + AAC (1024
                        # sample blok) navbatida DEADLOCK qilardi (jonli xato: 12
                        # kadrdan keyin butun ffmpeg futex'da muzlab qolardi; eski
                        # yo'l barqaror edi chunki jumla audiosi butunlay oldindan
                        # kelardi). Preroll oxirida video shu avansга tenglashtiriladi
                        # (qo'shimcha idle kadrlar) — A/V sinxron buzilmaydi.
                        _preroll_done = True
                        spf = 1.0 / float(fps)
                        sil = b"\x00\x00" * (16000 // int(fps))   # 1 kadrlik jimlik
                        _pre_max = int(fps) * 45   # xavfsizlik: ko'pi bilan 45s preroll
                        _A_LEAD = 8                # audio avansi (kadrlarda, ~0.3s)
                        for _ in range(_A_LEAD):
                            audio_bq.put(sil)
                        wav = None
                        while pos < _pre_max:
                            try:
                                wav = chunk_queue.get_nowait()
                                break
                            except _q.Empty:
                                pass
                            if cancel is not None and cancel.is_set():
                                break
                            _t0 = time.time()
                            audio_bq.put(sil)   # avans saqlanadi (video -_A_LEAD orqada)
                            proc.stdin.write(frames[pos % n].astype(np.uint8).tobytes())
                            _last_prog[0] = time.time()
                            if _sp and pos == 0:
                                log.info("[TTFF] preroll 1-kadr ffmpeg'ga yozildi: %.2fs",
                                         time.time() - _sp0)
                            pos += 1
                            # Dastlabki BURST kadrlar kutmasdan ketadi (brauzer bufer
                            # yostig'i); qolganlari real-vaqt sur'atida.
                            if pos > _PREROLL_BURST:
                                _dt = time.time() - _t0
                                if _dt < spf:
                                    time.sleep(spf - _dt)
                        # Avansni yopamiz: video audio'ga yetib oladi (sinxron teng).
                        for _ in range(_A_LEAD):
                            proc.stdin.write(frames[pos % n].astype(np.uint8).tobytes())
                            pos += 1
                    else:
                        # ── Keyingi jumlani KUTISH — bloklanmaydi. GPT/TTS kechiksa
                        # 0.35s dan keyin idle kadrlar oqadi (video jonli, brauzer
                        # stall bo'lmaydi); _GAP_MAX dan oshsa oqim muloyim tugaydi
                        # (aks holda producer abadiy kutib GPU slotni band qilardi).
                        # A/V yozish preroll bilan bir xil AVANS tartibida (lockstep
                        # deadlock'ka qarshi). ──
                        wav = None
                        _w0 = time.time()
                        _spf = 1.0 / float(fps)
                        _sil = b"\x00\x00" * (16000 // int(fps))
                        _lead_open = 0     # gap-fill boshlagan bo'lsak yopish kerak
                        while True:
                            try:
                                wav = chunk_queue.get(timeout=0.3)
                                break
                            except _q.Empty:
                                pass
                            if cancel is not None and cancel.is_set():
                                break
                            if time.time() - _w0 > _GAP_MAX:
                                log.warning("[streamq] jumla %ds ichida kelmadi — oqim yakunlanadi",
                                            _GAP_MAX)
                                break
                            if time.time() - _w0 <= 0.35:
                                continue   # qisqa pauza — to'ldirish shart emas
                            if _lead_open == 0:
                                for _ in range(_A_LEAD):   # audio avansini ochamiz
                                    audio_bq.put(_sil)
                                _lead_open = _A_LEAD
                            _t0 = time.time()
                            audio_bq.put(_sil)
                            proc.stdin.write(frames[pos % n].astype(np.uint8).tobytes())
                            _last_prog[0] = time.time()
                            pos += 1
                            _dt = time.time() - _t0
                            if _dt < _spf:
                                time.sleep(_spf - _dt)
                        if _lead_open:
                            # Avansni yopamiz (video audio'ga tenglashadi — sinxron).
                            for _ in range(_lead_open):
                                proc.stdin.write(frames[pos % n].astype(np.uint8).tobytes())
                                pos += 1
                    if wav is None:
                        break
                    if cancel is not None and cancel.is_set():   # barge-in: to'xtatamiz
                        break
                    _last_prog[0] = time.time()   # jumla keldi — whisper/inference gapi qotish emas
                    # 1) jumla audiosi → audio yozuvchi thread (quvur orqali ffmpeg'ga)
                    pcm = _wav_pcm16(wav)
                    if pcm:
                        audio_bq.put(pcm)
                    # 2) jumla kadrlari (kadr sikli `pos`dan davom etadi → bosh sakramaydi).
                    #    Whisper'ga dum+jumla birga beriladi, dum chunk'lari tashlanadi.
                    skip = 0
                    feat_wav = wav
                    if ctx_pcm and spf_b and pcm:
                        skip = len(ctx_pcm) // spf_b
                        feat_wav = wav + ".ctx.wav"
                        _write_wav16(feat_wav, ctx_pcm + pcm)
                    feats, llen = _audio_processor.get_audio_feature(feat_wav, weight_dtype=_weight_dtype)
                    wchunks = _audio_processor.get_whisper_chunk(
                        feats, _device, _weight_dtype, _whisper, llen,
                        fps=fps, audio_padding_length_left=2, audio_padding_length_right=2,
                    )
                    if skip:
                        wchunks = wchunks[skip:]
                        try:
                            _os.remove(feat_wav)
                        except OSError:
                            pass
                    # Keyingi jumla uchun dum (kadr chegarasiga tekislangan)
                    if _CTX_FRAMES and spf_b and pcm:
                        k = min(_CTX_FRAMES, len(pcm) // spf_b)
                        ctx_pcm = pcm[len(pcm) - k * spf_b:] if k else b""
                    else:
                        ctx_pcm = b""
                    vnum = len(wchunks)
                    if _sp and _sp_first:
                        log.info("[TTFF] whisper(1-jumla) tayyor: %.2fs (%d kadr)",
                                 time.time() - _sp0, vnum)
                    lat = _rotate(latents, pos % n) if n else latents
                    idx = 0
                    for wb, lb in datagen(wchunks, lat, perf.batch_size()):
                        if idx >= vnum:
                            break
                        afeat = _pe(wb.to(_device))
                        lb = lb.to(device=_device, dtype=_unet.model.dtype)
                        pred = _unet.model(lb, _timesteps, encoder_hidden_states=afeat).sample
                        pred = pred.to(device=_device, dtype=_vae.vae.dtype)
                        recon = _vae.decode_latents(pred)
                        for r in recon:
                            if idx >= vnum:
                                break
                            if cancel is not None and cancel.is_set():
                                break
                            if _ls > 0:
                                cur = r.astype(np.float32)
                                _ema = cur if _ema is None else (_ls * _ema + (1.0 - _ls) * cur)
                                r = _ema
                            ci = (pos + idx) % n
                            fr = _composite(ci, r)
                            if fr is not None:
                                proc.stdin.write(fr.astype(np.uint8).tobytes())
                                _last_prog[0] = time.time()
                                last_fr = fr
                                if _sp and _sp_first:
                                    log.info("[TTFF] 1-kadr ffmpeg'ga yozildi: %.2fs",
                                             time.time() - _sp0)
                                    _sp_first = False
                            idx += 1
                    if cancel is not None and cancel.is_set():
                        break
                    pos += vnum
            # OG'IZ YUMSHOQ YOPILISHI — faqat oxirida (barge-in bo'lsa o'tkazib yuboramiz).
            _cx = cancel is not None and cancel.is_set()
            if last_fr is not None and n and not _cx:
                n_tail = 7
                audio_bq.put(b"\x00\x00" * int(16000 * n_tail / fps))   # mos sukunat audio
                for k in range(1, n_tail + 1):
                    idle_fr = frames[(pos + k) % n]
                    alpha = k / (n_tail + 1)
                    bl = cv2.addWeighted(last_fr, 1.0 - alpha, idle_fr, alpha, 0)
                    proc.stdin.write(bl.astype(np.uint8).tobytes())
        except Exception as e:  # noqa: BLE001
            if _is_cuda_oom(e):
                _reclaim_vram()
                log.error("streamq GPU xotira yetishmadi (OOM): %s", e)
            else:
                log.error("streamq producer xato: %s", e, exc_info=True)
        finally:
            _wd_done.set()              # watchdog to'xtasin (normal tugash — kill kerak emas)
            audio_bq.put(None)          # audio yozuvchi → audio_w'ni yopadi (EOF)
            try:
                proc.stdin.close()
            except Exception:
                pass

    threading.Thread(target=audio_writer, daemon=True).start()
    threading.Thread(target=_watchdog, daemon=True).start()
    threading.Thread(target=producer, daemon=True).start()
    try:
        # os.read — bori bilan darrov qaytadi (64KB to'lishini kutmaydi) → birinchi
        # fragment brauzerga bir zumda yetadi (TTFF -0.5..0.9s).
        _out_fd = proc.stdout.fileno()
        while True:
            chunk = _os.read(_out_fd, 65536)
            if not chunk:
                break
            yield chunk
    finally:
        # Mijoz KETGAN bo'lsa (GeneratorExit) ffmpeg'ni DARROV o'ldiramiz — aks holda
        # ffmpeg stdout'i to'lib stdin o'qishni to'xtatadi → producer stdin.write'da
        # abadiy qotib GPU slotni ushlab qoladi → KEYINGI so'rovlarga video chiqmaydi
        # (jonli xato: 5 ta ffmpeg to'planib butun oqim o'lgan edi). Producer
        # BrokenPipe oladi → chiqadi → slot bo'shaydi. Normal tugashda zararsiz.
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.wait()
