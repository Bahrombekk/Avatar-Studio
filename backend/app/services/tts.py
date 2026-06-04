"""TTS — matn → ovoz. Provayderlar: edge-TTS, Yandex SpeechKit v1 va v3."""
import asyncio
import os
import re
import subprocess
import time

import edge_tts

# Yandex bitta so'rovda uzun matnni qabul qilmaydi ("Too long text"). Shu chegaradan
# uzun bo'lsa, matnni jumlalarga bo'lib, har bo'lakni alohida sintez qilamiz.
_YX_MAX_CHARS = 200

from app.core.config import load_env_var

# ── Ovozlar reestri ──
#   edge      → edge-TTS (uz-UZ-*Neural)
#   yandex    → Yandex SpeechKit v1 REST (uz-UZ nigora)
#   yandex_v3 → Yandex SpeechKit v3 REST (uz-UZ yulduz — faqat v3 da bor)
_YX_SMOOTH = "dynaudnorm=f=250:g=7,treble=g=-2:f=7000"
VOICES = {
    # ── O'zbek ──
    "madina": {"provider": "edge",   "voice": "uz-UZ-MadinaNeural", "label": "Madina (edge)"},
    "sardor": {"provider": "edge",   "voice": "uz-UZ-SardorNeural", "label": "Sardor (edge)"},
    "nigora": {"provider": "yandex", "voice": "nigora", "lang": "uz-UZ",
               "label": "Nigora (Yandex)", "speed": 0.95, "smooth_af": _YX_SMOOTH},
    "yulduz": {"provider": "yandex_v3", "voice": "yulduz",
               "label": "Yulduz (Yandex)", "speed": 0.97, "smooth_af": _YX_SMOOTH},
    # ── Rus ──
    "ru_dmitry":   {"provider": "edge", "voice": "ru-RU-DmitryNeural",   "label": "Dmitriy (edge)"},
    "ru_svetlana": {"provider": "edge", "voice": "ru-RU-SvetlanaNeural", "label": "Svetlana (edge)"},
    "ru_filipp": {"provider": "yandex", "voice": "filipp", "lang": "ru-RU",
                  "label": "Filipp (Yandex)", "speed": 1.0, "smooth_af": _YX_SMOOTH},
    "ru_alena":  {"provider": "yandex", "voice": "alena", "lang": "ru-RU",
                  "label": "Alyona (Yandex)", "speed": 1.0, "smooth_af": _YX_SMOOTH},
    # ── Ingliz ──
    "en_guy":  {"provider": "edge", "voice": "en-US-GuyNeural",  "label": "Guy (edge)"},
    "en_aria": {"provider": "edge", "voice": "en-US-AriaNeural", "label": "Aria (edge)"},
    # ── Qozoq ──
    "kk_daulet": {"provider": "edge", "voice": "kk-KZ-DauletNeural", "label": "Daulet (edge)"},
    "kk_aigul":  {"provider": "edge", "voice": "kk-KZ-AigulNeural",  "label": "Aigul (edge)"},
}
DEFAULT_VOICE = "madina"

# Ikki chetdagi sukunatni kesish filtri (nutq tugagach og'iz g'imirlamasin).
_TRIM_AF = (
    "silenceremove=start_periods=1:start_threshold=-45dB:detection=peak,"
    "areverse,"
    "silenceremove=start_periods=1:start_threshold=-45dB:detection=peak,"
    "areverse"
)

YANDEX_TTS_URL    = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
YANDEX_TTS_V3_URL = "https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis"


def _trim_to_wav(tmp_audio: str, wav_path: str, extra_af: str = ""):
    """Istalgan audio → sukunat kesilgan 16k mono WAV (MuseTalk uchun)."""
    af = _TRIM_AF + ("," + extra_af if extra_af else "")
    subprocess.run([
        "ffmpeg", "-y", "-i", tmp_audio, "-af", af,
        "-ar", "16000", "-ac", "1", wav_path,
    ], capture_output=True)


def _parts_to_wav(parts: list, wav_path: str, extra_af: str = ""):
    """Bir nechta audio bo'lakni ketma-ket ulab, kesilgan 16k mono WAV qiladi."""
    if len(parts) == 1:
        _trim_to_wav(parts[0], wav_path, extra_af)
        return
    af = _TRIM_AF + ("," + extra_af if extra_af else "")
    inputs = []
    for p in parts:
        inputs += ["-i", p]
    n = len(parts)
    concat = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[c]"
    fc = f"{concat};[c]{af}[out]"
    subprocess.run([
        "ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[out]",
        "-ar", "16000", "-ac", "1", wav_path,
    ], capture_output=True)


def _split_text(text: str, max_chars: int = _YX_MAX_CHARS) -> list:
    """Uzun matnni jumla chegaralarida (kerak bo'lsa so'z bo'yicha) bo'laklarga bo'ladi."""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return [text] if text else []
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    chunks, cur = [], ""
    for s in sentences:
        if len(s) > max_chars:                      # juda uzun jumla → so'z bo'yicha
            if cur:
                chunks.append(cur.strip())
                cur = ""
            for w in s.split():
                if len(cur) + len(w) + 1 > max_chars and cur:
                    chunks.append(cur.strip())
                    cur = ""
                cur += " " + w
            continue
        if len(cur) + len(s) + 1 > max_chars and cur:
            chunks.append(cur.strip())
            cur = ""
        cur += " " + s
    if cur.strip():
        chunks.append(cur.strip())
    return [c for c in chunks if c]


async def _tts_edge(text: str, tmp_path: str, voice_id: str):
    await edge_tts.Communicate(text=text, voice=voice_id).save(tmp_path)


def _yx_auth_folder():
    api_key = load_env_var("YX_API_KEY")
    iam_token = load_env_var("YX_IAM_TOKEN")
    folder = load_env_var("YX_FOLDER_ID")
    if api_key:
        auth = f"Api-Key {api_key}"
    elif iam_token:
        auth = f"Bearer {iam_token}"
    else:
        raise RuntimeError("Yandex TTS uchun YX_API_KEY yoki YX_IAM_TOKEN (.env) kerak")
    if not folder:
        raise RuntimeError("Yandex TTS uchun YX_FOLDER_ID (.env) kerak")
    return auth, folder


def _tts_yandex(text: str, tmp_path: str, voice_id: str, lang: str = "uz-UZ", speed: float = 1.0):
    import urllib.request
    import urllib.parse
    import urllib.error
    auth, folder = _yx_auth_folder()
    data = urllib.parse.urlencode({
        "text": text, "lang": lang, "voice": voice_id,
        "speed": f"{speed:.2f}", "folderId": folder,
        "format": "oggopus",
    }).encode("utf-8")
    req = urllib.request.Request(YANDEX_TTS_URL, data=data, headers={"Authorization": auth})
    audio = None
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio = resp.read()
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Yandex TTS {e.code}: {body}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    if audio is None:
        raise RuntimeError(f"Yandex TTS tarmoq xatosi (3 urinish): {last_err}")
    with open(tmp_path, "wb") as f:
        f.write(audio)


def _tts_yandex_v3(text: str, tmp_path: str, voice_id: str, speed: float = 1.0):
    """Yandex SpeechKit v3 (yulduz kabi yangi ovozlar shu yerda)."""
    import json as _json
    import base64
    import urllib.request
    import urllib.error
    auth, folder = _yx_auth_folder()
    body = _json.dumps({
        "text": text,
        "outputAudioSpec": {"containerAudio": {"containerAudioType": "OGG_OPUS"}},
        "hints": [{"voice": voice_id}, {"speed": speed}],
        "loudnessNormalizationType": "LUFS",
    }).encode("utf-8")
    req = urllib.request.Request(YANDEX_TTS_V3_URL, data=body, headers={
        "Authorization": auth, "x-folder-id": folder,
        "Content-Type": "application/json",
    })
    raw = None
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Yandex TTS v3 {e.code}: {body_txt}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    if raw is None:
        raise RuntimeError(f"Yandex TTS v3 tarmoq xatosi (3 urinish): {last_err}")
    audio = bytearray()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = _json.loads(line)
        except Exception:
            continue
        chunk = obj.get("result", {}).get("audioChunk", {}).get("data")
        if chunk:
            audio.extend(base64.b64decode(chunk))
    if not audio:
        raise RuntimeError("Yandex TTS v3: audio bo'sh qaytdi")
    with open(tmp_path, "wb") as f:
        f.write(bytes(audio))


def _synth_chunk(spec: dict, provider: str, text: str, out_path: str):
    """Bitta matn bo'lagini bitta audio faylga sintez qiladi (provayderga qarab)."""
    if provider == "edge":
        asyncio.run(_tts_edge(text, out_path, spec["voice"]))
    elif provider == "yandex":
        _tts_yandex(text, out_path, spec["voice"], spec.get("lang", "uz-UZ"),
                    speed=spec.get("speed", 1.0))
    elif provider == "yandex_v3":
        _tts_yandex_v3(text, out_path, spec["voice"], speed=spec.get("speed", 1.0))
    else:
        raise RuntimeError(f"Noma'lum provayder: {provider}")


def _ext_for(provider: str) -> str:
    return ".mp3" if provider == "edge" else ".ogg"


def tts(text: str, wav_path: str, voice: str = DEFAULT_VOICE):
    spec = VOICES.get(voice) or VOICES[DEFAULT_VOICE]
    provider = spec["provider"]
    smooth = spec.get("smooth_af", "")
    tmps = []
    if provider == "edge":
        # edge-TTS uzun matnni o'zi eplaydi — bo'lishga hojat yo'q.
        tmp = wav_path.replace(".wav", ".mp3")
        _synth_chunk(spec, provider, text, tmp)
        tmps = [tmp]
    elif provider in ("yandex", "yandex_v3"):
        # Yandex uzun matnni rad etadi → jumlalarga bo'lamiz. Bo'laklarni KETMA-KET
        # emas, PARALLEL sintez qilamiz (kechikish sum → max) — uzun javobda
        # TTS sezilarli tezlashadi. Tartib saqlanadi.
        from concurrent.futures import ThreadPoolExecutor
        chunks = _split_text(text) or [text]
        tmps = [wav_path.replace(".wav", f".p{i}.ogg") for i in range(len(chunks))]

        if len(chunks) == 1:
            _synth_chunk(spec, provider, chunks[0], tmps[0])
        else:
            with ThreadPoolExecutor(max_workers=min(6, len(chunks))) as ex:
                list(ex.map(lambda ic: _synth_chunk(spec, provider, ic[1], tmps[ic[0]]),
                            list(enumerate(chunks))))
    else:
        raise RuntimeError(f"Noma'lum provayder: {provider}")
    _parts_to_wav(tmps, wav_path, extra_af=smooth)
    for p in tmps:
        try:
            os.remove(p)
        except OSError:
            pass


# Jumla tugashini aniqlash uchun: matnda gap chegarasi (. ! ? …) bo'lsami.
_SENT_END_RE = re.compile(r"[.!?…]+[\)\"'»]?\s")


def tts_streaming(text_pieces, wav_path: str, voice: str = DEFAULT_VOICE) -> str:
    """GPT matn bo'laklari OQIMINI iste'mol qilib, jumla tayyor bo'lishi bilan
    uni TTS'ga (fon thread'ida) yuboradi — GPT yozayotganda TTS sintez qiladi.

    Pipelining: GPT jumla-2 ni yozayotganda TTS jumla-1 ni sintez qiladi
    (kechikish: GPT + TTS o'rniga max(GPT, TTS)). Natija — bitta WAV (downstream
    MuseTalk o'zgarmaydi). To'liq javob matnini qaytaradi.

    text_pieces — toza matn bo'laklari iteratori (masalan gpt.ask_gpt_stream).
    """
    spec = VOICES.get(voice) or VOICES[DEFAULT_VOICE]
    provider = spec["provider"]
    smooth = spec.get("smooth_af", "")
    ext = _ext_for(provider)
    base = wav_path[:-4] if wav_path.endswith(".wav") else wav_path

    from concurrent.futures import ThreadPoolExecutor
    ex = ThreadPoolExecutor(max_workers=6)
    futures = []          # (index, future, tmp_path) — tartib saqlanadi
    full_text = []
    buf = ""
    idx = 0

    def _kick(segment: str):
        nonlocal idx
        seg = segment.strip()
        if not seg:
            return
        tmp = f"{base}.p{idx}{ext}"
        futures.append((idx, ex.submit(_synth_chunk, spec, provider, seg, tmp), tmp))
        idx += 1

    # 1) Oqimni o'qib, jumla chegarasida (yoki Yandex chegarasidan uzun bo'lsa) sintezni boshlaymiz.
    for piece in text_pieces:
        if not piece:
            continue
        full_text.append(piece)
        buf += piece
        # Jumla(lar) tugagan bo'lsa — tugagan qismini sintezga uzatamiz, qoldiqni saqlaymiz.
        while True:
            m = None
            for mm in _SENT_END_RE.finditer(buf):
                m = mm
                break
            if not m:
                break
            cut = m.end()
            _kick(buf[:cut])
            buf = buf[cut:]
        # Yandex juda uzun bo'lakni rad etadi — jumla chegarasi kelmasa ham bo'lamiz.
        if provider in ("yandex", "yandex_v3") and len(buf) >= _YX_MAX_CHARS:
            parts = _split_text(buf)
            for p in parts[:-1]:
                _kick(p)
            buf = parts[-1] if parts else ""

    # 2) Qoldiq matn.
    _kick(buf)

    if idx == 0:                       # bo'sh javob
        ex.shutdown(wait=True)
        raise RuntimeError("TTS uchun matn bo'sh")

    # 3) Barcha bo'laklarni tartibda kutib, ulab, bitta WAV qilamiz.
    tmps = []
    try:
        for i, fut, tmp in futures:
            fut.result()               # xato bo'lsa shu yerda ko'tariladi
            tmps.append(tmp)
    finally:
        ex.shutdown(wait=True)

    _parts_to_wav(tmps, wav_path, extra_af=smooth)
    for p in tmps:
        try:
            os.remove(p)
        except OSError:
            pass
    return "".join(full_text).strip()
