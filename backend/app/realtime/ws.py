"""Real-time WebSocket — /api/realtime/ws (streaming STT + idle-loop + video stream).

Protokol (klient → server):
  matn "start"        → STT sessiyasi ochiladi (gapirish boshlandi)
  binar PCM (16k m16) → Yandex streaming STT'ga uzatiladi (gapirish paytida)
  matn "stop"         → STT yakunlanadi → matn → GPT+TTS+video quvuri
  matn "ping"         → "pong"

Server → klient eventlari:
  {"type":"listening"} {"type":"transcript","text","t"} {"type":"text","text","t"}
  {"type":"stream","url","timing"} {"type":"done"} {"type":"error","message"}

Video baytlari GET /api/realtime/stream/<token> orqali progressive oqadi.
"""
import asyncio
import json
import os
import threading
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.services import avatar_store, musetalk
from app.realtime.session import reply_stream, take_pending
from app.realtime.stt_stream import StreamingSTT

router = APIRouter(tags=["realtime"])


@router.get("/api/realtime/stream/{token}")
def realtime_stream(token: str):
    """Javob videosini GENERATSIYA PAYTIDA progressive (fragmented-mp4) oqim qiladi."""
    if "/" in token or "\\" in token:
        raise HTTPException(404, "Topilmadi")
    info = take_pending(token)
    if not info:
        raise HTTPException(404, "Stream topilmadi yoki muddati o'tgan")
    wav = info["wav"]

    def gen():
        try:
            for chunk in musetalk.musetalk_infer_stream(
                wav, fps=info["fps"], avatar_id=info["avatar_id"],
            ):
                yield chunk
        finally:
            try:
                os.remove(wav)
            except OSError:
                pass

    return StreamingResponse(gen(), media_type="video/mp4",
                             headers={"Cache-Control": "no-store"})


@router.websocket("/api/realtime/ws")
async def realtime_ws(ws: WebSocket):
    await ws.accept()
    avatar_id = ws.query_params.get("avatar") or None
    voice = ws.query_params.get("voice") or None
    avatar = avatar_store.get_avatar(avatar_id) if avatar_id else None
    language = (avatar or {}).get("language", "uz")
    loop = asyncio.get_event_loop()

    stt = None          # joriy StreamingSTT sessiyasi
    speak_t0 = 0.0

    async def send(obj):
        await ws.send_text(json.dumps(obj, ensure_ascii=False))

    async def run_reply(user_text):
        """GPT+TTS+video quvurini thread'da yuritib, eventlarni yuboradi."""
        q: asyncio.Queue = asyncio.Queue()

        def worker():
            try:
                for ev in reply_stream(user_text, avatar_id, voice):
                    loop.call_soon_threadsafe(q.put_nowait, ev)
            except Exception as e:  # noqa: BLE001
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "message": str(e)})
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        threading.Thread(target=worker, daemon=True).start()
        while True:
            ev = await q.get()
            if ev is None:
                break
            await send(ev)

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            text = msg.get("text")
            if text is not None:
                if text == "ping":
                    await send({"type": "pong"})
                elif text == "start":
                    stt = StreamingSTT(language=language)
                    speak_t0 = time.time()
                    await send({"type": "listening"})
                elif text == "stop":
                    if stt is None:
                        continue
                    cur = stt
                    stt = None
                    cur.finish()
                    t = time.time()
                    try:
                        user_text = await loop.run_in_executor(None, cur.result, 10.0)
                    except Exception as e:  # noqa: BLE001
                        await send({"type": "error", "message": str(e)})
                        continue
                    stt_t = round(time.time() - t, 2)   # to'xtagandan keyin kutish
                    if not user_text:
                        await send({"type": "error", "message": "Nutq aniqlanmadi — qaytadan gapiring"})
                        continue
                    await send({"type": "transcript", "text": user_text, "t": stt_t})
                    await run_reply(user_text)
                continue

            # binar PCM bo'lak → STT'ga uzatamiz
            audio = msg.get("bytes")
            if audio and stt is not None:
                stt.feed(audio)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass
