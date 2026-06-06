"""Video Studiya endpointlari (/api/studio) — offline HD render (HeyGen uslubi).

Render boshlash/ro'yxat/holat/o'chirish — ADMIN himoyasi. Video faylni berish (GET)
public (id taxmin qilib bo'lmaydigan 12-hex; avatar idle/photo kabi).
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import require_admin
from app.core.paths import render_file
from app.services import render

router = APIRouter(prefix="/api/studio", tags=["studio"])
Admin = Depends(require_admin)


class RenderRequest(BaseModel):
    avatar_id: str
    mode: Literal["script", "gpt"] = "script"
    text: str = Field("", max_length=4000)
    prompt: str = Field("", max_length=2000)
    voice: Optional[str] = None
    hd: bool = False
    title: str = Field("", max_length=120)


@router.post("/render")
def create_render(req: RenderRequest, _: bool = Admin):
    try:
        rid = render.start_render(
            avatar_id=req.avatar_id, text=req.text, voice=req.voice,
            mode=req.mode, prompt=req.prompt, hd=req.hd, title=req.title,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "render_id": rid, "state": "processing"}


@router.get("/renders")
def list_renders(_: bool = Admin):
    return {"renders": render.list_renders()}


@router.get("/render/{render_id}/status")
def render_status(render_id: str, _: bool = Admin):
    return render.render_status(render_id)


@router.delete("/render/{render_id}")
def delete_render(render_id: str, _: bool = Admin):
    if not render.delete_render(render_id):
        raise HTTPException(404, "Render topilmadi")
    return {"deleted": render_id}


@router.get("/render/{render_id}/video")
def get_render_video(render_id: str):
    """Tayyor videoni beradi (preview/yuklab olish). Public — id taxminlanmas."""
    if "/" in render_id or "\\" in render_id:
        raise HTTPException(404, "Topilmadi")
    f = render_file(render_id)
    if not f.is_file():
        raise HTTPException(404, "Video topilmadi")
    return FileResponse(str(f), media_type="video/mp4",
                        filename=f"{render_id}.mp4")
