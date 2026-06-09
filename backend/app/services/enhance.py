"""GFPGAN GPU yuz tiklash — HD render sifati (offline Video Studiya).

MuseTalk og'izni 256x256'da yaratadi → kattalashganda yumshaydi. GFPGAN to'liq yuzni
512 sifatda tiklaydi (identiklikni saqlab). RTX GPU'da tez.

To'siqlar hal qilingan:
 - torchvision.transforms.functional_tensor olib tashlangan (yangi torch) → SHIM.
 - vazn: backend/checkpoints/gfpgan/GFPGANv1.4.pth.
GFPGANer LAZY yuklanadi (birinchi HD render'da). Har qanday xatoda kadr O'ZGARMAYDI
(render to'xtamaydi). RT_NO_GFPGAN=1 bilan butunlay o'chiriladi.
"""
import logging
import os
import sys
import threading
import types

log = logging.getLogger(__name__)
_lock = threading.Lock()
_restorer = None
_disabled = os.environ.get("RT_NO_GFPGAN") == "1"


def _gfpgan_weight():
    from app.core.paths import CHECKPOINTS_DIR
    return CHECKPOINTS_DIR / "gfpgan" / "GFPGANv1.4.pth"


def available() -> bool:
    return (not _disabled) and _gfpgan_weight().is_file()


def _apply_torchvision_shim():
    """basicsr/gfpgan eski torchvision API (functional_tensor) qidiradi — shim beramiz."""
    if "torchvision.transforms.functional_tensor" in sys.modules:
        return
    import torchvision.transforms.functional as _F
    m = types.ModuleType("torchvision.transforms.functional_tensor")
    m.rgb_to_grayscale = _F.rgb_to_grayscale
    sys.modules["torchvision.transforms.functional_tensor"] = m


def _get_restorer():
    global _restorer, _disabled
    if _restorer is not None or _disabled:
        return _restorer
    with _lock:
        if _restorer is not None or _disabled:
            return _restorer
        try:
            _apply_torchvision_shim()
            from gfpgan import GFPGANer
            wp = _gfpgan_weight()
            if not wp.is_file():
                log.warning("GFPGAN vazni yo'q: %s — o'chirildi", wp)
                _disabled = True
                return None
            _restorer = GFPGANer(model_path=str(wp), upscale=1, arch="clean",
                                 channel_multiplier=2, bg_upsampler=None)
            log.info("GFPGAN yuklandi (GPU yuz tiklash faol)")
        except Exception as e:  # noqa: BLE001
            log.warning("GFPGAN yuklab bo'lmadi → o'chirildi: %s", e)
            _disabled = True
            _restorer = None
    return _restorer


def restore_frame(bgr, blend: float = 0.7):
    """BGR kadr → yuz tiklangan BGR. Yuz topilmasa/xato bo'lsa asl kadr qaytadi.
    blend: tiklangan vs asl aralashmasi (flicker va ortiqcha silliqlikni kamaytiradi)."""
    r = _get_restorer()
    if r is None:
        return bgr
    try:
        import cv2
        _, _, out = r.enhance(bgr, has_aligned=False, only_center_face=True,
                              paste_back=True)
        if out is None:
            return bgr
        if out.shape != bgr.shape:
            out = cv2.resize(out, (bgr.shape[1], bgr.shape[0]),
                             interpolation=cv2.INTER_LANCZOS4)
        if blend < 0.999:
            out = cv2.addWeighted(out, blend, bgr, 1.0 - blend, 0)
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("restore xato (kadr o'tkazildi): %s", e)
        return bgr
