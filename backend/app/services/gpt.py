"""GPT javob generatsiyasi + persona/system prompt boshqaruvi.

LLM provayderi sozlanadigan (config.llm_provider):
  ollama (standart) — lokal qwen3:8b, Ollama NATIV /api/chat endpointi orqali.
                      Tarmoq kechikishi yo'q → GPT bosqichi keskin tezlashadi (~0.5s).
  openai            — OpenAI gpt-4o-mini (fallback / A-B test uchun, ~2s).

MUHIM: Qwen3 — "thinking" modeli. Nativ /api/chat'da `think=False` fikrlashni
O'CHIRADI (to'g'ridan javob). Ollama'ning OpenAI-mos /v1 endpointi `think`'ni
E'TIBORSIZ qoldiradi — model fikrlab, token budjetini sarflaydi va javob BO'SH
qaytadi. Shu sababli ollama uchun OpenAI SDK emas, nativ /api/chat ishlatamiz.
"""
import json as _json
import re as _re
import urllib.error
import urllib.request

from openai import OpenAI

from app.core.config import (
    llm_keep_alive,
    llm_provider,
    ollama_base_url,
    ollama_model,
    openai_api_key,
)

_PROVIDER = llm_provider()
_MODEL = "gpt-4o-mini" if _PROVIDER == "openai" else ollama_model()

# OpenAI mijozi faqat openai provayderida kerak (ollama nativ HTTP ishlatadi).
_openai_client = OpenAI(api_key=openai_api_key()) if _PROVIDER == "openai" else None

# Ollama nativ /api/chat URL'i (base_url /v1'siz). config /v1 bilan keladi → kesamiz.
_OLLAMA_CHAT_URL = ollama_base_url().rstrip("/")
if _OLLAMA_CHAT_URL.endswith("/v1"):
    _OLLAMA_CHAT_URL = _OLLAMA_CHAT_URL[:-3]
_OLLAMA_CHAT_URL = _OLLAMA_CHAT_URL.rstrip("/") + "/api/chat"

print(f"[GPT] provayder={_PROVIDER} model={_MODEL}")


def _complete(messages, temperature, max_tokens) -> str:
    """Provayderga qarab javob matnini qaytaradi."""
    if _PROVIDER == "openai":
        resp = _openai_client.chat.completions.create(
            model=_MODEL, max_tokens=max_tokens, temperature=temperature,
            messages=messages,
        )
        return resp.choices[0].message.content or ""

    # Ollama nativ /api/chat — think=False (tezlik kaliti), keep_alive (rezident).
    body = _json.dumps({
        "model": _MODEL,
        "messages": messages,
        "think": False,
        "stream": False,
        "keep_alive": llm_keep_alive(),
        # repeat_penalty — takroriy "10000 dan ortiq..." kabi degeneratsiya
        # loopining oldini oladi (qwen3:8b qisqa javoblarda ba'zan takrorlanadi).
        "options": {"temperature": temperature, "num_predict": max_tokens,
                    "repeat_penalty": 1.3, "repeat_last_n": 64},
    }).encode("utf-8")
    req = urllib.request.Request(_OLLAMA_CHAT_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Ollama {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"Ollama ulanish xatosi: {e}") from None
    return (data.get("message") or {}).get("content", "") or ""


def _complete_stream(messages, temperature, max_tokens):
    """Javob token'larini OQIM bilan yieldlaydi (matn bo'laklari ketma-ket).

    GPT↔TTS pipeline uchun: GPT gapni yozayotganda TTS oldingi jumlani sintez
    qiladi. Token'lar kelishi bilan yieldlanadi (to'liq javobni kutmaymiz).
    """
    if _PROVIDER == "openai":
        stream = _openai_client.chat.completions.create(
            model=_MODEL, max_tokens=max_tokens, temperature=temperature,
            messages=messages, stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
        return

    # Ollama nativ /api/chat — stream=True → har bir token NDJSON qatori sifatida.
    body = _json.dumps({
        "model": _MODEL,
        "messages": messages,
        "think": False,
        "stream": True,
        "keep_alive": llm_keep_alive(),
        "options": {"temperature": temperature, "num_predict": max_tokens,
                    "repeat_penalty": 1.3, "repeat_last_n": 64},
    }).encode("utf-8")
    req = urllib.request.Request(_OLLAMA_CHAT_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Ollama {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"Ollama ulanish xatosi: {e}") from None
    with resp:
        for line in resp:
            line = line.strip()
            if not line:
                continue
            try:
                obj = _json.loads(line)
            except Exception:
                continue
            piece = (obj.get("message") or {}).get("content", "")
            if piece:
                yield piece
            if obj.get("done"):
                break


SYSTEM_PROMPT = """Siz O'zbekiston Temir Yo'llari virtual yordamchisisiz, ismingiz Madina.

JAVOB USLUBI (juda muhim — qisqa javob real-time video uchun shart):
- HAR DOIM imkon qadar qisqa: 1 jumla, eng ko'pi 2 qisqa jumla
- Har bir jumla 14 so'zdan oshmasin
- Faqat "batafsil ayting" yoki "to'liqroq" deyilsa → eng ko'pi 3 qisqa jumla
- Hech qachon ro'yxat, misol yoki kirish so'zi bermang ("Albatta", "Tabiiyki" kabi ortiqcha so'zlarsiz)
- To'g'ridan-to'g'ri javobni ayting, ortiqcha tushuntirishsiz
- O'zbek tilida, do'stona ohangda
- Narxlarni "yo'nalishga qarab farq qiladi" deb umumiy ayting"""

# Global (None kalit) + avatarga xos suhbat tarixi
chat_history = []
_histories = {}


def _history_for(key):
    if key is None:
        return chat_history
    return _histories.setdefault(key, [])


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


# Xavfsizlik to'ri: agar model baribir <think>...</think> bloki qaytarsa
# (think=False qo'llab-quvvatlanmagan eski versiya), uni olib tashlaymiz.
_THINK_RE = _re.compile(r"<think>.*?</think>", _re.DOTALL | _re.IGNORECASE)


def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


def ask_gpt(user_message: str, system_prompt: str = SYSTEM_PROMPT,
            temperature: float = 0.4, max_tokens: int = 90,
            history_key=None) -> str:
    hist = _history_for(history_key)
    hist.append({"role": "user", "content": user_message})
    messages = [{"role": "system", "content": system_prompt}] + hist
    reply = _strip_think(_complete(messages, temperature, max_tokens))
    hist.append({"role": "assistant", "content": reply})
    if len(hist) > 16:
        del hist[:-16]
    return reply


def ask_gpt_stream(user_message: str, system_prompt: str = SYSTEM_PROMPT,
                   temperature: float = 0.4, max_tokens: int = 90,
                   history_key=None):
    """ask_gpt'ning OQIMLI varianti — toza matn bo'laklarini yieldlaydi.

    Token'lar kelishi bilan <think> bloklarini tashlab, qolganini yield qiladi.
    Generator tugaganda to'liq javobni suhbat tarixiga yozadi. Chaqiruvchi
    bo'laklarni jumlalarga yig'ib, TTS'ga oqim bilan uzatishi mumkin.
    """
    hist = _history_for(history_key)
    hist.append({"role": "user", "content": user_message})
    messages = [{"role": "system", "content": system_prompt}] + hist

    full = []
    in_think = False           # <think>...</think> ichidamizmi
    buf = ""                   # teglarni qisman ko'rish uchun bufer
    for piece in _complete_stream(messages, temperature, max_tokens):
        buf += piece
        # Bufer ichidan toza (think'siz) matnni ajratib, qolganini saqlaymiz.
        # Teg yarmida uzilmaslik uchun oxirgi '<...' bo'lagini buferda qoldiramiz.
        while True:
            if in_think:
                end = buf.lower().find("</think>")
                if end == -1:
                    buf = buf[-8:] if len(buf) > 8 else buf  # '</think>' uzunligi
                    break
                buf = buf[end + len("</think>"):]
                in_think = False
                continue
            start = buf.lower().find("<think>")
            if start == -1:
                # Ehtimoliy yarim teg ('<', '<th', ...) ni keyingi bo'lakka qoldiramiz.
                lt = buf.rfind("<")
                emit = buf if lt == -1 else buf[:lt]
                hold = "" if lt == -1 else buf[lt:]
                if emit:
                    full.append(emit)
                    yield emit
                buf = hold
                break
            emit = buf[:start]
            if emit:
                full.append(emit)
                yield emit
            buf = buf[start + len("<think>"):]
            in_think = True
    if buf and not in_think:
        full.append(buf)
        yield buf

    reply = "".join(full).strip()
    hist.append({"role": "assistant", "content": reply})
    if len(hist) > 16:
        del hist[:-16]
