"""Real-time suhbat — javob quvuri (matn → video). STT alohida (ws.py'da streaming).

ws.py mikrofon PCM'ini Yandex streaming STT'ga uzatadi (gapirish paytida) → matn.
Bu modul SHU MATNdan boshlab: GPT (voice) → TTS → video progressive oqim.
Avatar idle loopda turadi (kutish ko'rinmaydi).

JUMLA-DARAJALI OQIM (RT_SENTENCE_STREAM=1 bilan yoqiladi; default O'CHIQ):
  GPT token oqimi jumla chegarasida bo'linadi → 1-jumla TTS bo'lishi bilan
  MuseTalk gapira BOSHLAYDI, qolgan jumlalar parallel sintez qilinadi
  (ws.py'dagi chunk_queue yo'li). Birinchi ovozgacha kechikish keskin kamayadi.
  Barge-in: cancel tokeni TTS worker'da ham, GPU producer'da ham tekshiriladi.
  OGOHLANTIRISH: hozircha sifat muammosi bor — Whisper har jumla uchun alohida
  ishlaydi, chegaralarda lab qaltirashi/sinxron buzilishi kuzatildi. Default
  bitta-wav (sifatli) yo'l; chunk-kontekst tuzatilgunicha 1 qilib yoqmang.

RAG bilim bazasi (agar avatar uchun sozlangan bo'lsa) system prompt'ga qo'shiladi.
"""
import logging
import os
import queue
import re
import subprocess
import threading
import time
import uuid

from app.core.paths import TEMP_DIR
from app.services import avatar_store
from app.services.gpt import SYSTEM_PROMPT, ask_gpt_stream, build_system_prompt
from app.services.tts import tts

log = logging.getLogger(__name__)
_PENDING = {}
_PENDING_LOCK = threading.Lock()

# Jumla-darajali streaming (default: O'CHIQ — sifat). RT_SENTENCE_STREAM=1 → yoqish.
# SABAB: musetalk_infer_stream_queue Whisper xususiyatlarini HAR JUMLA uchun alohida
# hisoblaydi — jumla chegaralarida audio kontekst uziladi → lab qaltirashi/sinxron
# buzilishi (jonli sinovda tasdiqlandi). Yoqishdan oldin chunk'lararo Whisper
# kontekst-overlap kerak (yoki Ditto kabi streaming-native modelga o'tish).
_SENTENCE_STREAM = os.environ.get("RT_SENTENCE_STREAM", "0").lower() not in ("0", "false", "no")
# 1-jumladan KEYINGI bo'laklar juda mayda bo'lmasin (TTS so'rov overhead'i +
# uzuq-yuluq ohang oldini olish). 1-jumla esa imkon qadar TEZ chiqadi.
_MIN_TAIL_CHARS = 20
# Jumlalar orasiga qo'shiladigan tabiiy pauza (soniya). 0 → o'chirilgan.
_SENT_PAUSE = float(os.environ.get("RT_SENT_PAUSE", "0.22") or 0)
# Dinamik emotsiya: har jumla mazmuniga qarab TTS roli/ohangi o'zgaradi (yulduz v3).
# Qo'shimcha kechikish yo'q (evristika). O'chirish: RT_EMOTION=0.
_EMOTION = os.environ.get("RT_EMOTION", "1").lower() not in ("0", "false", "no")

# Jumla oxiri: . ! ? … (+ yopuvchi qo'shtirnoq/qavs), KEYIN bo'shliq.
# Oqim paytida $ (bufer oxiri) bilan bo'lmaymiz — "3." dan keyin "5" kelishi
# mumkin (kasr son); bo'shliq talab qilingani uchun "3.5" hech qachon bo'linmaydi.
_SENT_END = re.compile(r"[.!?…]+[\"'»)\]]*\s+")


def split_sentences(buf: str):
    """Buferdan TUGALLANGAN jumlalarni ajratadi → (jumlalar, qolgan dum).
    Faqat tinish belgisi + bo'shliq chegara hisoblanadi (oqim uchun xavfsiz)."""
    parts = []
    last = 0
    for m in _SENT_END.finditer(buf):
        sent = buf[last:m.end()].strip()
        if sent:
            parts.append(sent)
        last = m.end()
    return parts, buf[last:]


def take_pending(token: str):
    with _PENDING_LOCK:
        return _PENDING.pop(token, None)


def _pad_wav(wav: str, pad: float):
    """Jumla wav'i oxiriga qisqa jimlik qo'shadi (jumlalar orasida tabiiy pauza).
    Xato bo'lsa — asl wav qoladi (oqim to'xtamaydi)."""
    if pad <= 0:
        return
    tmp = wav.replace(".wav", "_pad.wav")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", wav,
             "-af", f"apad=pad_dur={pad:.2f}", "-ar", "16000", "-ac", "1", tmp],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0 and os.path.exists(tmp):
            os.replace(tmp, wav)
        else:
            log.warning("[rt-tts] pad xato: %s", (r.stderr or b"")[:200])
    except Exception as e:  # noqa: BLE001
        log.warning("[rt-tts] pad xato: %s", e)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def reply_stream(user_text: str, avatar_id: str = None, voice: str = None,
                 session_id: str = None, start_frame=None, cancel=None):
    """Matndan javob quvuri. {token}* → {stream,url} → {text} → {done} yoki {error}.

    session_id — har WS ulanishiga noyob (multi-user): GPT suhbat tarixi shu kalit
    bo'yicha alohida saqlanadi. cancel — barge-in tokeni: jumla-oqim rejimida TTS
    worker va GPU producer'da tekshiriladi (javob darhol to'xtaydi).
    """
    avatar = avatar_store.get_avatar(avatar_id) if avatar_id else None
    history_key = session_id or avatar_id
    use_voice = voice or (avatar or {}).get("voice", "madina")
    fps = int((avatar or {}).get("fps", 25)) or 25

    # ── TAYYOR JAVOB (pre-rendered Q&A) ── mos kelsa tayyor videoni DARROV beramiz.
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

    # RAG — bilim bazasidan mos bo'laklarni system prompt'ga qo'shamiz (asoslash).
    if avatar_id:
        try:
            from app.services import knowledge
            _block = knowledge.build_context_block(knowledge.retrieve(avatar_id, user_text))
            if _block:
                system_prompt = system_prompt + "\n\n" + _block
        except Exception as e:  # noqa: BLE001
            log.warning("[rag] augment xato: %s", e)

    # JONLI TEMIR YO'L — savol poyezd/chipta haqida bo'lsa, eticket.railway.uz'dan
    # real narx/jadval/turlarni olib system prompt'ga qo'shamiz.
    try:
        from app.services import railway
        _rail = railway.railway_context(user_text, (avatar or {}).get("language", "uz"))
        if _rail:
            system_prompt = system_prompt + "\n\n" + _rail
            # Jadval javobi uzunroq — token budjetini ko'taramiz (kesilmasin).
            max_tokens = max(max_tokens, 500)
    except Exception as e:  # noqa: BLE001
        log.warning("[railway] augment xato: %s", e)

    # ── Jumla-oqim holati ──
    sid = uuid.uuid4().hex[:12]
    sent_q: queue.Queue = queue.Queue()    # GPT → TTS worker (jumla matnlari)
    chunk_q: queue.Queue = queue.Queue()   # TTS worker → GPU producer (wav yo'llari)
    tts_total = [0.0]                      # worker yig'adigan TTS vaqti (log uchun)
    worker_started = False
    stream_sent = False

    def _tts_worker():
        """Jumlalarni KETMA-KET sintez qilib wav'larni chunk_q'ga uzatadi.
        (Har jumla ichida Yandex bo'laklari baribir parallel — tts() o'zi qiladi.)
        Xato bo'lgan jumla O'TKAZIB yuboriladi (javob butunlay yiqilmasin)."""
        i = 0
        try:
            while True:
                sent = sent_q.get()
                if sent is None:
                    break
                if cancel is not None and cancel.is_set():
                    break
                wav = str(TEMP_DIR / f"rt_{sid}_{i}.wav")
                t0 = time.time()
                try:
                    tts(sent, wav, voice=use_voice, auto_emotion=_EMOTION)
                except Exception as e:  # noqa: BLE001
                    log.error("[rt-tts] jumla %d xato (%s): %s", i, use_voice, e,
                              extra={"stage": "tts", "voice": use_voice})
                    continue
                _pad_wav(wav, _SENT_PAUSE)
                tts_total[0] += time.time() - t0
                chunk_q.put(wav)
                i += 1
        finally:
            chunk_q.put(None)   # GPU producer'ga "tugadi" signali

    def _start_worker():
        nonlocal worker_started
        if not worker_started:
            threading.Thread(target=_tts_worker, daemon=True,
                             name=f"rt-tts-{sid}").start()
            worker_started = True

    def _register_pending():
        from app.services import musetalk
        with _PENDING_LOCK:
            _PENDING[sid] = {"chunk_queue": chunk_q, "avatar_id": avatar_id,
                             "fps": fps, "start_frame": start_frame,
                             "cancel": cancel,
                             "max_dim": musetalk.rt_max_dim(avatar)}

    t = time.time()
    parts = []
    ttft = None      # time-to-first-token (his qilinadigan kechikish)
    pend = ""        # GPT bufer (jumla chegarasi kutilmoqda)
    hold = ""        # juda qisqa jumlalarni yig'ish (keyingisiga qo'shiladi)
    try:
        for delta in ask_gpt_stream(user_text, system_prompt=system_prompt,
                                    temperature=temperature, max_tokens=max_tokens,
                                    history_key=history_key):
            if ttft is None:
                ttft = round(time.time() - t, 2)
            parts.append(delta)
            yield {"type": "token", "text": delta}   # jonli matn
            if not _SENTENCE_STREAM:
                continue
            if cancel is not None and cancel.is_set():
                break    # barge-in: GPT oqimini ham to'xtatamiz
            pend += delta
            sents, pend = split_sentences(pend)
            for s in sents:
                hold = f"{hold} {s}".strip() if hold else s
                # 1-jumla — DARROV (kechikish past); keyingilar mayda bo'lmasin.
                if stream_sent and len(hold) < _MIN_TAIL_CHARS:
                    continue
                _start_worker()
                sent_q.put(hold)
                hold = ""
                if not stream_sent:
                    _register_pending()
                    yield {"type": "stream", "url": f"/api/realtime/stream/{sid}",
                           "timing": {"gpt": round(time.time() - t, 2), "tts": 0.0},
                           "start_frame": start_frame, "sentence_stream": True}
                    stream_sent = True
    except Exception as e:  # noqa: BLE001
        if worker_started:
            sent_q.put(None)   # boshlangan nutq yakunlansin (video osilib qolmasin)
        yield {"type": "error", "message": f"GPT xatosi: {e}"}
        return
    reply = "".join(parts).strip()
    gpt_t = round(time.time() - t, 2)
    yield {"type": "text", "text": reply, "t": gpt_t, "ttft": ttft}

    if avatar_id:
        try:
            avatar_store.log_event(avatar_id, user_text, False, gpt=0, tts=0, video=0, total=0)
        except Exception:  # noqa: BLE001
            pass

    if _SENTENCE_STREAM:
        # Dum: chegarasiz qolgan matn + yig'ilgan qisqa jumlalar.
        tail = f"{hold} {pend}".strip()
        if not reply:
            if worker_started:
                sent_q.put(None)
            yield {"type": "error", "message": "Javob bo'sh qaytdi"}
            return
        if tail and not (cancel is not None and cancel.is_set()):
            _start_worker()
            sent_q.put(tail)
        if not stream_sent:
            # Hamma matn bitta dumda (qisqa javob) — oqimni endi ochamiz.
            _start_worker()
            _register_pending()
            yield {"type": "stream", "url": f"/api/realtime/stream/{sid}",
                   "timing": {"gpt": gpt_t, "tts": 0.0},
                   "start_frame": start_frame, "sentence_stream": True}
            stream_sent = True
        sent_q.put(None)     # boshqa jumla yo'q
        yield {"type": "done"}
        return

    # ── ESKI YO'L (RT_SENTENCE_STREAM=0): bitta to'liq wav ──
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
                         "max_dim": musetalk.rt_max_dim(avatar)}
    yield {"type": "stream", "url": f"/api/realtime/stream/{sid}",
           "timing": {"gpt": gpt_t, "tts": tts_t}, "start_frame": start_frame}
    yield {"type": "done"}
