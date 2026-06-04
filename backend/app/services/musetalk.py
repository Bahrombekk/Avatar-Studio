"""MuseTalk lip-sync dvigateli — modellarni yuklash + audio→mp4 inference.

Modellar (VAE/UNet/Whisper/FaceParsing) avatardan MUSTAQIL — bir marta yuklanadi.
Avatar artefakti (latents, koordinatalar, full_imgs, mask) esa HAR AVATAR uchun
alohida: avval per-avatar artefakt (data/avatars/<id>/artifact/) qidiriladi, topilmasa
eski madina_lp artefakti (MT_DIR) fallback bo'ladi. Yuklangan artefaktlar keshlanadi.
"""
import glob
import os
import pickle
import subprocess
import threading
import time

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


def _get_artifact(avatar_id):
    """Avatar artefaktini (keshlangan) qaytaradi. Topilmasa RuntimeError."""
    key, paths = _resolve_artifact(avatar_id)
    if key is None:
        raise RuntimeError(
            "Avatar artefakti topilmadi — avval MuseTalk preprocessing bajaring"
        )
    with _avatars_lock:
        cached = _avatars.get(key)
    if cached is not None:
        return cached

    import torch
    import cv2
    from concurrent.futures import ThreadPoolExecutor

    t1 = time.time()
    latents = torch.load(str(paths["latents"]))
    with open(paths["coords"], "rb") as f:
        coords = pickle.load(f)
    with open(paths["mask_coords"], "rb") as f:
        mask_coords = pickle.load(f)
    # 200 kadr + 200 mask PNG — PARALLEL o'qiymiz (DrvFs'da ketma-ket o'qish sekin;
    # cv2.imread GIL'ni bo'shatadi → parallel I/O birinchi yuklashni keskin tezlashtiradi).
    img_paths = sorted(glob.glob(str(paths["imgs_dir"] / "*.png")))
    mask_paths = sorted(glob.glob(str(paths["mask_dir"] / "*.png")))
    with ThreadPoolExecutor(max_workers=16) as ex:
        frames = list(ex.map(cv2.imread, img_paths))
        masks = list(ex.map(cv2.imread, mask_paths))

    art = {"latents": latents, "coords": coords, "mask_coords": mask_coords,
           "frames": frames, "masks": masks}
    with _avatars_lock:
        _avatars[key] = art
    print(f"[LP-MuseTalk] Artefakt '{key}': {len(frames)} kadr ({time.time()-t1:.1f}s)")
    return art


def invalidate(avatar_id):
    """Avatar artefakt keshini bo'shatadi (preprocessing qayta yasalgach)."""
    with _avatars_lock:
        _avatars.pop(avatar_id, None)


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


def preload_artifact(avatar_id: str) -> bool:
    """Avatar artefaktini (200 kadr/mask PNG) keshга oldindan yuklaydi.

    Birinchi so'rov sekin bo'lmasligi uchun startupda chaqiriladi — aks holda
    foydalanuvchining BIRINCHI savolida artefakt diskdan (sekin DrvFs) o'qiladi.
    """
    try:
        ensure_loaded()
        _get_artifact(avatar_id)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[LP-MuseTalk] preload '{avatar_id}' ogohlantirish: {e}")
        return False


def musetalk_infer(wav_path: str, out_mp4: str, fps: int = 25, avatar_id: str = None) -> bool:
    import torch
    import cv2
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor
    from musetalk.utils.utils import datagen
    from musetalk.utils.blending import get_image_blending

    ensure_loaded()

    try:
        art = _get_artifact(avatar_id)
        _input_latent_list_cycle = art["latents"]
        _coord_list_cycle = art["coords"]
        _mask_coords_list_cycle = art["mask_coords"]
        _frame_list_cycle = art["frames"]
        _mask_list_cycle = art["masks"]

        # 1. Whisper audio xususiyatlari
        whisper_input_features, librosa_length = _audio_processor.get_audio_feature(
            wav_path, weight_dtype=_weight_dtype
        )
        whisper_chunks = _audio_processor.get_whisper_chunk(
            whisper_input_features, _device, _weight_dtype, _whisper, librosa_length,
            fps=fps, audio_padding_length_left=2, audio_padding_length_right=2,
        )
        video_num = len(whisper_chunks)

        # 2. Batch inference
        batch_size = 8
        gen = datagen(whisper_chunks, _input_latent_list_cycle, batch_size)
        res_frame_list = []
        with torch.inference_mode():
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

        # 3. To'liq kadrga composite (parallel)
        n_total = min(len(res_frame_list), video_num)

        def _composite_one(idx):
            cycle_idx = idx % len(_frame_list_cycle)
            bbox = _coord_list_cycle[cycle_idx]
            ori_frame = _frame_list_cycle[cycle_idx].copy()
            x1, y1, x2, y2 = bbox
            try:
                rf = cv2.resize(res_frame_list[idx].astype(np.uint8), (x2 - x1, y2 - y1))
            except Exception:
                return None
            mask = _mask_list_cycle[cycle_idx]
            mask_crop_box = _mask_coords_list_cycle[cycle_idx]
            return get_image_blending(ori_frame, rf, bbox, mask, mask_crop_box)

        with ThreadPoolExecutor(max_workers=12) as ex:
            out_frames = [f for f in ex.map(_composite_one, range(n_total)) if f is not None]

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

        # 4. ffmpeg STDIN orqali mp4
        h, w = out_frames[0].shape[:2]
        proc = subprocess.Popen([
            "ffmpeg", "-y", "-v", "warning",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps),
            "-i", "-", "-i", wav_path,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "ultrafast",
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

        return os.path.exists(out_mp4)

    except Exception as e:
        print(f"[LP-MuseTalk ERR] {e}")
        import traceback
        traceback.print_exc()
        return False


def musetalk_infer_stream(wav_path: str, fps: int = 25, avatar_id: str = None):
    """STREAMING variant: kadrlarni generatsiya paytida fragmented-mp4 bayt
    bo'laklari sifatida yieldlaydi (eski musetalk_infer'ga TEGILMAYDI — additiv).

    ffmpeg fragmented mp4 (frag_keyframe+empty_moov) — brauzer progressive o'ynaydi.
    Yozuvchi thread kadrlarni stdin'ga yozadi; generator stdout'dan o'qib uzatadi
    (deadlock yo'q). Kadrlar BATCH bo'yicha parallel composit qilinib, tartibda yoziladi.
    """
    import torch
    import cv2
    import numpy as np
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from musetalk.utils.utils import datagen
    from musetalk.utils.blending import get_image_blending

    ensure_loaded()
    art = _get_artifact(avatar_id)
    latents = art["latents"]
    coords = art["coords"]
    mask_coords = art["mask_coords"]
    frames = art["frames"]
    masks = art["masks"]

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
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0",
        "-i", wav_path,
        "-map", "0:v", "-map", "1:a",
        # Sifat: crf 18 + veryfast (ultrafast'dan aniqroq), tezlikka deyarli ta'sir yo'q.
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-g", str(fps), "-crf", "18", "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1",
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _composite(idx, res_frame):
        ci = idx % len(frames)
        x1, y1, x2, y2 = coords[ci]
        ori = frames[ci].copy()
        try:
            rf = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
        except Exception:
            return None
        return get_image_blending(ori, rf, [x1, y1, x2, y2], masks[ci], mask_coords[ci])

    # LEAN: GPU thread UNet'ni UZLUKSIZ yuritadi (GPU isib/pipelined qoladi → batch
    # tezligi), dekodlangan kadrlarni navbatga qo'yadi. Consumer BITTA thread'da
    # composite (cv2 GIL'ni bo'shatadi) + ffmpeg'ga yozadi. Kam thread → GIL kurashi minimal.
    import queue as _queue
    frame_q: _queue.Queue = _queue.Queue(maxsize=48)

    def producer():
        try:
            gen = datagen(whisper_chunks, latents, 8)
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
        except Exception as e:  # noqa: BLE001
            print(f"[LP-MuseTalk stream producer ERR] {e}")
        finally:
            frame_q.put(None)

    def consumer():
        try:
            while True:
                item = frame_q.get()
                if item is None:
                    break
                idx, rf = item
                fr = _composite(idx, rf)
                if fr is not None:
                    proc.stdin.write(fr.astype(np.uint8).tobytes())
        except Exception as e:  # noqa: BLE001
            print(f"[LP-MuseTalk stream consumer ERR] {e}")
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

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
