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
import logging
import os
import threading
import time
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.services import avatar_store
from app.services.gpt import clear_history
from app.realtime.session import reply_stream, take_pending

log = logging.getLogger("app.realtime.ws")

# DIQQAT: `musetalk` (torch) va `StreamingSTT` (grpc/yandex) handler ICHIDA import
# qilinadi — modul yuqorisida emas — yengil muhitda (test/CI) import bo'lishi uchun.

router = APIRouter(tags=["realtime"])


@router.get("/api/realtime/stream/{token}")
def realtime_stream(token: str):
    """Javob videosini GENERATSIYA PAYTIDA progressive (fragmented-mp4) oqim qiladi."""
    if "/" in token or "\\" in token:
        raise HTTPException(404, "Topilmadi")
    info = take_pending(token)
    if not info:
        raise HTTPException(404, "Stream topilmadi yoki muddati o'tgan")

    def gen():
        from app.services import musetalk
        try:
            if info.get("chunk_queue") is not None:
                # SENTENCE-LEVEL: jumla wav'lari navbatdan kelib turadi (None = tugadi).
                for chunk in musetalk.musetalk_infer_stream_queue(
                    info["chunk_queue"], fps=info["fps"], avatar_id=info["avatar_id"],
                    start_frame=info.get("start_frame"), max_dim=info.get("max_dim"),
                    cancel=info.get("cancel"),
                ):
                    yield chunk
            else:
                # Eski yo'l — bitta to'liq wav.
                for chunk in musetalk.musetalk_infer_stream(
                    info["wav"], fps=info["fps"], avatar_id=info["avatar_id"],
                    start_frame=info.get("start_frame"), max_dim=info.get("max_dim"),
                ):
                    yield chunk
        finally:
            # Vaqtinchalik jumla wav'larini tozalaymiz (rt_<token>_*.wav) yoki bitta wav.
            import glob as _glob
            from app.core.paths import TEMP_DIR as _TMP
            for p in _glob.glob(str(_TMP / f"rt_{token}_*.wav")):
                try:
                    os.remove(p)
                except OSError:
                    pass
            if info.get("wav"):
                try:
                    os.remove(info["wav"])
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
    # Har ulanish — alohida suhbat sessiyasi (multi-user: tarixlar aralashmasin).
    session_id = "rt_" + uuid.uuid4().hex[:16]

    stt = None          # joriy StreamingSTT sessiyasi
    speak_t0 = 0.0
    audio_bytes = 0     # shu sessiyada qabul qilingan PCM baytlari (diagnostika)
    cancel_event = None     # joriy javob uchun bekor qilish tokeni (barge-in)
    turn = 0                # navbat raqami — eski javob eventlarini ajratish uchun

    async def send(obj):
        await ws.send_text(json.dumps(obj, ensure_ascii=False))

    def stop_active_reply():
        """Oqayotgan javobni (agar bo'lsa) to'xtatadi — barge-in."""
        nonlocal cancel_event
        if cancel_event is not None:
            cancel_event.set()
            cancel_event = None

    async def run_reply(user_text, start_frame, cancel, turn_id):
        """GPT+TTS+video quvurini thread'da yuritib, eventlarni yuboradi (task sifatida —
        receive-loop bloklanmaydi, shuning uchun barge-in xabari o'qiladi)."""
        q: asyncio.Queue = asyncio.Queue()

        def worker():
            try:
                for ev in reply_stream(user_text, avatar_id, voice, session_id=session_id,
                                       start_frame=start_frame, cancel=cancel):
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
            await send({**ev, "turn": turn_id})

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            text = msg.get("text")
            if text is not None:
                if text == "ping":
                    await send({"type": "pong"})
                elif text == "barge":
                    # Foydalanuvchi javob o'rtasida qayta gapirdi → joriy javobni tashlaymiz.
                    stop_active_reply()
                    await send({"type": "canceled", "turn": turn})
                elif text == "start":
                    stop_active_reply()      # gapirish = oldingi javobni bo'lish (agar bor)
                    from app.realtime.stt_stream import StreamingSTT
                    stt = StreamingSTT(language=language)
                    speak_t0 = time.time()
                    audio_bytes = 0
                    log.info("[stt] start lang=%s", language)
                    await send({"type": "listening"})
                elif text == "stop" or text.startswith("stop:"):
                    if stt is None:
                        continue
                    # "stop:<frame>" — frontend jonli idle videosining joriy kadri
                    # (kadr-sinxron handoff). Javob aynan shu pozadan boshlanadi.
                    start_frame = None
                    if ":" in text:
                        try:
                            start_frame = int(text.split(":", 1)[1])
                        except ValueError:
                            start_frame = None
                    cur = stt
                    stt = None
                    cur.finish()
                    t = time.time()
                    try:
                        user_text = await loop.run_in_executor(None, cur.result, 10.0)
                    except Exception as e:  # noqa: BLE001
                        log.warning("[stt] xato (fed=%d bayt): %s", audio_bytes, e)
                        await send({"type": "error", "message": str(e)})
                        continue
                    stt_t = round(time.time() - t, 2)   # to'xtagandan keyin kutish
                    log.info("[stt] stop: fed=%d bayt, partial='%s', natija='%s'",
                             audio_bytes, getattr(cur, "partial", ""), user_text)
                    if not user_text:
                        await send({"type": "error", "message": "Nutq aniqlanmadi — qaytadan gapiring"})
                        continue
                    stop_active_reply()                 # ehtiyot: oldingi javob qolgan bo'lsa
                    turn += 1
                    cancel_event = threading.Event()
                    await send({"type": "transcript", "text": user_text, "t": stt_t, "turn": turn})
                    # AWAIT EMAS — task sifatida ishga tushiramiz, loop barge'ni o'qiy oladi.
                    asyncio.create_task(run_reply(user_text, start_frame, cancel_event, turn))
                continue

            # binar PCM bo'lak → STT'ga uzatamiz
            audio = msg.get("bytes")
            if audio and stt is not None:
                audio_bytes += len(audio)
                stt.feed(audio)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass
    finally:
        # Sessiya tarixini bo'shatamiz (xotira oqmasin — har ulanish noyob kalit).
        clear_history(session_id)
