"""MuseTalk lip-sync dvigateli — modellarni yuklash + audio→mp4 inference.

Modellar (VAE/UNet/Whisper/FaceParsing) avatardan MUSTAQIL — bir marta yuklanadi.
Avatar artefakti (latents, koordinatalar, full_imgs, mask) esa HAR AVATAR uchun
alohida: avval per-avatar artefakt (data/avatars/<id>/artifact/) qidiriladi, topilmasa
eski madina_lp artefakti (MT_DIR) fallback bo'ladi. Yuklangan artefaktlar keshlanadi.
"""
import glob
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

# Og'ir importlarni MODUL yuklanishida (asosiy thread) bajaramiz. diffusers
# lazy-import tizimi bir nechta thread'dan chaqirilsa "object of type 'int' has
# no len()" xatosi beradi — warmup fon thread'i shunga uchragan edi.
try:
    import torch  # noqa: F401
    import diffusers  # noqa: F401
    from diffusers import AutoencoderKL, UNet2DConditionModel  # noqa: F401
    import diffusers.schedulers.scheduling_lms_discrete  # noqa: F401
except Exception as _imp_err:
    print(f"[LP-MuseTalk] eager import ogohlantirish: {_imp_err}")

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
_SHARPEN = max(0.0, float(os.environ.get("RT_SHARPEN", "0.55")))

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
        print(f"[LP-MuseTalk] GPU navbatda kutildi {waited:.2f}s ({tag})")
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
    print(f"[LP-MuseTalk] Video kodlovchi: {_ENCODER}")
    return _ENCODER


def _venc_args(fps: int, hd: bool = False) -> list:
    """ffmpeg video kodlash argumentlari. hd=True (offline Studio) → yuqoriroq sifat
    (crf 16 + sekinroq preset; NVENC cq 17/p7). hd=False (real-time) → tez (crf 18).
    NVENC ~5x tez, lekin x264 (slow) biroz tiniqroq — offline'da x264 afzal."""
    enc = _encoder_name()
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
    print("[LP-MuseTalk] Modellar yuklanmoqda...")

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
            print("[LP-MuseTalk] torch.compile yoqildi (UNet + VAE)")
        except Exception as e:  # noqa: BLE001
            print(f"[LP-MuseTalk] torch.compile o'tkazib yuborildi: {e}")

    _loaded = True
    print(f"[LP-MuseTalk] Asosiy modellar tayyor: {time.time()-t0:.1f}s")


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
    return v if v in (1280, 1920) else 1280


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
        print(f"[LP-MuseTalk] Artefakt '{key}': {len(native['frames'])} kadr ({time.time()-t1:.1f}s)")
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
    print(f"[LP-MuseTalk] Artefakt '{key}' @{max_dim} ({ratio:.3f}x): "
          f"{len(scaled['frames'])} kadr ({time.time()-t2:.1f}s)")
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
        print("[LP-MuseTalk] Warmup o'tkazib yuborildi — hech qanday artefakt yo'q")
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
    print(f"[LP-MuseTalk] Warmup: {time.time()-t:.1f}s")


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
        print(f"[LP-MuseTalk] preload '{avatar_id}' ogohlantirish: {e}")
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
            print(f"[PROFILE] {name}: {time.time()-_pt:.3f}s")
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
        batch_size = _BATCH
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
                print(f"[LP-MuseTalk GFPGAN o'tkazildi] {e}")

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
            proc.stdin.close()
            proc.wait(timeout=60)
        except Exception as e:
            print(f"[LP-MuseTalk ffmpeg ERR] {e}")
            proc.kill()
            return False
        _lap("ffmpeg encode")

        return os.path.exists(out_mp4)

    except Exception as e:
        print(f"[LP-MuseTalk ERR] {e}")
        import traceback
        traceback.print_exc()
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
        *_venc_args(fps), "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1",
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _composite(idx, res_frame):
        ci = idx % len(frames)
        x1, y1, x2, y2 = coords[ci]
        ori = frames[ci].copy()
        try:
            # Realtime: INTER_LINEAR (LANCZOS4 dan ~2x tez; sifat farqi sezilmaydi).
            rf = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1),
                            interpolation=cv2.INTER_LINEAR)
            rf = _sharpen_region(rf, _SHARPEN)
        except Exception:
            return None
        return get_image_blending(ori, rf, [x1, y1, x2, y2], masks[ci], mask_coords[ci])

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
                gen = datagen(whisper_chunks, latents, _BATCH)
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
                print(f"[LP-MuseTalk stream producer ERR] {e}")
        # slot bo'shadi — endi consumer/ffmpeg/tarmoq GPU'siz davom etadi
        frame_q.put(None)

    def consumer():
        last_fr = None
        last_idx = -1
        try:
            while True:
                item = frame_q.get()
                if item is None:
                    break
                idx, rf = item
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
            print(f"[LP-MuseTalk stream consumer ERR] {e}")
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
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.wait()
        tp.join(timeout=5)
        tc.join(timeout=5)
        if _prof:
            wall = time.time() - _w0
            print(f"[PROFILE-STREAM] {video_num} kadr | GPU={_stat['gpu']:.3f}s | "
                  f"jami devor-soat={wall:.3f}s | consumer+ffmpeg overlap={wall-_stat['gpu']:.3f}s")


def _wav_pcm16(wav_path: str) -> bytes:
    """wav → xom s16le 16kHz mono PCM baytlari (ffmpeg orqali, ishonchli)."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", wav_path,
         "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
        capture_output=True,
    )
    return p.stdout or b""


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
        *_venc_args(fps), "-c:a", "aac", "-b:a", "128k",
        # max_interleave_delta 0 — ffmpeg interleave uchun kutmasdan paketlarni darrov
        # muxer'ga beradi (frag'lar tez chiqadi, birinchi kadr bloklanmaydi).
        "-max_interleave_delta", "0",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1",
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
       pass_fds=(audio_r,))
    _os.close(audio_r)   # ota jarayon o'qish uchini yopadi (ffmpeg meros oldi)

    # Audio'ni ALOHIDA thread yozadi — GPU loop'ni quvur to'lib bloklamaydi.
    audio_bq: _q.Queue = _q.Queue()

    def audio_writer():
        try:
            while True:
                b = audio_bq.get()
                if b is None:
                    break
                _os.write(audio_w, b)
        except Exception as e:  # noqa: BLE001
            print(f"[LP-MuseTalk streamq audio ERR] {e}")
        finally:
            try:
                _os.close(audio_w)
            except Exception:
                pass

    def _composite(ci, res_frame):
        x1, y1, x2, y2 = coords[ci]
        ori = frames[ci].copy()
        try:
            # Realtime: INTER_LINEAR (LANCZOS4 dan ~2x tez; realtime'da sifat farqi
            # deyarli sezilmaydi, lekin per-kadr compositing'ni keskin tezlashtiradi).
            rf = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1),
                            interpolation=cv2.INTER_LINEAR)
            rf = _sharpen_region(rf, _SHARPEN)
        except Exception:
            return None
        return get_image_blending(ori, rf, [x1, y1, x2, y2], masks[ci], mask_coords[ci])

    def producer():
        pos = 0
        last_fr = None
        try:
            with _gpu_slot("streamq"), torch.inference_mode():
                while True:
                    wav = chunk_queue.get()
                    if wav is None:
                        break
                    if cancel is not None and cancel.is_set():   # barge-in: to'xtatamiz
                        break
                    # 1) jumla audiosi → audio yozuvchi thread (quvur orqali ffmpeg'ga)
                    pcm = _wav_pcm16(wav)
                    if pcm:
                        audio_bq.put(pcm)
                    # 2) jumla kadrlari (kadr sikli `pos`dan davom etadi → bosh sakramaydi)
                    feats, llen = _audio_processor.get_audio_feature(wav, weight_dtype=_weight_dtype)
                    wchunks = _audio_processor.get_whisper_chunk(
                        feats, _device, _weight_dtype, _whisper, llen,
                        fps=fps, audio_padding_length_left=2, audio_padding_length_right=2,
                    )
                    vnum = len(wchunks)
                    lat = _rotate(latents, pos % n) if n else latents
                    idx = 0
                    for wb, lb in datagen(wchunks, lat, _BATCH):
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
                            ci = (pos + idx) % n
                            fr = _composite(ci, r)
                            if fr is not None:
                                proc.stdin.write(fr.astype(np.uint8).tobytes())
                                last_fr = fr
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
            print(f"[LP-MuseTalk streamq producer ERR] {e}")
        finally:
            audio_bq.put(None)          # audio yozuvchi → audio_w'ni yopadi (EOF)
            try:
                proc.stdin.close()
            except Exception:
                pass

    threading.Thread(target=audio_writer, daemon=True).start()
    threading.Thread(target=producer, daemon=True).start()
    try:
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.wait()
