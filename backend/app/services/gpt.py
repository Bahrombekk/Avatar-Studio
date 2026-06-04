"""GPT javob generatsiyasi + persona/system prompt boshqaruvi."""
import json as _json
import re as _re
import threading

from openai import OpenAI

from app.core.config import openai_api_key

client = OpenAI(api_key=openai_api_key())

SYSTEM_PROMPT = """Siz O'zbekiston Temir Yo'llari virtual yordamchisisiz, ismingiz Madina.

JAVOB USLUBI (juda muhim — qisqa javob real-time video uchun shart):
- HAR DOIM imkon qadar qisqa: 1 jumla, eng ko'pi 2 qisqa jumla
- Har bir jumla 14 so'zdan oshmasin
- Faqat "batafsil ayting" yoki "to'liqroq" deyilsa → eng ko'pi 3 qisqa jumla
- Hech qachon ro'yxat, misol yoki kirish so'zi bermang ("Albatta", "Tabiiyki" kabi ortiqcha so'zlarsiz)
- To'g'ridan-to'g'ri javobni ayting, ortiqcha tushuntirishsiz
- O'zbek tilida, do'stona ohangda
- Narxlarni "yo'nalishga qarab farq qiladi" deb umumiy ayting"""

# Suhbat tarixi. MUHIM: real-time public sahifada bir avatarga ko'p user
# gaplashadi — shuning uchun tarix HAR SESSIYA uchun alohida bo'lishi shart
# (aks holda userlar bir-birining konteksti/gaplarini ko'radi). ws.py har WS
# ulanishiga noyob session_id beradi va shuni history_key sifatida uzatadi.
# Admin matn-chat (/chat) esa avatar_id'ni kalit qiladi (bitta admin, davomiylik).
chat_history = []        # None kalit (eski global yo'l)
_histories = {}          # key (session_id yoki avatar_id) → xabarlar ro'yxati
_hist_lock = threading.Lock()


def _history_for(key):
    if key is None:
        return chat_history
    with _hist_lock:
        return _histories.setdefault(key, [])


def clear_history(key) -> None:
    """Sessiya tarixini o'chiradi (WS uzilganda chaqiriladi — xotira oqmasin)."""
    if key is None:
        return
    with _hist_lock:
        _histories.pop(key, None)


# Javob uzunligi profillari (respLen → ko'rsatma + token chegarasi).
_RESP_LEN = {
    "short":  ("HAR DOIM imkon qadar qisqa: 1 jumla, eng ko'pi 2 qisqa jumla. "
               "Har jumla 14 so'zdan oshmasin.", 90),
    "medium": ("Qisqa-o'rta javob: eng ko'pi 3-4 jumla.", 160),
    "long":   ("Batafsilroq javob bering, lekin ortiqcha cho'zmang: eng ko'pi 6 jumla.", 280),
    # Real-time ovozli suhbat uchun: javob TUGALLANGAN bo'lsin (kesilmasin),
    # markdown/ro'yxatsiz (ovoz uchun), ixcham. Token budjeti kengroq (kesilmaslik uchun).
    "voice":  ("To'liq va TUGALLANGAN, lekin ixcham suhbat javobi ber (2-5 jumla). "
               "Markdown, yulduzcha (*) yoki raqamli ro'yxat ISHLATMA — faqat oddiy, "
               "og'zaki gaplar. Gapni o'rtada uzma, doim tugat.", 360),
}


# Til kodi → (nomi, "har doim shu tilda javob ber" ko'rsatmasi).
_LANG_NAMES = {"uz": "o'zbek", "ru": "rus", "en": "ingliz", "kk": "qozoq"}


def _lang_rule(language: str) -> str:
    """Avatar tili uchun majburiy til qoidasi. uz — standart (qo'shimcha shart yo'q)."""
    code = (language or "uz").lower()
    name = _LANG_NAMES.get(code)
    if not name or code == "uz":
        return ""
    return (
        f"\n\nMUHIM TIL QOIDASI: Foydalanuvchi qaysi tilda yozishidan qat'i nazar, "
        f"HAR DOIM va FAQAT {name} tilida javob bering."
    )


def build_system_prompt(persona: str = "", resp_len: str = "short",
                        language: str = "uz") -> tuple:
    """Avatar personasi + tilidan to'liq system prompt + max_tokens quradi.
    persona bo'sh bo'lsa — standart Madina prompti (+ til qoidasi)."""
    length_rule, max_tokens = _RESP_LEN.get(resp_len, _RESP_LEN["short"])
    lang_rule = _lang_rule(language)
    base = (persona or "").strip()
    if not base:
        # Bo'sh persona: standart Madina prompti + tanlangan uzunlik qoidasi + til.
        # (Ilgari max_tokens 90 ga QOTIRILGAN edi — javob chala kesilardi; tuzatildi.)
        return f"{SYSTEM_PROMPT}\n- {length_rule}{lang_rule}", max_tokens
    prompt = (
        f"{base}\n\n"
        f"JAVOB USLUBI (real-time video uchun muhim):\n"
        f"- {length_rule}\n"
        f"- Ro'yxat, misol yoki ortiqcha kirish so'zisiz, to'g'ridan-to'g'ri javob bering\n"
        f"- Foydalanuvchi tilida, do'stona ohangda"
        f"{lang_rule}"
    )
    return prompt, max_tokens


def ask_gpt(user_message: str, system_prompt: str = SYSTEM_PROMPT,
            temperature: float = 0.4, max_tokens: int = 90,
            history_key=None) -> str:
    hist = _history_for(history_key)
    hist.append({"role": "user", "content": user_message})
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "system", "content": system_prompt}] + hist,
    )
    reply = resp.choices[0].message.content.strip()
    hist.append({"role": "assistant", "content": reply})
    if len(hist) > 16:
        del hist[:-16]
    return reply


def normalize_for_tts(text: str, language: str = "uz") -> str:
    """Matnni ovozlashtirish (TTS) uchun normallashtiradi: qisqartma/belgilar to'liq
    so'z bo'ladi (km→kilometr, %→foiz...), sonlar/yillar/sanalar so'z bilan yoziladi.
    Yandex/edge TTS sonlar va qisqartmalarni noto'g'ri aytadi — shuni oldini oladi.
    Xato bo'lsa asl matnni qaytaradi (render to'xtamasin)."""
    text = (text or "").strip()
    if not text:
        return text
    name = _LANG_NAMES.get((language or "uz").lower(), "o'zbek")
    sp = (
        f"Sen matnni ovozlashtirish (TTS) uchun tayyorlaysan. Quyidagilarni qil va "
        f"FAQAT tayyor matnni qaytar (izoh, qo'shimcha, qavs YO'Q):\n"
        f"- Qisqartma va belgilarni TO'LIQ SO'Z bilan yoz ({name} tilida): km→kilometr, "
        f"m→metr, kg→kilogramm, %→foiz, $→dollar, °C→gradus, № yoki #→raqam, & ва h.k.\n"
        f"- Barcha SONLAR, yillar, sanalar, telefon/raqamlarni SO'Z bilan yoz "
        f"(masalan 2024→ikki ming yigirma to'rt; 15 km→o'n besh kilometr).\n"
        f"- Ma'noni O'ZGARTIRMA, jumlalarni qisqartirma — faqat aytilishini tabiiy qil.\n"
        f"- Til: {name}. Boshqa tilga tarjima QILMA."
    )
    try:
        out = ask_gpt(text, system_prompt=sp, temperature=0.0,
                      max_tokens=1200, history_key=None)
        return (out or "").strip() or text
    except Exception:  # noqa: BLE001
        return text


# ── Avatar skript analizatori (Video Studiya) — matn → tuzilgan JSON ──
# 4 bosqich: (1) normalizatsiya (raqam/sana→so'z, qisqartma→harflab/to'liq),
# (2) his-tuyg'u, (3) bosh harakati rejasi, (4) lip-sync (pace/pauza/urg'u).
SCRIPT_ANALYZER_PROMPT = """Sen — avatar (talking-head) video uchun matn tayyorlovchi mutaxassissan.
Vazifang: berilgan xom matnni avatar TABIIY va JONLI gapiradigan holatga keltirish.
SENGA TEZLIK EMAS, SIFAT VA ANIQLIK MUHIM.

1-BOSQICH — MATNNI TO'G'RILASH:
- Barcha RAQAM va SANALARNI to'liq og'zaki (so'z) shaklga o'tkaz (1994-yil → bir ming
  to'qqiz yuz to'qson to'rtinchi yil). Qisqartmalarni harflab o'qi (O'TY → O-Te-Ye).
- Ro'yxat/bandlarni tabiiy gapga aylantir. Imlo/talaffuz xatolarini tuzat. Ortiqcha
  belgilarni (—, :, •) olib tashla.
2-BOSQICH — HIS-TUYG'U: matnni jonli qil (faxr, ishonch, samimiylik). Ma'noni o'zgartirma.
3-BOSQICH — BOSH HARAKATI: har segment uchun turi (nod/tilt_left/tilt_right/turn_left/
  turn_right/lean_forward/none), trigger_word, speed (slow/medium/fast), intensity (0..1).
  MUHIM: harakatni FAOL ishlat — KO'PCHILIK segmentda harakat bo'lsin, "none" ni KAM
  ishlat (faqat juda qisqa bog'lovchi gapda). Qoidalar:
   • sanash/ro'yxat (birinchidan, ikkinchidan, yana...) → "nod"
   • faxr / urg'u / muhim e'lon → "lean_forward" yoki "nod" (intensity 0.6-0.9)
   • savol yoki taqqoslash → "tilt_right" yoki "tilt_left"
   • yangi mavzuga o'tish / salomlashish → "turn_left" yoki "turn_right" (yengil)
  Har 1-2 jumlada kamida bitta harakat bo'lsin (jonli ko'rinishi uchun).
4-BOSQICH — LIP-SYNC: har segment uchun pace (slow/medium/fast), pause_after_ms, emphasis_words.

FAQAT shu JSON ni qaytar (izoh, sarlavha, ``` belgilarisiz):
{
  "full_text": "to'g'rilangan, og'zaki shakldagi to'liq matn",
  "segments": [
    {"id": 1, "text": "bitta gap, og'zaki shaklda", "emotion": "neutral",
     "emphasis_words": [], "head_motion": {"type": "none", "trigger_word": "",
     "speed": "medium", "intensity": 0.0}, "pace": "medium", "pause_after_ms": 300}
  ]
}
QOIDA: id ketma-ket; har gap alohida segment; raqam/sana HAR DOIM so'z bilan; faqat JSON."""


def _parse_json_block(raw: str) -> dict:
    """GPT javobidan JSON'ni ajratib oladi (``` fence yoki ortiqcha matn bo'lsa ham)."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = _re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = _re.sub(r"\n?```$", "", raw).strip()
    i, j = raw.find("{"), raw.rfind("}")
    if i >= 0 and j > i:
        raw = raw[i:j + 1]
    return _json.loads(raw)


def analyze_script(text: str, language: str = "uz") -> dict:
    """Xom matnni avatar uchun tuzilgan rejaga aylantiradi (full_text + segments).
    Xato/parse muvaffaqiyatsiz → fallback {full_text: normalize_for_tts(text), segments: []}."""
    text = (text or "").strip()
    if not text:
        return {"full_text": "", "segments": []}
    try:
        raw = ask_gpt(text, system_prompt=SCRIPT_ANALYZER_PROMPT, temperature=0.5,
                      max_tokens=2400, history_key=None)
        data = _parse_json_block(raw)
        ft = (data.get("full_text") or "").strip()
        segs = data.get("segments") if isinstance(data.get("segments"), list) else []
        if ft:
            return {"full_text": ft, "segments": segs}
    except Exception as e:  # noqa: BLE001
        print(f"[analyze_script] fallback (parse xato): {e}")
    return {"full_text": normalize_for_tts(text, language), "segments": []}


def ask_gpt_stream(user_message: str, system_prompt: str = SYSTEM_PROMPT,
                   temperature: float = 0.4, max_tokens: int = 90,
                   history_key=None):
    """ask_gpt'ning token-oqim varianti: javob bo'laklarini (delta) yieldlaydi.

    Frontend matnni jonli (yozilayotgandek) ko'rsatadi → his qilinadigan kechikish
    keskin kamayadi. Tarixga TO'LIQ javob oxirida bir marta yoziladi (generator
    to'liq iste'mol qilinishi shart — session.py shuni qiladi)."""
    hist = _history_for(history_key)
    hist.append({"role": "user", "content": user_message})
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "system", "content": system_prompt}] + hist,
        stream=True,
    )
    parts = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            parts.append(delta)
            yield delta
    reply = "".join(parts).strip()
    hist.append({"role": "assistant", "content": reply})
    if len(hist) > 16:
        del hist[:-16]
