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
from app.services.gpt import SYSTEM_PROMPT, ask_gpt, build_system_prompt
from app.services.tts import tts

_PENDING = {}
_PENDING_LOCK = threading.Lock()


def take_pending(token: str):
    with _PENDING_LOCK:
        return _PENDING.pop(token, None)


def reply_stream(user_text: str, avatar_id: str = None, voice: str = None):
    """Matndan javob quvuri. {text} → {stream,url} → {done}  yoki {error}."""
    avatar = avatar_store.get_avatar(avatar_id) if avatar_id else None
    use_voice = voice or (avatar or {}).get("voice", "madina")
    fps = int((avatar or {}).get("fps", 25)) or 25

    # GPT — voice rejimi (to'liq, markdownsiz)
    if avatar:
        system_prompt, max_tokens = build_system_prompt(
            avatar.get("persona", ""), "voice", avatar.get("language", "uz"),
        )
        temperature = float(avatar.get("temperature", 0.4))
    else:
        system_prompt, max_tokens, temperature = SYSTEM_PROMPT, 360, 0.4
    t = time.time()
    try:
        reply = ask_gpt(user_text, system_prompt=system_prompt,
                        temperature=temperature, max_tokens=max_tokens,
                        history_key=avatar_id)
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"GPT xatosi: {e}"}
        return
    gpt_t = round(time.time() - t, 2)
    yield {"type": "text", "text": reply, "t": gpt_t}

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

    with _PENDING_LOCK:
        _PENDING[sid] = {"wav": wav, "avatar_id": avatar_id, "fps": fps}
    yield {"type": "stream", "url": f"/api/realtime/stream/{sid}",
           "timing": {"gpt": gpt_t, "tts": tts_t}}
    yield {"type": "done"}
