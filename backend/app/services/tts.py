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
               "label": "Yulduz (Yandex)", "speed": 0.97, "smooth_af": _YX_SMOOTH,
               # Yandex v3 emotsiya/uslub — yulduz qo'llaydi: neutral|strict|friendly|whisper.
               # "friendly" = iliq, jonli ohang (jalb qiluvchi yordamchi uchun).
               # O'chirish/o'zgartirish: env YULDUZ_ROLE (bo'sh = role yubormaydi).
               "role": os.environ.get("YULDUZ_ROLE", "friendly").strip() or None},
    # ── Rus ──
    "ru_dmitry":   {"provider": "edge", "voice": "ru-RU-DmitryNeural",   "label": "Dmitriy (edge)"},
    "ru_svetlana": {"provider": "edge", "voice": "ru-RU-SvetlanaNeural", "label": "Svetlana (edge)"},
    "ru_filipp": {"provider": "yandex", "voice": "filipp", "lang": "ru-RU",
                  "label": "Filipp (Yandex)", "speed": 1.0, "smooth_af": _YX_SMOOTH},
    "ru_alena":  {"provider": "yandex", "voice": "alena", "lang": "ru-RU",
                  "label": "Alyona (Yandex)", "speed": 1.0, "smooth_af": _YX_SMOOTH},
    "ru_omazh":  {"provider": "yandex", "voice": "omazh", "lang": "ru-RU",
                  "label": "Omazh (Yandex)", "speed": 1.0, "smooth_af": _YX_SMOOTH},
    "ru_marina": {"provider": "yandex_v3", "voice": "marina", "lang": "ru-RU",
                  "label": "Marina (Yandex v3)", "speed": 1.0, "smooth_af": _YX_SMOOTH,
                  "role": "neutral"},
    # ── Ingliz ──
    "en_guy":  {"provider": "edge", "voice": "en-US-GuyNeural",  "label": "Guy (edge)"},
    "en_aria": {"provider": "edge", "voice": "en-US-AriaNeural", "label": "Aria (edge)"},
    "en_ava":  {"provider": "edge", "voice": "en-US-AvaNeural",  "label": "Ava (edge)"},
    # ── Qozoq ──
    "kk_daulet": {"provider": "edge", "voice": "kk-KZ-DauletNeural", "label": "Daulet (edge)"},
    "kk_aigul":  {"provider": "edge", "voice": "kk-KZ-AigulNeural",  "label": "Aigul (edge)"},
}
DEFAULT_VOICE = "madina"

# Til → o'sha til uchun standart ovoz (avatar.langVoices bermasa fallback).
_LANG_DEFAULT_VOICE = {"uz": "madina", "en": "en_ava", "ru": "ru_marina", "kk": "kk_aigul"}
_UZ_VOICES = {"madina", "sardor", "nigora", "yulduz"}


def voice_for(avatar: dict, language: str = None) -> str:
    """Avatar + til uchun samarali ovoz. Ustuvorlik:
      1) avatar.langVoices[til]  (foydalanuvchi har tilga oldindan tanlagan ovoz)
      2) avatar.voice — agar u tanlangan tilga mos bo'lsa
      3) o'sha til uchun standart ovoz (_LANG_DEFAULT_VOICE)
      4) avatar.voice (oxirgi fallback)
    Shunday qilib 'til=ingliz' → inglizcha ovoz, o'zbekcha normalizatsiya o'zi o'chadi."""
    av = avatar or {}
    lang = (language or av.get("language") or "uz").lower()
    lv = (av.get("langVoices") or {}).get(lang)
    if lv and lv in VOICES:
        return lv
    main = av.get("voice") or DEFAULT_VOICE
    spec = VOICES.get(main) or {}
    vlang = (spec.get("lang", "") or "").lower()
    main_is_uz = main in _UZ_VOICES
    if lang == "uz" and main_is_uz:
        return main
    if lang != "uz" and (f"{lang}-" in vlang or main.startswith(f"{lang}_")):
        return main
    return _LANG_DEFAULT_VOICE.get(lang, main)

# ── Dinamik emotsiya (jumla mazmuniga qarab rol/ohang) ──
# Qaysi ovozlar Yandex v3 rollarini qo'llaydi va qaysi rollar xavfsiz.
# (yulduz: neutral|strict|friendly|whisper — boshqa rollar HTTP 400 beradi.)
ROLE_VOICES = {"yulduz": {"neutral", "strict", "friendly", "whisper"}}

# O'zbekcha kalit-so'zlar (registrsiz, apostrof birxillashtirilgan holda qidiriladi).
_EMO_SOFT = ("kechiras", "uzr", "afsus", "afsuski", "achinar", "tushunaman",
             "muammo", "xato", "imkoni yo'q", "imkoni yoq", "bekor qilin",
             "topilmadi", "mavjud emas", "band emas")
_EMO_FIRM = ("diqqat", "muhim", "ogohlantir", "majbur", "shart ", "taqiq",
             "mumkin emas", "ruxsat etilmaydi", "esda tut")
_EMO_WARM = ("assalom", "salom", "xush kelib", "rahmat", "tashakkur", "tabrik",
             "xayrli", "marhamat", "yordam bera")


def detect_emotion(text: str, voice: str = "yulduz"):
    """Jumla mazmunidan (role, pitchShift) qaytaradi — jonli ohang uchun.
    Faqat rol qo'llaydigan ovozlarda ishlaydi; aks holda (None, 0.0).
    Yengil evristika (kalit-so'z + tinish belgisi) — QO'SHIMCHA KECHIKISH yo'q,
    tashqi so'rov yo'q. Yulduz rollari cheklangan, shuning uchun asosan
    friendly↔neutral↔strict + kichik pitchShift (±3) bilan modulyatsiya."""
    roles = ROLE_VOICES.get(voice)
    if not roles:
        return None, 0.0
    t = (text or "").strip().lower().replace("ʻ", "'").replace("`", "'").replace("ʼ", "'")
    if not t:
        return None, 0.0

    def _pick(name):
        return name if name in roles else ("friendly" if "friendly" in roles else None)

    # 1) Yumshoq/hamdard (uzr, afsus, muammo, topilmadi) — sekinroq, past ohang.
    if any(k in t for k in _EMO_SOFT):
        return _pick("neutral"), -1.0
    # 2) Qat'iy/ogohlantirish (diqqat, muhim, taqiq).
    if any(k in t for k in _EMO_FIRM):
        return _pick("strict"), 0.0
    # 3) Salomlashish/minnatdorchilik yoki xitob → iliq, ko'tarinki.
    if t.endswith("!") or any(k in t for k in _EMO_WARM):
        return _pick("friendly"), 2.0
    # 4) Savol → iliq, taklif ohangi (biroz ko'tarilgan).
    if t.endswith("?"):
        return _pick("friendly"), 1.0
    # 5) Standart bayon → iliq, neytral ohang.
    return _pick("friendly"), 0.0

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


async def _tts_edge(text: str, tmp_path: str, voice_id: str, rate: str = ""):
    kw = {"text": text, "voice": voice_id}
    if rate:
        kw["rate"] = rate          # masalan "+10%" / "-10%" (gapirish tezligi)
    await edge_tts.Communicate(**kw).save(tmp_path)


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
    import http.client
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
        except http.client.IncompleteRead as e:
            # Javob Content-Length'ni to'g'ri yopmasa — o'qilgan qism to'liq audio.
            audio = e.partial
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Yandex TTS {e.code}: {body}") from None
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException) as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    if not audio:
        raise RuntimeError(f"Yandex TTS tarmoq xatosi (3 urinish): {last_err}")
    with open(tmp_path, "wb") as f:
        f.write(audio)


def _tts_yandex_v3(text: str, tmp_path: str, voice_id: str, speed: float = 1.0,
                   role: str = None, pitch: float = 0.0):
    """Yandex SpeechKit v3 (yulduz kabi yangi ovozlar shu yerda).

    role  — emotsiya/uslub (yulduz: neutral|strict|friendly|whisper). None = yubormaydi.
    pitch — ovoz balandligi siljishi (pitchShift), 0 = yubormaydi."""
    import json as _json
    import base64
    import http.client
    import urllib.request
    import urllib.error
    auth, folder = _yx_auth_folder()
    hints = [{"voice": voice_id}, {"speed": speed}]
    if role:
        hints.append({"role": role})
    if pitch:
        hints.append({"pitchShift": pitch})
    body = _json.dumps({
        "text": text,
        "outputAudioSpec": {"containerAudio": {"containerAudioType": "OGG_OPUS"}},
        "hints": hints,
        "loudnessNormalizationType": "LUFS",
    }).encode("utf-8")
    req = urllib.request.Request(YANDEX_TTS_V3_URL, data=body, headers={
        "Authorization": auth, "x-folder-id": folder,
        "Content-Type": "application/json",
    })
    def _parse_v3(raw_bytes: bytes) -> bytes:
        """v3 javobidan (JSON qatorlar) base64 audio chunk'larni yig'adi.
        Chala/buzuq qatorlar o'tkazib yuboriladi."""
        audio = bytearray()
        for line in (raw_bytes or b"").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = _json.loads(line)
            except Exception:
                continue   # kesilgan/buzuq JSON qatori — o'tkazamiz
            chunk = obj.get("result", {}).get("audioChunk", {}).get("data")
            if chunk:
                audio.extend(base64.b64decode(chunk))
        return bytes(audio)

    # Yandex v3 javobi chunked + connection:close — ba'zan yakuniy chunk kelmay
    # IncompleteRead bo'ladi. Strategiya: o'qilgan qismni (to'liq yoki partial) PARSE
    # qilib ko'ramiz; audio chiqsa — ishlatamiz; chiqmasa (JSON kesilgan) — QAYTA
    # urinamiz (yangi so'rov to'liq javob beradi). 4 urinish.
    last_err = None
    for attempt in range(4):
        raw = None
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except http.client.IncompleteRead as e:
            raw = e.partial
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Yandex TTS v3 {e.code}: {body_txt}") from None
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException) as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
            continue
        audio = _parse_v3(raw)
        if audio:
            with open(tmp_path, "wb") as f:
                f.write(audio)
            return
        last_err = "javob chala/bo'sh (audio topilmadi)"
        time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"Yandex TTS v3 tarmoq xatosi (4 urinish): {last_err}")


# ── Ovoz namunasi (preview) — editorda har ovozni eshitib tanlash uchun ──
_PREVIEW_TEXT = {
    "uz": "Assalomu alaykum! Men sizning virtual yordamchingizman.",
    "ru": "Здравствуйте! Я ваш виртуальный помощник.",
    "en": "Hello! I'm your virtual assistant.",
    "kk": "Сәлеметсіз бе! Мен сіздің виртуалды көмекшіңізмін.",
}


def voice_lang(voice_id: str) -> str:
    """Ovozning tili (uz/ru/en/kk) — spec 'lang' yoki voice id prefiksidan."""
    spec = VOICES.get(voice_id) or {}
    lang = spec.get("lang")
    if lang:
        return lang.split("-")[0]
    v = spec.get("voice", "")
    if "-" in v:
        return v.split("-")[0]
    return "uz"


def ensure_preview(voice_id: str) -> str:
    """Ovoz namunasi wav'ini qaytaradi (keshlangan; yo'q bo'lsa generatsiya qiladi).
    Har ovoz o'z tilida bir qisqa gap gapiradi."""
    if voice_id not in VOICES:
        raise ValueError(f"Noma'lum ovoz: {voice_id}")
    from app.core.paths import CHECKPOINTS_DIR
    d = CHECKPOINTS_DIR / "voice_previews"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{voice_id}.wav"
    if p.exists() and p.stat().st_size > 0:
        return str(p)
    txt = _PREVIEW_TEXT.get(voice_lang(voice_id), _PREVIEW_TEXT["uz"])
    tts(txt, str(p), voice=voice_id)
    return str(p)


def tts(text: str, wav_path: str, voice: str = DEFAULT_VOICE, speed: float = 1.0,
        role: str = None, pitch: float = None, auto_emotion: bool = False):
    """speed — gapirish tezligi ko'paytuvchisi (1.0 = normal; <1 sekin, >1 tez).
    pace (slow/medium/fast) shu orqali qo'llanadi. edge: rate%, Yandex: speed param.

    role/pitch — Yandex v3 emotsiya override (None = spec/auto). auto_emotion=True
    bo'lsa va role berilmagan bo'lsa, jumla mazmunidan (detect_emotion) rol/ohang
    aniqlanadi (jonli suhbatда jumlama-jumla o'zgaradi)."""
    spec = VOICES.get(voice) or VOICES[DEFAULT_VOICE]
    provider = spec["provider"]
    smooth = spec.get("smooth_af", "")
    speed = max(0.5, min(2.0, float(speed or 1.0)))

    # Emotsiya (role/pitch) — RAW matndan aniqlanadi (normalizatsiyadan oldin, tinish
    # belgisi saqlansin). Aniq override > auto > spec standarti.
    eff_role = spec.get("role")
    eff_pitch = spec.get("pitch", 0.0)
    if role is not None or pitch is not None:
        if role is not None:
            eff_role = role
        if pitch is not None:
            eff_pitch = pitch
    elif auto_emotion:
        _r, _p = detect_emotion(text, voice)
        if _r is not None:
            eff_role, eff_pitch = _r, _p
    # O'zbek ovozlari uchun: raqam/sana/vaqt/klass kodlarini SO'Zga o'giramiz
    # (TTS to'g'ri talaffuz qilsin). Ekranda ko'rsatilgan matn O'ZGARMAYDI — bu faqat
    # TTS'ga kiruvchi nusxa. Rus/ingliz/qozoq ovozlarida o'tkazib yuboramiz.
    _vlang = spec.get("lang", "") or spec.get("voice", "")
    if "uz" in _vlang.lower() or voice in ("madina", "sardor", "nigora", "yulduz"):
        try:
            from app.services.uznum import normalize_uz_tts
            text = normalize_uz_tts(text)
        except Exception:  # noqa: BLE001
            pass
    tmps = []
    if provider == "edge":
        # edge-TTS uzun matnni o'zi eplaydi — bo'lishga hojat yo'q.
        tmp = wav_path.replace(".wav", ".mp3")
        rate = ""
        if abs(speed - 1.0) > 0.01:
            pct = round((speed - 1.0) * 100)
            rate = f"+{pct}%" if pct >= 0 else f"{pct}%"
        asyncio.run(_tts_edge(text, tmp, spec["voice"], rate))
        tmps = [tmp]
    elif provider in ("yandex", "yandex_v3"):
        # Yandex uzun matnni rad etadi → jumlalarga bo'lamiz. Bo'laklarni KETMA-KET
        # emas, PARALLEL sintez qilamiz (kechikish sum → max) — uzun javobda
        # TTS sezilarli tezlashadi. Tartib saqlanadi.
        from concurrent.futures import ThreadPoolExecutor
        chunks = _split_text(text) or [text]
        tmps = [wav_path.replace(".wav", f".p{i}.ogg") for i in range(len(chunks))]
        yx_speed = max(0.5, min(2.0, spec.get("speed", 1.0) * speed))

        def _synth(i_ch):
            i, ch = i_ch
            if provider == "yandex":
                _tts_yandex(ch, tmps[i], spec["voice"], spec.get("lang", "uz-UZ"),
                            speed=yx_speed)
            else:
                _tts_yandex_v3(ch, tmps[i], spec["voice"], speed=yx_speed,
                               role=eff_role, pitch=eff_pitch or 0.0)

        if len(chunks) == 1:
            _synth((0, chunks[0]))
        else:
            with ThreadPoolExecutor(max_workers=min(6, len(chunks))) as ex:
                list(ex.map(_synth, list(enumerate(chunks))))
    else:
        raise RuntimeError(f"Noma'lum provayder: {provider}")
    _parts_to_wav(tmps, wav_path, extra_af=smooth)
    for p in tmps:
        try:
            os.remove(p)
        except OSError:
            pass
