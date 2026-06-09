"""To'liq oqim — GPT → TTS → MuseTalk → mp4 (sinxron va SSE-stream variantlari).

Avatar = madina_lp (real artefakt). Kesh har (avatar, ovoz) juftligiga alohida.
Video FAQAT bir marta saqlanadi: MuseTalk tmp'ga yozadi → kesh uni o'z papkasiga
ko'chiradi (move). Serv qiluvchi nusxa yo'q.
"""
import logging
import os
import time
import uuid

from app.core.paths import TEMP_DIR, VID_OUT_DIR
from app.services.cache import get_cache, is_repeat_request
from app.services.gpt import ask_gpt, build_system_prompt, SYSTEM_PROMPT
from app.services.musetalk import musetalk_infer, use_max_dim
from app.services.tts import tts, DEFAULT_VOICE

log = logging.getLogger(__name__)


def _avatar_params(avatar):
    """Avatar dict'idan pipeline parametrlarini ajratadi (None bo'lsa standart)."""
    if not avatar:
        return SYSTEM_PROMPT, 0.4, 90, 25, None
    sp, mt = build_system_prompt(avatar.get("persona", ""), avatar.get("respLen", "short"),
                                 avatar.get("language", "uz"))
    temp = float(avatar.get("temperature", 0.4))
    fps = int(avatar.get("fps", 25)) or 25
    return sp, temp, mt, fps, avatar.get("id")


def _augment_prompt(system_prompt: str, avatar_id, user_message: str) -> str:
    """Bilim bazasidan (RAG) mos bo'laklarni topib, system prompt'ga qo'shadi.

    Xato/bo'sh bo'lsa o'zgarmagan system_prompt qaytadi (degradatsiya)."""
    # RAG — bilim bazasi (avatarga bog'liq).
    if avatar_id:
        try:
            from app.services import knowledge
            block = knowledge.build_context_block(knowledge.retrieve(avatar_id, user_message))
            if block:
                system_prompt = system_prompt + "\n\n" + block
        except Exception as e:  # noqa: BLE001
            log.warning("[rag] augment xato: %s", e)
    # Jonli temir yo'l (savol-bog'liq, eticket.railway.uz).
    try:
        from app.services import railway
        rail = railway.railway_context(user_message)
        if rail:
            system_prompt = system_prompt + "\n\n" + rail
    except Exception as e:  # noqa: BLE001
        log.warning("[railway] augment xato: %s", e)
    return system_prompt


def run_pipeline(user_message: str, voice: str = DEFAULT_VOICE, avatar: dict = None) -> dict:
    t0 = time.time()
    system_prompt, temperature, max_tokens, fps, hist_key = _avatar_params(avatar)
    # Kesh (avatar, ovoz)'ga bog'liq: bir xil savol, boshqa ovoz/persona → boshqa video.
    cache = get_cache(hist_key, voice)
    ckey = user_message

    if is_repeat_request(user_message):
        last = cache.get_last_entry()
        if last:
            cache.record_hit(last)
            dt = round(time.time() - t0, 3)
            return {"text": last["response"], "video": last["video"],
                    "timing": {"gpt": 0, "tts": 0, "wav2lip": 0, "total": dt},
                    "cached": True, "repeat": True, "cache_id": last["id"]}

    hit = cache.exact_match(ckey)
    if hit:
        cache.record_hit(hit)
        dt = round(time.time() - t0, 3)
        return {"text": hit["response"], "video": hit["video"],
                "timing": {"gpt": 0, "tts": 0, "wav2lip": 0, "total": dt},
                "cached": True, "cache_id": hit["id"]}

    sid = str(uuid.uuid4())[:8]
    system_prompt = _augment_prompt(system_prompt, hist_key, user_message)

    t1 = time.time()
    reply = ask_gpt(user_message, system_prompt=system_prompt,
                    temperature=temperature, max_tokens=max_tokens, history_key=hist_key)
    t_gpt = round(time.time() - t1, 2)
    log.info("[gpt] %ss → %s", t_gpt, reply[:60])

    t2 = time.time()
    wav_path = str(TEMP_DIR / f"{sid}.wav")
    try:
        tts(reply, wav_path, voice=voice)
    except Exception as e:
        log.error("[tts] %s: %s", voice, e)
        return {"error": f"Ovoz ({voice}) xatosi: {e}"}
    t_tts = round(time.time() - t2, 2)
    log.info("[tts] %ss (%s)", t_tts, voice)

    t3 = time.time()
    linux_mp4 = str(VID_OUT_DIR / f"{sid}.mp4")
    ok = musetalk_infer(wav_path, linux_mp4, fps=fps, avatar_id=hist_key,
                        max_dim=use_max_dim(avatar))
    if os.path.exists(wav_path):
        os.remove(wav_path)
    t_mt = round(time.time() - t3, 2)
    log.info("[musetalk] %ss", t_mt)

    if not ok:
        return {"error": "MuseTalk xato"}

    t_total = round(time.time() - t0, 2)
    log.info("[pipeline] jami %ss", t_total)

    # Video keshga KO'CHIRILADI (linux_mp4 endi mavjud bo'lmaydi).
    entry = cache.add(query=ckey, response=reply,
                      video_src_path=linux_mp4, gen_time=t_total)
    if not entry:
        return {"error": "Video saqlashda xato"}

    return {"text": reply, "video": entry["video"],
            "timing": {"gpt": t_gpt, "tts": t_tts, "wav2lip": t_mt, "total": t_total},
            "cached": False}


def run_pipeline_stream(user_message: str, voice: str = DEFAULT_VOICE, avatar: dict = None):
    t0 = time.time()
    system_prompt, temperature, max_tokens, fps, hist_key = _avatar_params(avatar)
    cache = get_cache(hist_key, voice)
    ckey = user_message

    if is_repeat_request(user_message):
        last = cache.get_last_entry()
        if last:
            cache.record_hit(last)
            dt = round(time.time() - t0, 3)
            yield {"type": "text", "text": last["response"], "cached": True, "repeat": True}
            yield {"type": "tts_done", "tts_time": 0, "cached": True}
            yield {"type": "video", "video": last["video"], "cached": True, "repeat": True,
                   "timing": {"gpt": 0, "tts": 0, "wav2lip": 0, "total": dt}}
            yield {"type": "done"}
            return

    hit = cache.exact_match(ckey)
    if hit:
        cache.record_hit(hit)
        dt = round(time.time() - t0, 3)
        yield {"type": "text", "text": hit["response"], "cached": True, "cache_id": hit["id"]}
        yield {"type": "tts_done", "tts_time": 0, "cached": True}
        yield {"type": "video", "video": hit["video"], "cached": True,
               "timing": {"gpt": 0, "tts": 0, "wav2lip": 0, "total": dt}}
        yield {"type": "done"}
        return

    sid = str(uuid.uuid4())[:8]
    system_prompt = _augment_prompt(system_prompt, hist_key, user_message)

    t1 = time.time()
    reply = ask_gpt(user_message, system_prompt=system_prompt,
                    temperature=temperature, max_tokens=max_tokens, history_key=hist_key)
    t_gpt = round(time.time() - t1, 2)
    yield {"type": "text", "text": reply, "gpt_time": t_gpt, "sid": sid}

    t2 = time.time()
    wav_full = str(TEMP_DIR / f"{sid}.wav")
    try:
        tts(reply, wav_full, voice=voice)
    except Exception as e:
        log.error("[tts] %s: %s", voice, e)
        yield {"type": "error", "message": f"Ovoz ({voice}) xatosi: {e}"}
        return
    t_tts = round(time.time() - t2, 2)
    yield {"type": "tts_done", "tts_time": t_tts}

    t3 = time.time()
    linux_mp4 = str(VID_OUT_DIR / f"{sid}.mp4")
    ok = musetalk_infer(wav_full, linux_mp4, fps=fps, avatar_id=hist_key,
                        max_dim=use_max_dim(avatar))
    try:
        os.remove(wav_full)
    except Exception:
        pass

    if not ok:
        yield {"type": "error", "message": "MuseTalk xato"}
        return

    total = round(time.time() - t0, 2)
    t_mt = round(time.time() - t3, 2)

    entry = cache.add(query=ckey, response=reply,
                      video_src_path=linux_mp4, gen_time=total)
    if not entry:
        yield {"type": "error", "message": "Video saqlashda xato"}
        return

    yield {"type": "video", "video": entry["video"],
           "timing": {"gpt": t_gpt, "tts": t_tts, "wav2lip": t_mt, "total": total}}
    yield {"type": "done"}
