"""Portretdan idle video yaratish — blink + YUMSHOQ BOSH HARAKATI (parametrlanadigan CLI).

Avatar "tirik" his bersin uchun: ko'z pirpiratish (blink) + sekin, kichik amplitudali
bosh tebranishi (yaw/pitch/roll). Harakat loop-silliq (integer harmonikalar → klip
oxiri boshiga mos, sakrash yo'q) va amplituda kichik (sifat/identiklik buzilmaydi).
Amplitudalar CLI orqali sozlanadi; 0 berilsa o'sha o'q qotadi (eski xulq).

Ishlatish (liveportrait muhiti):
    python gen_idle.py --source /path/portrait.jpg --out /path/idle.mp4 \
        --fps 25 --blink-every 4 --duration 4 \
        --head-yaw 2.2 --head-pitch 1.3 --head-roll 0.9
"""
import argparse
import math
import os
import subprocess
import sys

import cv2
import numpy as np
import torch
import tyro

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Portativ rejim: gradio faqat web-UI uchun kerak; idle generatsiya unga
#    muhtoj emas (gr faqat xato yo'lida chaqiriladi). Agar gradio o'rnatilmagan
#    bo'lsa (bundle qilingan avatar muhiti), yengil stub bilan importni o'tkazamiz.
import types as _types
try:
    import gradio  # noqa: F401
except ImportError:
    class _GradioStub(_types.ModuleType):
        class Error(Exception):
            def __init__(self, *a, **k):
                super().__init__(*(a[:1] or ("gradio stub error",)))
        Warning = Error

        def __getattr__(self, _name):
            def _noop(*a, **k):
                return None
            return _noop
    sys.modules["gradio"] = _GradioStub("gradio")

from src.gradio_pipeline import GradioPipeline
from src.config.crop_config import CropConfig
from src.config.argument_config import ArgumentConfig
from src.config.inference_config import InferenceConfig
from src.utils.crop import paste_back
from src.utils.retargeting_utils import calc_eye_close_ratio
from src.utils.camera import get_rotation_matrix

BLINK_HALF = 3      # blink yarim davomiyligi (kadr): jami ~6-7 kadr
CLOSED = 0.02       # blink eng yopiq nuqtasi (ko'z ochiqlik nisbati)
BLINK_SPAN = 3.6    # blink tezligi (kichikroq = tezroq ochilib-yopilish; oldin 4 edi → ~10% tez)


def head_offsets(i, n, amp_pitch, amp_yaw, amp_roll):
    """i-kadr uchun bosh burchak ofsetlari (gradus).

    KO'P HARMONIKA (1,2,3,5 sikl) aralashmasi → harakat tezligi O'ZGARUVCHAN
    (goh sekin suriladi, goh tez kichik harakat) — bir tekis "robotik" temp emas,
    tabiiy. Eksenlar (yaw/pitch/roll) har xil faza/og'irlik → desinxron harakatlanadi.
    Hamma chastota BUTUN son → klip loop qilinganda chetda silliq (qiymat+hosila mos).
    Og'irliklar yig'indisi ~1 → amplituda chegarada qoladi (sifat/identiklik buzilmaydi).
    """
    ph = 2.0 * math.pi * i / max(1, n)
    dyaw = amp_yaw * (0.50 * math.sin(ph)
                      + 0.26 * math.sin(2 * ph + 1.3)
                      + 0.15 * math.sin(3 * ph + 2.1)
                      + 0.09 * math.sin(5 * ph + 0.6))
    dpitch = amp_pitch * (0.48 * math.sin(ph + 0.9)
                          + 0.28 * math.sin(2 * ph + 2.4)
                          + 0.15 * math.sin(3 * ph + 0.3)
                          + 0.09 * math.sin(5 * ph + 1.7))
    droll = amp_roll * (0.62 * math.sin(ph + 1.5) + 0.38 * math.sin(2 * ph + 0.2))
    return dpitch, dyaw, droll


# Harakat primitivlari — bitta harakat: neytral → peak → neytral (chetlarda 0).
# Render'da segment trigger'iga ulanadi (hammasi neytralda boshlanib-tugaydi → silliq).
# intensity (0..1) amplitudani masshtablaydi. Maks gradus xavfsiz chegarada.
_PRIMITIVE_MAX = {
    "nod":          (11.0, 0.0, 0.0),   # pitch — bosh irg'ash (past-tepa)
    "lean_forward": (5.5, 0.0, 0.0),    # oldinga egilish (pitch) — urg'u uchun yumshoqroq
    "tilt_left":    (0.0, 0.0, -11.0),  # roll — chapga qiyshayish
    "tilt_right":   (0.0, 0.0, 11.0),
    "turn_left":    (0.0, -15.0, 0.0),  # yaw — chapga burilish
    "turn_right":   (0.0, 15.0, 0.0),
    # ── Yangi turlar ──
    "lean_back":    (-6.0, 0.0, 0.0),    # orqaga/tepaga egilish (pitch MANFIY — o'ylash)
    "look_up":      (-9.0, 0.0, 0.0),    # tepaga qarash (eslash/o'ylab turish)
    "look_down":    (7.0, 0.0, 0.0),     # pastga qarash (yumshoq — yakun/kamtarlik)
    "shake":        (0.0, 11.0, 0.0),    # "yo'q" — yaw tebranish (oscillation, pastda)
}
# Tebranuvchi (oscillation) primitivlar — peak emas, env ichida sin to'lqin.
# qiymat = yarim-sikllar soni (1.5 → o'ng-chap-o'ng, chetlarda 0 ga qaytadi).
_OSC = {"shake": 1.5}


def primitive_offsets(i, n, mtype, intensity):
    """Primitiv harakat ofseti (gradus). env = sin(pi*p): chetlarda 0, o'rtada peak →
    neytraldan chiqib neytralga qaytadi (silliq ulash uchun)."""
    pk = _PRIMITIVE_MAX.get(mtype)
    if not pk:
        return 0.0, 0.0, 0.0
    p = i / max(1, n - 1)
    env = math.sin(math.pi * p) * max(0.0, min(1.0, intensity))
    osc = _OSC.get(mtype)
    if osc:
        # tebranuvchi harakat (shake "yo'q"): env chetlarda 0 → silliq boshlanib-tugaydi
        w = math.sin(2.0 * math.pi * osc * p)
        return pk[0] * env * w, pk[1] * env * w, pk[2] * env * w
    return pk[0] * env, pk[1] * env, pk[2] * env


def partial_fields(target_class, kwargs):
    return target_class(**{k: v for k, v in kwargs.items() if hasattr(target_class, k)})


def build_pipeline():
    sys.argv = ["app.py"]  # tyro ArgumentConfig default qiymatlar bilan
    args = tyro.cli(ArgumentConfig)
    inference_cfg = partial_fields(InferenceConfig, args.__dict__)
    crop_cfg = partial_fields(CropConfig, args.__dict__)
    return GradioPipeline(inference_cfg=inference_cfg, crop_cfg=crop_cfg, args=args)


def blink_centers(n_frames, fps, blink_every_sec):
    """blinkRate (sekund) ga ko'ra blink markaz kadrlarini klip bo'ylab teng taqsimlaydi.

    Klip MuseTalk'da loop qilinadi, shuning uchun blinklar chetlarda emas, ichkarida
    joylashtiriladi (silliq loop uchun). Kamida bitta blink kafolatlanadi.
    """
    duration = n_frames / fps
    n_blinks = max(1, int(round(duration / max(0.1, blink_every_sec))))
    # (i + 0.5) / n_blinks → har blokning markazi (chetlardan uzoq).
    return [int(round((i + 0.5) / n_blinks * n_frames)) for i in range(n_blinks)]


def eye_ratio_at(frame_idx, source_ratio, centers):
    """Asosan ochiq (source_ratio); blink markazlarida ~CLOSED gacha tushib qaytadi."""
    r = source_ratio
    for c in centers:
        d = abs(frame_idx - c)
        if d <= BLINK_HALF:
            k = max(0.0, 1.0 - d / BLINK_SPAN)   # ~10% tezroq blink
            r = min(r, source_ratio * (1 - k) + CLOSED * k)
    return float(r)


@torch.no_grad()
def generate(source, out, fps, blink_every, duration,
             head_yaw=2.8, head_pitch=1.6, head_roll=1.1,
             motion_type="idle", intensity=0.6, gp=None):
    n_frames = max(1, int(round(duration * fps)))
    # motion turlari:
    #  - motion primitiv (nod/tilt/turn/lean): bitta harakat, neytral→peak→neytral, BLINKSIZ
    #  - neutral: filler — yumshoq idle, lekin chetlarda source-pozaga qaytadi (envelope),
    #    blink BOR (jim turganda ko'z pirpiraydi). Primitivlar bilan bir xil chegara → silliq ulanadi.
    #  - idle: eski to'liq periodik idle (loop)
    is_motion = motion_type in _PRIMITIVE_MAX
    is_neutral = motion_type == "neutral"
    centers = [] if is_motion else blink_centers(n_frames, fps, blink_every)

    if gp is None:
        gp = build_pipeline()
    w = gp.live_portrait_wrapper
    device = w.device

    f_s, x_s, R_s, R_d, x_s_info, source_lmk, crop_M_c2o, mask_ori, img_rgb = \
        gp.prepare_retargeting_image(source, 0.0, 0.0, 0.0, 2.3, flag_do_crop=True)

    x_s = x_s.to(device); f_s = f_s.to(device); R_s = R_s.to(device)
    x_c_s = x_s_info['kp'].to(device)
    delta = x_s_info['exp'].to(device)
    scale = x_s_info['scale'].to(device)
    t = x_s_info['t'].to(device)
    # Manba bosh burchaklari (gradus) — har kadr shularga kichik ofset qo'shamiz.
    p0 = x_s_info['pitch'].to(device)
    y0 = x_s_info['yaw'].to(device)
    r0 = x_s_info['roll'].to(device)

    source_ratio = float(calc_eye_close_ratio(source_lmk[None])[0][0])
    print(f"[idle] source_eye_ratio={source_ratio:.4f}, {n_frames} kadr, blink kadrlar: {centers}; "
          f"bosh harakati yaw={head_yaw} pitch={head_pitch} roll={head_roll}")

    H, W = img_rgb.shape[:2]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    # H.264 (libx264) ffmpeg orqali yozamiz — BRAUZER o'ynashi uchun shart.
    # cv2.VideoWriter "mp4v" (mpeg4 part 2) brauzerlarda ishlamaydi → idle ko'rinmaydi.
    proc = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "veryfast",
        "-movflags", "+faststart", out,
    ], stdin=subprocess.PIPE)

    for i in range(n_frames):
        # Bosh pozasi: primitiv (bitta harakat) yoki idle (yumshoq loop tebranish).
        if is_motion:
            dp, dy, dr = primitive_offsets(i, n_frames, motion_type, intensity)
        elif is_neutral:
            e = math.sin(math.pi * (i / max(1, n_frames - 1)))   # chetlarda 0 → source poza
            bp, by, br = head_offsets(i, n_frames, head_pitch, head_yaw, head_roll)
            dp, dy, dr = bp * e, by * e, br * e
        else:
            dp, dy, dr = head_offsets(i, n_frames, head_pitch, head_yaw, head_roll)
        R_d_new = get_rotation_matrix(p0 + dp, y0 + dy, r0 + dr)
        x_d = scale * (x_c_s @ R_d_new + delta) + t
        # Ko'z pirpiratish (blink) — bosh pozasidan mustaqil qo'shimcha delta.
        ratio = eye_ratio_at(i, source_ratio, centers)
        if abs(ratio - source_ratio) > 1e-4:
            comb = w.calc_combined_eye_ratio([[ratio]], source_lmk)
            eyes_delta = w.retarget_eye(x_s, comb)
            x_d = x_d + eyes_delta
        x_d = w.stitching(x_s, x_d)
        out_frame = w.warp_decode(f_s, x_s, x_d)
        frame = w.parse_output(out_frame['out'])[0]
        full = paste_back(frame, crop_M_c2o, img_rgb, mask_ori)
        bgr = cv2.cvtColor(full, cv2.COLOR_RGB2BGR)
        proc.stdin.write(np.ascontiguousarray(bgr, dtype=np.uint8).tobytes())

    proc.stdin.close()
    proc.wait()
    if not (os.path.isfile(out) and os.path.getsize(out) > 0):
        raise RuntimeError(f"Idle video yozilmadi: {out}")
    print(f"[idle] saqlandi: {out} ({W}x{H}, {n_frames} kadr)")


def main():
    p = argparse.ArgumentParser(description="Portretdan idle blink video yaratish")
    p.add_argument("--source", required=True, help="Manba portret rasm yo'li")
    p.add_argument("--out", default="", help="Chiqish mp4 yo'li (--all-motion'siz majburiy)")
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--blink-every", type=float, default=4.0, help="Blink oralig'i (sekund)")
    p.add_argument("--duration", type=float, default=4.0, help="Klip davomiyligi (sekund)")
    p.add_argument("--head-yaw", type=float, default=2.8, help="Bosh chap-o'ng amplitudasi (gradus, 0=qotgan)")
    p.add_argument("--head-pitch", type=float, default=1.6, help="Bosh yuqori-past amplitudasi (gradus)")
    p.add_argument("--head-roll", type=float, default=1.1, help="Bosh egilish amplitudasi (gradus)")
    p.add_argument("--motion-type", default="idle",
                   help="idle | nod | tilt_left | tilt_right | turn_left | turn_right | lean_forward")
    p.add_argument("--intensity", type=float, default=0.6, help="Primitiv harakat kuchi (0..1)")
    p.add_argument("--all-motion", action="store_true",
                   help="Barcha harakat primitivlarini bir LivePortrait yuklashda yaratish")
    p.add_argument("--out-dir", default="", help="--all-motion uchun chiqish papkasi (motion/)")
    a = p.parse_args()
    if not os.path.isfile(a.source):
        print(f"XATO: manba topilmadi: {a.source}", file=sys.stderr)
        sys.exit(2)

    if a.all_motion:
        if not a.out_dir:
            print("XATO: --all-motion uchun --out-dir kerak", file=sys.stderr)
            sys.exit(2)
        os.makedirs(a.out_dir, exist_ok=True)
        gp = build_pipeline()   # bir marta yuklaymiz
        # neutral filler — uzunroq (2.4s), boshqa primitivlar — 1.2s.
        # Filler amplitudasi sezilarli bo'lsin (harakatsiz segmentlarda ham bosh
        # tabiiy suriladi) → defaultdan kattaroq: yaw 4.2 / pitch 2.4 / roll 1.7.
        generate(a.source, os.path.join(a.out_dir, "neutral.mp4"), a.fps, a.blink_every, 2.4,
                 head_yaw=4.2, head_pitch=2.4, head_roll=1.7,
                 motion_type="neutral", gp=gp)
        for mt in ["nod", "tilt_left", "tilt_right", "turn_left", "turn_right", "lean_forward",
                   "lean_back", "look_up", "look_down", "shake"]:
            generate(a.source, os.path.join(a.out_dir, f"{mt}.mp4"), a.fps, a.blink_every, 1.2,
                     motion_type=mt, intensity=0.9, gp=gp)   # 0.7 → 0.9: sezilarliroq harakat
        print("ALL-MOTION-OK")
        return

    if not a.out:
        print("XATO: --out kerak (yoki --all-motion)", file=sys.stderr)
        sys.exit(2)
    generate(a.source, a.out, a.fps, a.blink_every, a.duration,
             head_yaw=a.head_yaw, head_pitch=a.head_pitch, head_roll=a.head_roll,
             motion_type=a.motion_type, intensity=a.intensity)


if __name__ == "__main__":
    main()
