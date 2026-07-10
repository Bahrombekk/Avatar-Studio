"""Bilim bazasi (RAG) endpointlari — /api/avatars/{id}/knowledge. Hammasi admin."""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import require_admin
from app.services import avatar_store, knowledge

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/avatars/{avatar_id}/knowledge", tags=["knowledge"])
Admin = Depends(require_admin)


class SuggestFaqRequest(BaseModel):
    n: int = Field(default=8, ge=1, le=15)


class FaqPair(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=4000)


class FaqBulkRequest(BaseModel):
    faqs: list[FaqPair] = Field(min_length=1, max_length=30)


class TranslateRequest(BaseModel):
    langs: list[str] = Field(default_factory=lambda: ["ru", "en"])

MAX_DOC_BYTES = 2 * 1024 * 1024          # 2 MB (txt/md)
ALLOWED_DOC_SUFFIX = (".txt", ".md", ".markdown")


def _require_avatar(avatar_id: str):
    if avatar_store.get_avatar(avatar_id) is None:
        raise HTTPException(404, "Avatar topilmadi")


class FaqRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=4000)


class SourceUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=2_000_000)
    name: str | None = Field(default=None, max_length=200)


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


@router.get("/source/{src_id}")
def get_source(avatar_id: str, src_id: str, _: bool = Admin):
    _require_avatar(avatar_id)
    data = knowledge.get_source(avatar_id, src_id)
    if data is None:
        raise HTTPException(404, "Manba topilmadi")
    return data


@router.put("/source/{src_id}")
def put_source(avatar_id: str, src_id: str, req: SourceUpdate, _: bool = Admin):
    _require_avatar(avatar_id)
    try:
        res = knowledge.update_source(avatar_id, src_id, req.text, req.name)
    except KeyError:
        raise HTTPException(404, "Manba topilmadi")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Embedding xatosi: {e}")
    return {"ok": True, **res}


@router.put("/faq/{faq_id}")
def put_faq(avatar_id: str, faq_id: str, req: FaqRequest, _: bool = Admin):
    _require_avatar(avatar_id)
    try:
        ok = knowledge.update_faq(avatar_id, faq_id, req.question, req.answer)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Embedding xatosi: {e}")
    if not ok:
        raise HTTPException(404, "FAQ topilmadi")
    return {"ok": True}


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


# ── GPT amallari (avto-FAQ + tarjima) ──
@router.post("/source/{src_id}/suggest-faqs")
def suggest_faqs(avatar_id: str, src_id: str, req: SuggestFaqRequest, _: bool = Admin):
    """Manba matnidan FAQ nomzodlari (SAQLANMAYDI — admin tanlaydi)."""
    _require_avatar(avatar_id)
    if knowledge.get_source(avatar_id, src_id) is None:
        raise HTTPException(404, "Manba topilmadi")
    from app.services import kb_ai
    try:
        cands = kb_ai.suggest_faqs(avatar_id, src_id, n=req.n)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"GPT xatosi: {e}")
    return {"candidates": cands}


@router.post("/faq/bulk")
def add_faq_bulk(avatar_id: str, req: FaqBulkRequest, _: bool = Admin):
    """Bir nechta FAQ'ni birato'la qo'shadi (tanlangan nomzodlar)."""
    _require_avatar(avatar_id)
    from app.services import kb_ai
    pairs = [{"q": f.question, "a": f.answer} for f in req.faqs]
    try:
        res = kb_ai.add_faqs_bulk(avatar_id, pairs)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Embedding xatosi: {e}")
    return {"ok": True, **res}


@router.post("/translate")
def translate(avatar_id: str, req: TranslateRequest, _: bool = Admin):
    """Manba+FAQ'larni RU/EN ga aynan tarjima + embed (fon-job)."""
    _require_avatar(avatar_id)
    from app.services import kb_ai
    started = kb_ai.start_translation(avatar_id, req.langs)
    if not started:
        raise HTTPException(409, "Tarjima allaqachon ishlamoqda")
    return {"ok": True, **kb_ai.translation_status(avatar_id)}


@router.get("/translate/status")
def translate_status(avatar_id: str, _: bool = Admin):
    _require_avatar(avatar_id)
    from app.services import kb_ai
    return kb_ai.translation_status(avatar_id)
