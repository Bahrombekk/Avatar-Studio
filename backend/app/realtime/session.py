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
from app.services.tts import tts, tts_streaming
from app.services.pipeline import _is_portfolio
from app.services import portfolio

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
    # GPT↔TTS pipelining: GPT token'larini OQIM bilan TTS'ga uzatamiz — GPT
    # keyingi jumlani yozayotganda TTS oldingisini sintez qiladi (kechikish
    # GPT+TTS o'rniga ~max(GPT, TTS)). Natija — bitta wav (MuseTalk o'zgarmaydi).
    sid = uuid.uuid4().hex[:12]
    wav = str(TEMP_DIR / f"rt_{sid}.wav")

    # Vaqtlarni ALOHIDA o'lchaymiz (oqimli quvurda haqiqiy va ko'paytirilmagan):
    #   gpt_t = GPT'ning BIRINCHI token'gacha vaqti — oqimli tizimda "GPT kechikishi"
    #           shu (qolgani TTS bilan overlap bo'ladi). Lokal qwen3:8b → juda kichik.
    #   tts_t = umumiy GPT+TTS quvuri vaqtidan birinchi token'gacha bo'lgan qismni
    #           ayirgani — ya'ni gapni ovozga aylantirish ishi.
    t0 = time.time()
    gpt_first = {"at": None}

    def _timed(gen):
        for p in gen:
            if gpt_first["at"] is None:
                gpt_first["at"] = time.time()   # GPT birinchi token'ni berdi
            yield p

    try:
        if _is_portfolio(avatar):
            # DASUTY loyihalar bazasi: bitta loyihaga yo'naltirilgan javob (qwen3:8b),
            # keyin oddiy TTS. Loyihalar aralashmaydi.
            res = portfolio.answer(user_text, max_tokens=max_tokens)
            reply = res["text"]
            gpt_first["at"] = time.time()
            tts(reply, wav, voice=use_voice)
        else:
            pieces = _timed(ask_gpt_stream(user_text, system_prompt=system_prompt,
                                           temperature=temperature, max_tokens=max_tokens,
                                           history_key=avatar_id))
            reply = tts_streaming(pieces, wav, voice=use_voice)
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"Javob/ovoz xatosi: {e}"}
        return
    end = time.time()
    gpt_t = round((gpt_first["at"] or end) - t0, 2)   # birinchi token'gacha (GPT kechikishi)
    tts_t = round(end - (gpt_first["at"] or end), 2)  # qolgan quvur (TTS sintez)
    yield {"type": "text", "text": reply, "t": gpt_t}

    if avatar_id:
        try:
            avatar_store.log_event(avatar_id, user_text, False, gpt=0, tts=0, video=0, total=0)
        except Exception:
            pass

    with _PENDING_LOCK:
        _PENDING[sid] = {"wav": wav, "avatar_id": avatar_id, "fps": fps}
    yield {"type": "stream", "url": f"/api/realtime/stream/{sid}",
           "timing": {"gpt": gpt_t, "tts": tts_t}}
    yield {"type": "done"}
