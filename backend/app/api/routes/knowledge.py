"""Bilim bazasi (RAG) endpointlari — /api/avatars/{id}/knowledge. Hammasi admin."""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import require_admin
from app.services import avatar_store, knowledge

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/avatars/{avatar_id}/knowledge", tags=["knowledge"])
Admin = Depends(require_admin)

MAX_DOC_BYTES = 2 * 1024 * 1024          # 2 MB (txt/md)
ALLOWED_DOC_SUFFIX = (".txt", ".md", ".markdown")


def _require_avatar(avatar_id: str):
    if avatar_store.get_avatar(avatar_id) is None:
        raise HTTPException(404, "Avatar topilmadi")


class FaqRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=4000)


@router.get("")
def get_knowledge(avatar_id: str, _: bool = Admin):
    _require_avatar(avatar_id)
    return knowledge.list_knowledge(avatar_id)


@router.post("/upload")
async def upload_source(avatar_id: str, file: UploadFile = File(...), _: bool = Admin):
    _require_avatar(avatar_id)
    name = (file.filename or "").lower()
    if not name.endswith(ALLOWED_DOC_SUFFIX):
        raise HTTPException(415, "Faqat .txt yoki .md fayl qabul qilinadi")
    data = await file.read()
    if len(data) > MAX_DOC_BYTES:
        raise HTTPException(413, f"Hujjat juda katta (maks {MAX_DOC_BYTES // (1024*1024)} MB)")
    text = data.decode("utf-8", errors="replace")
    try:
        res = knowledge.add_file_source(avatar_id, file.filename or "manba.txt", text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Embedding xatosi: {e}")
    return {"ok": True, **res}


@router.post("/faq")
def add_faq(avatar_id: str, req: FaqRequest, _: bool = Admin):
    _require_avatar(avatar_id)
    try:
        res = knowledge.add_faq(avatar_id, req.question, req.answer)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Embedding xatosi: {e}")
    return {"ok": True, **res}


@router.delete("/source/{src_id}")
def del_source(avatar_id: str, src_id: str, _: bool = Admin):
    _require_avatar(avatar_id)
    if not knowledge.delete_source(avatar_id, src_id):
        raise HTTPException(404, "Manba topilmadi")
    return {"deleted": src_id}


@router.delete("/faq/{faq_id}")
def del_faq(avatar_id: str, faq_id: str, _: bool = Admin):
    _require_avatar(avatar_id)
    if not knowledge.delete_faq(avatar_id, faq_id):
        raise HTTPException(404, "FAQ topilmadi")
    return {"deleted": faq_id}
