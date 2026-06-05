"""Real-time suhbat — javob quvuri (matn → video). STT alohida (ws.py'da streaming).

ws.py mikrofon PCM'ini Yandex streaming STT'ga uzatadi (gapirish paytida) → matn.
Bu modul SHU MATNdan boshlab: GPT (voice) → TTS (parallel, bitta wav) → video
progressive oqim. Avatar idle loopda turadi (kutish ko'rinmaydi).
"""
import threading
import time
import uuid

from app.core.paths import TEMP_DIR
from app.services import avatar_store
from app.services.gpt import SYSTEM_PROMPT, ask_gpt_stream, build_system_prompt
from app.services.tts import tts

_PENDING = {}
_PENDING_LOCK = threading.Lock()


def take_pending(token: str):
    with _PENDING_LOCK:
        return _PENDING.pop(token, None)


def reply_stream(user_text: str, avatar_id: str = None, voice: str = None,
                 session_id: str = None, start_frame=None):
    """Matndan javob quvuri. {text} → {stream,url} → {done}  yoki {error}.

    session_id — har WS ulanishiga noyob (multi-user): GPT suhbat tarixi shu kalit
    bo'yicha alohida saqlanadi, shunda bir avatarga gaplashayotgan turli userlar
    bir-birining kontekstini ko'rmaydi. Berilmasa avatar_id'ga qaytadi.
    """
    avatar = avatar_store.get_avatar(avatar_id) if avatar_id else None
    history_key = session_id or avatar_id
    use_voice = voice or (avatar or {}).get("voice", "madina")
    fps = int((avatar or {}).get("fps", 25)) or 25

    # ── TAYYOR JAVOB (pre-rendered Q&A) ── Savol biror tayyor javobga mos kelsa,
    # GPT+TTS+jonli-gen'ni butunlay o'tkazib, tayyor videoni DARROV beramiz (idle
    # bilan silliq: render lead-in/tail idle pozada). Foydalanuvchi farqini sezmaydi.
    if avatar_id:
        try:
            from app.services import canned
            hit = canned.match(avatar_id, user_text)
        except Exception:  # noqa: BLE001
            hit = None
        if hit:
            ans = (hit.get("text") or "").strip()
            yield {"type": "token", "text": ans}
            yield {"type": "text", "text": ans, "t": 0.0, "ttft": 0.0, "canned": True}
            try:
                avatar_store.log_event(avatar_id, user_text, False, gpt=0, tts=0, video=0, total=0)
            except Exception:  # noqa: BLE001
                pass
            yield {"type": "stream", "url": canned.video_url(hit["id"]),
                   "timing": {"gpt": 0.0, "tts": 0.0}, "start_frame": start_frame,
                   "canned": True}
            yield {"type": "done"}
            return

    # GPT — voice rejimi (to'liq, markdownsiz)
    if avatar:
        system_prompt, max_tokens = build_system_prompt(
            avatar.get("persona", ""), "voice", avatar.get("language", "uz"),
        )
        temperature = float(avatar.get("temperature", 0.4))
    else:
        system_prompt, max_tokens, temperature = SYSTEM_PROMPT, 360, 0.4
    t = time.time()
    parts = []
    ttft = None      # time-to-first-token (his qilinadigan kechikish)
    try:
        for delta in ask_gpt_stream(user_text, system_prompt=system_prompt,
                                    temperature=temperature, max_tokens=max_tokens,
                                    history_key=history_key):
            if ttft is None:
                ttft = round(time.time() - t, 2)
            parts.append(delta)
            yield {"type": "token", "text": delta}   # jonli matn
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"GPT xatosi: {e}"}
        return
    reply = "".join(parts).strip()
    gpt_t = round(time.time() - t, 2)
    # To'liq matn (frontend yakunlash/timing uchun) — ttft = birinchi token vaqti.
    yield {"type": "text", "text": reply, "t": gpt_t, "ttft": ttft}

    if avatar_id:
        try:
            avatar_store.log_event(avatar_id, user_text, False, gpt=0, tts=0, video=0, total=0)
        except Exception:
            pass

    # TTS — bitta wav (Yandex bo'laklari tts() ichida PARALLEL sintez qilinadi)
    sid = uuid.uuid4().hex[:12]
    wav = str(TEMP_DIR / f"rt_{sid}.wav")
    t = time.time()
    try:
        tts(reply, wav, voice=use_voice)
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"Ovoz xatosi: {e}"}
        return
    tts_t = round(time.time() - t, 2)

    from app.services import musetalk
    with _PENDING_LOCK:
        _PENDING[sid] = {"wav": wav, "avatar_id": avatar_id, "fps": fps,
                         "start_frame": start_frame,
                         "max_dim": musetalk.use_max_dim(avatar)}
    yield {"type": "stream", "url": f"/api/realtime/stream/{sid}",
           "timing": {"gpt": gpt_t, "tts": tts_t}, "start_frame": start_frame}
    yield {"type": "done"}
