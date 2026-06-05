"""Tayyor javoblar (/api/canned) — oldindan generatsiya qilingan Q&A videolari.

Admin savol(lar)+javob beradi → video Video Studiya quvuri bilan quriladi. Real-time'da
foydalanuvchi savoli mos kelsa, shu video darrov o'ynaladi. Yozish — ADMIN himoyasi;
video faylni berish (GET) public (real-time klient o'ynashi uchun)."""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import require_admin
from app.core.paths import canned_file
from app.services import canned

router = APIRouter(prefix="/api/canned", tags=["canned"])
Admin = Depends(require_admin)


class CannedRequest(BaseModel):
    avatar_id: str
    questions: List[str] = Field(default_factory=list)
    mode: Literal["script", "gpt"] = "script"
    text: str = Field("", max_length=4000)
    prompt: str = Field("", max_length=2000)
    voice: Optional[str] = None
    hd: bool = False
    title: str = Field("", max_length=120)


class QuestionsUpdate(BaseModel):
    questions: List[str] = Field(default_factory=list)


@router.post("")
def create_canned(req: CannedRequest, _: bool = Admin):
    try:
        cid = canned.start_generate(
            avatar_id=req.avatar_id, questions=req.questions, text=req.text,
            voice=req.voice, mode=req.mode, prompt=req.prompt, title=req.title, hd=req.hd,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "canned_id": cid, "state": "processing"}


@router.get("")
def list_canned(_: bool = Admin):
    return {"canned": canned.list_canned()}


@router.get("/{cid}/status")
def canned_status(cid: str, _: bool = Admin):
    return canned.get_status(cid)


@router.put("/{cid}/questions")
def edit_questions(cid: str, req: QuestionsUpdate, _: bool = Admin):
    if not canned.update_questions(cid, req.questions):
        raise HTTPException(404, "Topilmadi")
    return {"ok": True, "id": cid}


@router.delete("/{cid}")
def delete_canned(cid: str, _: bool = Admin):
    if not canned.delete_canned(cid):
        raise HTTPException(404, "Topilmadi")
    return {"deleted": cid}


@router.get("/{cid}/video")
def get_canned_video(cid: str):
    """Tayyor javob videosi (real-time klient o'ynaydi). Public — id taxminlanmas."""
    if "/" in cid or "\\" in cid:
        raise HTTPException(404, "Topilmadi")
    f = canned_file(cid)
    if not f.is_file():
        raise HTTPException(404, "Video topilmadi")
    return FileResponse(str(f), media_type="video/mp4", filename=f"{cid}.mp4")
