"""Avatar CRUD endpointlari (/api/avatars). Yozish/qurish — admin himoyasi bilan."""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import require_admin
from app.core.paths import avatar_idle_file, avatar_portrait_file
from app.schemas.avatar import AvatarCreate, AvatarUpdate
from app.services import avatar_store, idle, jobs

# DIQQAT: og'ir servislar (`face` → insightface, `musetalk` → torch, `preprocess`)
# handler ICHIDA import qilinadi — `create_app()` yengil muhitda import bo'lishi uchun.

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/avatars", tags=["avatars"])

# Admin himoyasi (yozish/qurish endpointlari uchun). GET (o'qish) public qoladi.
Admin = Depends(require_admin)

# Yuklash chegaralari.
MAX_PHOTO_BYTES = 12 * 1024 * 1024          # 12 MB
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.get("")
def list_avatars():
    return {"avatars": avatar_store.list_avatars()}


@router.get("/{avatar_id}")
def get_avatar(avatar_id: str):
    a = avatar_store.get_avatar(avatar_id)
    if not a:
        raise HTTPException(404, "Avatar topilmadi")
    return a


@router.post("")
def create_avatar(data: AvatarCreate, _: bool = Admin):
    # by_alias → Portrait.from_ "from" bo'lib yoziladi (frontend kutgan shakl).
    return avatar_store.create_avatar(data.model_dump(by_alias=True))


@router.put("/{avatar_id}")
def update_avatar(avatar_id: str, data: AvatarUpdate, _: bool = Admin):
    # exclude_unset → faqat klient yuborgan maydonlar yangilanadi (qisman).
    patch = data.model_dump(by_alias=True, exclude_unset=True)
    a = avatar_store.update_avatar(avatar_id, patch)
    if not a:
        raise HTTPException(404, "Avatar topilmadi")
    return a


@router.delete("/{avatar_id}")
def delete_avatar(avatar_id: str, _: bool = Admin):
    if not avatar_store.delete_avatar(avatar_id):
        raise HTTPException(404, "Avatar topilmadi")
    return {"deleted": avatar_id}


@router.post("/{avatar_id}/photo")
async def upload_photo(avatar_id: str, file: UploadFile = File(...), _: bool = Admin):
    """Portret rasmini yuklaydi, yuzni tekshiradi va source/portrait.jpg ga saqlaydi.

    Avatar avval mavjud bo'lishi shart (saqlangan bo'lishi kerak). Yuz validatsiyasi
    o'tmasa 422 qaytadi va rasm SAQLANMAYDI.
    """
    if avatar_store.get_avatar(avatar_id) is None:
        raise HTTPException(404, "Avatar topilmadi — avval avatarni saqlang")
    if file.content_type not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(415, "Faqat JPG, PNG yoki WebP rasm qabul qilinadi")

    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, f"Rasm juda katta (maksimum {MAX_PHOTO_BYTES // (1024 * 1024)} MB)")

    from app.services import face
    result = face.validate_portrait(data)
    if not result["ok"]:
        raise HTTPException(422, result["error"])

    # Validatsiyadan o'tdi — JPG sifatida saqlaymiz (idle generatsiya kirishi).
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    dest = avatar_portrait_file(avatar_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), img, [cv2.IMWRITE_JPEG_QUALITY, 95])

    avatar = avatar_store.set_photo(avatar_id, True)
    return {"ok": True, "avatar": avatar, "face": result["face"],
            "width": result["width"], "height": result["height"]}


@router.get("/{avatar_id}/photo")
def get_photo(avatar_id: str):
    """Saqlangan portret rasmini qaytaradi (editor preview uchun)."""
    path = avatar_portrait_file(avatar_id)
    if not path.is_file():
        raise HTTPException(404, "Portret yuklanmagan")
    return FileResponse(str(path), media_type="image/jpeg")


@router.post("/{avatar_id}/build-idle")
def build_idle(avatar_id: str, _: bool = Admin):
    """Idle (blink) video generatsiyani fon job sifatida boshlaydi.

    Portret yuklangan bo'lishi shart. Holatni `GET /{id}` build maydonidan kuzating.
    """
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise HTTPException(404, "Avatar topilmadi")
    if not av.get("hasPhoto") or not avatar_portrait_file(avatar_id).is_file():
        raise HTTPException(409, "Avval portret rasm yuklang")
    if jobs.is_running(avatar_id):
        raise HTTPException(409, "Generatsiya allaqachon ketmoqda")

    started = jobs.start(avatar_id, "idle_gen", lambda: idle.generate_idle(avatar_id))
    if not started:
        raise HTTPException(409, "Generatsiya allaqachon ketmoqda")
    return {"ok": True, "state": "processing", "stage": "idle_gen"}


@router.post("/{avatar_id}/build-musetalk")
def build_musetalk(avatar_id: str, _: bool = Admin):
    """Idle videodan MuseTalk artefakt (latents/coords/mask) generatsiyasini boshlaydi.

    Idle video oldindan yaratilgan bo'lishi shart. Holatni `GET /{id}/build`
    (stage="musetalk_prep") orqali kuzating.
    """
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise HTTPException(404, "Avatar topilmadi")
    if not avatar_idle_file(avatar_id).is_file():
        raise HTTPException(409, "Avval idle video yarating")
    if jobs.is_running(avatar_id):
        raise HTTPException(409, "Generatsiya allaqachon ketmoqda")

    from app.services import musetalk, preprocess

    def _rebuild():
        # Artefakt ALOHIDA jarayonda (subprocess) quriladi — u o'z keshini tozalaydi,
        # lekin BU ishlab turgan serverning xotira keshini emas. Shuning uchun
        # subprocess tugagach SERVER keshini bo'shatamiz va yangisini qayta yuklaymiz,
        # aks holda server eski (harakatsiz) artefaktni berishda davom etadi.
        preprocess.preprocess_avatar_subprocess(avatar_id)
        musetalk.invalidate(avatar_id)
        try:
            _av = avatar_store.get_avatar(avatar_id)
            musetalk.preload_artifact(avatar_id, musetalk.use_max_dim(_av))
        except Exception:
            pass
        # Bosh-harakat primitivlarini ham AVTOMATIK quramiz — yangi avatar darrov
        # Video Studiyada bosh harakati bilan tayyor bo'lsin (qo'lda alohida qadam
        # shart emas). Xato bo'lsa avatar baribir ishlaydi (faqat motionsiz).
        if avatar_portrait_file(avatar_id).is_file():
            try:
                idle.generate_motion_clips(avatar_id)
                preprocess.preprocess_motion_all_subprocess(avatar_id)
                musetalk.invalidate(avatar_id)
                avatar_store.set_motion(avatar_id, True)
            except Exception as e:  # noqa: BLE001
                log.warning("[build-musetalk] motion auto-build o'tkazildi (xato): %s", e)

    started = jobs.start(avatar_id, "musetalk_prep", _rebuild)
    if not started:
        raise HTTPException(409, "Generatsiya allaqachon ketmoqda")
    return {"ok": True, "state": "processing", "stage": "musetalk_prep"}


@router.post("/{avatar_id}/build-motion")
def build_motion(avatar_id: str, _: bool = Admin):
    """Bosh-harakat primitivlarini (nod/tilt/turn/lean/neutral) quradi (2-faza).

    Avatar artefakti tayyor bo'lishi kerak (idle + MuseTalk). Klip generatsiya
    (LivePortrait) + preprocess (MuseTalk) — uzoq fon job."""
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise HTTPException(404, "Avatar topilmadi")
    if not avatar_portrait_file(avatar_id).is_file():
        raise HTTPException(409, "Avval portret rasm yuklang")
    if not av.get("real"):
        raise HTTPException(409, "Avval avatar modelini quring (Idle + Artefakt)")
    if jobs.is_running(avatar_id):
        raise HTTPException(409, "Generatsiya allaqachon ketmoqda")

    from app.services import musetalk, preprocess

    def _job():
        idle.generate_motion_clips(avatar_id)            # LivePortrait kliplar
        preprocess.preprocess_motion_all_subprocess(avatar_id)  # MuseTalk artefaktlar
        musetalk.invalidate(avatar_id)                   # kesh (motion) yangilansin
        avatar_store.set_motion(avatar_id, True)

    started = jobs.start(avatar_id, "motion", _job)
    if not started:
        raise HTTPException(409, "Generatsiya allaqachon ketmoqda")
    return {"ok": True, "state": "processing", "stage": "motion"}


@router.get("/{avatar_id}/build")
def build_status(avatar_id: str):
    """Joriy generatsiya holati (frontend polling uchun)."""
    av = avatar_store.get_avatar(avatar_id)
    if av is None:
        raise HTTPException(404, "Avatar topilmadi")
    build = av.get("build") or {"state": "idle", "stage": None, "error": None}
    build["running"] = jobs.is_running(avatar_id)
    return build


@router.get("/{avatar_id}/idle")
def get_idle(avatar_id: str):
    """Generatsiya qilingan idle videosini qaytaradi (editor preview uchun)."""
    path = avatar_idle_file(avatar_id)
    if not path.is_file():
        raise HTTPException(404, "Idle video hali yaratilmagan")
    return FileResponse(str(path), media_type="video/mp4")
