"""MuseTalk lip-sync dvigateli — modellarni yuklash + audio→mp4 inference.

madina_lp avatar artefakti (latents, koordinatalar, full_imgs) MT_DIR ichida.
"""
import glob
import os
import pickle
import subprocess
import threading
import time

from app.core.paths import (
    MT_DIR, AVATAR_DIR, AVATAR_LATENTS, AVATAR_COORDS, AVATAR_MASK_COORD,
    AVATAR_MASK_DIR, AVATAR_IMGS_DIR, VID_OUT_DIR,
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

# ── Global model holatlari ──
_loaded = False
_lock = threading.Lock()
_vae = _unet = _pe = _whisper = _audio_processor = _fp = None
_timesteps = _weight_dtype = _device = None

_frame_list_cycle = None
_coord_list_cycle = None
_input_latent_list_cycle = None
_mask_coords_list_cycle = None
_mask_list_cycle = None


def is_loaded() -> bool:
    return _loaded


def _load():
    """MuseTalk modellari + madina_lp avatar artifaktini yuklash (bir martalik)."""
    global _loaded, _vae, _unet, _pe, _whisper, _audio_processor, _fp
    global _timesteps, _weight_dtype, _device
    global _frame_list_cycle, _coord_list_cycle, _input_latent_list_cycle
    global _mask_coords_list_cycle, _mask_list_cycle

    if _loaded:
        return

    import torch
    import cv2
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
    print(f"[LP-MuseTalk] Asosiy modellar: {time.time()-t0:.1f}s")

    if not AVATAR_LATENTS.exists():
        raise RuntimeError(
            f"Avatar artifact topilmadi: {AVATAR_DIR}\n"
            f"Avval MuseTalk preprocessing ishga tushiring (assets/musetalk_idle_lp.yaml)."
        )

    t1 = time.time()
    _input_latent_list_cycle = torch.load(str(AVATAR_LATENTS))
    with open(AVATAR_COORDS, "rb") as f:
        _coord_list_cycle = pickle.load(f)
    with open(AVATAR_MASK_COORD, "rb") as f:
        _mask_coords_list_cycle = pickle.load(f)

    img_paths = sorted(glob.glob(str(AVATAR_IMGS_DIR / "*.png")))
    _frame_list_cycle = [cv2.imread(p) for p in img_paths]
    mask_paths = sorted(glob.glob(str(AVATAR_MASK_DIR / "*.png")))
    _mask_list_cycle = [cv2.imread(p) for p in mask_paths]

    print(f"[LP-MuseTalk] Avatar: {len(_frame_list_cycle)} kadr ({time.time()-t1:.1f}s)")
    _loaded = True
    print(f"[LP-MuseTalk] Tayyor! ({time.time()-t0:.1f}s)")


def ensure_loaded():
    if _loaded:
        return
    with _lock:
        if not _loaded:
            _load()


def warmup():
    """Birinchi inference sekin — startupda bir marta isitib qo'yish."""
    ensure_loaded()
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
        "-t", "0.5", "-ar", "16000", "-ac", "1", tmp.name,
    ], capture_output=True)
    t = time.time()
    musetalk_infer(tmp.name, str(VID_OUT_DIR / "_warmup.mp4"))
    for p in (tmp.name, str(VID_OUT_DIR / "_warmup.mp4")):
        try:
            os.remove(p)
        except Exception:
            pass
    print(f"[LP-MuseTalk] Warmup: {time.time()-t:.1f}s")


def musetalk_infer(wav_path: str, out_mp4: str, fps: int = 25) -> bool:
    import torch
    import cv2
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor
    from musetalk.utils.utils import datagen
    from musetalk.utils.blending import get_image_blending

    ensure_loaded()

    try:
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
