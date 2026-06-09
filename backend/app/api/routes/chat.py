"""Chat endpointlari — sinxron /chat va SSE /chat-stream."""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import resolve
from app.schemas.chat import ChatRequest
from app.services import avatar_store

router = APIRouter(tags=["chat"])

# DIQQAT: `app.services.pipeline` (musetalk/torch) handler ICHIDA import qilinadi —
# modul yuqorisida emas — `create_app()` yengil muhitda import bo'lishi uchun.


@router.post("/chat")
def chat(req: ChatRequest):
    from app.services.pipeline import run_pipeline
    msg = req.message.strip()
    if not msg:
        raise HTTPException(400, "Xabar bo'sh")
    avatar, voice = resolve(req)
    result = run_pipeline(msg, voice=voice, avatar=avatar)
    if "error" in result:
        raise HTTPException(500, result["error"])
    if req.avatar_id:
        tm = result.get("timing", {})
        avatar_store.log_event(req.avatar_id, msg, result.get("cached", False),
                               gpt=tm.get("gpt", 0), tts=tm.get("tts", 0),
                               video=tm.get("wav2lip", 0), total=tm.get("total", 0))
    return result


@router.post("/chat-stream")
def chat_stream(req: ChatRequest):
    from app.services.pipeline import run_pipeline_stream
    msg = req.message.strip()
    if not msg:
        raise HTTPException(400, "Xabar bo'sh")
    avatar, voice = resolve(req)

    def event_source():
        try:
            for event in run_pipeline_stream(msg, voice=voice, avatar=avatar):
                if event.get("type") == "video" and req.avatar_id:
                    tm = event.get("timing", {})
                    avatar_store.log_event(req.avatar_id, msg, event.get("cached", False),
                                           gpt=tm.get("gpt", 0), tts=tm.get("tts", 0),
                                           video=tm.get("wav2lip", 0), total=tm.get("total", 0))
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
