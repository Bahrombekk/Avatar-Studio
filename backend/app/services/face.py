"""Portret rasm validatsiyasi — insightface (buffalo_l) bilan yuz tekshiruvi.

Avatar yaratishda foydalanuvchi yuklagan rasm idle generatsiya (LivePortrait) va
MuseTalk preprocessing uchun yaroqli bo'lishi shart. Bu yerda rasmni dekod qilib,
o'lcham va yuz sifatini tekshiramiz — yaroqsiz rasm pipeline'ni keyinroq buzmaydi.

Tekshiruvlar:
    1. Rasm dekod bo'ladimi (buzilmagan JPG/PNG)
    2. O'lcham kamida MIN_SIDE × MIN_SIDE
    3. Aniq BITTA yuz (0 yoki >1 → rad)
    4. Yuz yetarlicha katta (kichik selfi/olis yuz rad etiladi)
    5. Yuz old tomondan (pose mavjud bo'lsa: yaw/pitch chegarada)

Model lazy yuklanadi (birinchi so'rovda) — import vaqtida emas.
"""
import threading

import cv2
import numpy as np

MIN_SIDE = 512               # rasmning eng qisqa tomoni (px)
MIN_FACE_RATIO = 0.15        # yuz qutisi qisqa tomoni / rasm qisqa tomoni
MIN_DET_SCORE = 0.5          # insightface aniqlash ishonchi
MAX_YAW = 35.0               # gorizontal burilish (daraja)
MAX_PITCH = 30.0             # vertikal burilish (daraja)

_app = None
_lock = threading.Lock()


def _get_app():
    """FaceAnalysis (buffalo_l) singleton — faqat aniqlash + poza moduli, CPU."""
    global _app
    if _app is not None:
        return _app
    with _lock:
        if _app is None:
            from insightface.app import FaceAnalysis
            app = FaceAnalysis(
                name="buffalo_l",
                allowed_modules=["detection", "landmark_3d_68"],
                providers=["CPUExecutionProvider"],
            )
            app.prepare(ctx_id=-1, det_size=(640, 640))
            _app = app
    return _app


def validate_portrait(img_bytes: bytes) -> dict:
    """Rasm baytlarini tekshiradi.

    Qaytaradi: {"ok": bool, "error": str|None, "width", "height", "face": {...}}
    `face` faqat ok=True bo'lganda to'liq bo'ladi.
    """
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return {"ok": False, "error": "Rasmni o'qib bo'lmadi (buzilgan yoki qo'llab-quvvatlanmaydigan format)."}

    h, w = img.shape[:2]
    short = min(h, w)
    if short < MIN_SIDE:
        return {"ok": False, "error": f"Rasm juda kichik: {w}×{h}. Kamida {MIN_SIDE}×{MIN_SIDE} bo'lishi kerak.",
                "width": w, "height": h}

    faces = _get_app().get(img)
    faces = [f for f in faces if getattr(f, "det_score", 0) >= MIN_DET_SCORE]
    if len(faces) == 0:
        return {"ok": False, "error": "Rasmda yuz topilmadi. Old tomondan, yorug' fonda suratga tushiring.",
                "width": w, "height": h}
    if len(faces) > 1:
        return {"ok": False, "error": f"Rasmda {len(faces)} ta yuz aniqlandi. Faqat bitta yuz bo'lishi kerak.",
                "width": w, "height": h}

    face = faces[0]
    x1, y1, x2, y2 = face.bbox
    fw, fh = float(x2 - x1), float(y2 - y1)
    if min(fw, fh) < MIN_FACE_RATIO * short:
        return {"ok": False, "error": "Yuz juda kichik. Yuz kadrning kattaroq qismini egallashi kerak.",
                "width": w, "height": h}

    yaw = pitch = None
    pose = getattr(face, "pose", None)
    if pose is not None and len(pose) >= 2:
        pitch, yaw = float(pose[0]), float(pose[1])
        if abs(yaw) > MAX_YAW or abs(pitch) > MAX_PITCH:
            return {"ok": False,
                    "error": "Yuz juda burilgan. To'g'ridan-to'g'ri kameraga qaragan surat kerak.",
                    "width": w, "height": h}

    return {
        "ok": True,
        "error": None,
        "width": w,
        "height": h,
        "face": {
            "bbox": [round(float(v), 1) for v in (x1, y1, x2, y2)],
            "det_score": round(float(face.det_score), 3),
            "yaw": round(yaw, 1) if yaw is not None else None,
            "pitch": round(pitch, 1) if pitch is not None else None,
        },
    }
