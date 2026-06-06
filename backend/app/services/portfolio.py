"""DASUTY loyihalar portfeli bo'yicha savol-javob — loyihalararo ARALASHMASLIK kafolati.

Yondashuv: vektor BD EMAS. Korpus kichik (19 loyiha, kirill o'zbek) — embedding
loyihalararo "oqib ketish" (cross-contamination) keltiradi (hammasi "monitoring/
hisobot/Face-ID" haqida). O'rniga TUZILMAVIY retrieval:

  1. Har sahifa = bitta atomik loyiha yozuvi (projects.json, chunklanmaydi).
  2. ROUTING: avval kalit so'z/sarlavha/alias mosligi; topilmasa qwen3:8b
     19 ta (sarlavha+xulosa) ichidan tanlaydi.
  3. JAVOB: faqat O'SHA loyiha full_text'i + qat'iy prompt (boshqa loyiha haqida
     gapirma, ma'lumot yo'q bo'lsa "ma'lumotim yo'q" de). Model bir vaqtda FAQAT
     bitta loyiha matnini ko'radi → boshqa loyiha ma'lumotini jismonan bera olmaydi.

Javob TILI: doimo lotin o'zbek (manba kirill bo'lsa ham).
Mos kelmasa: "ma'lumotim yo'q" + loyihalar ro'yxati (hech qachon to'qib chiqarmaydi).
"""
import json
import re
from functools import lru_cache

from app.core.paths import DATA_DIR
from app.services.gpt import _complete  # provayderga (qwen3:8b) chaqiruv

PROJECTS_FILE = DATA_DIR / "portfolio" / "projects.json"


@lru_cache(maxsize=1)
def _load() -> list:
    if not PROJECTS_FILE.exists():
        return []
    try:
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _norm(s: str) -> str:
    """Kichik harf, apostrof/tире birxil, ortiqcha bo'shliq olib tashlash."""
    s = (s or "").lower()
    s = s.replace("ʻ", "'").replace("ʼ", "'").replace("`", "'").replace("'", "'")
    s = re.sub(r"[“”\"().,!?:;]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def list_projects() -> list:
    """Barcha loyiha sarlavhalari (ro'yxat intent uchun)."""
    return [p["title"].strip(" “”\"") for p in _load()]


# Ko'p sarlavhada uchraydigan UMUMIY so'zlar — bularga qarab yo'naltirmaymiz
# (aks holda "KPI tizimi" → "tizim" bo'yicha boshqa loyihaga tushib qoladi).
_STOPWORDS = {
    "tizim", "tizimi", "nazorat", "axborot", "axboroot", "platforma", "platformasi",
    "loyiha", "loyihasi", "boshqaruv", "boshqarish", "raqamli", "elektron",
    "onlayn", "tahlil", "hisobot", "monitoring", "modul", "moduli", "temir",
    "yo'l", "yo'llari", "uty", "aj", "haqida", "nima", "qanday", "uchun",
}


def _similar(a: str, b: str) -> float:
    """Ikki so'z o'xshashligi 0..1 (STT noto'g'ri eshitishiga chidamli)."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def _keyword_route(question: str):
    """Alias/o'ziga xos so'z mosligi bo'yicha loyiha topadi — FUZZY (STT xatosiga chidamli).

    Aniq moslik (substring) eng kuchli; topilmasa so'zlarni FONETIK yaqinlik bilan
    solishtiradi ("xotin"≈"xodim", "marshurt"≈"marshrut"). Umumiy so'zlar (STOPWORDS)
    e'tiborga olinmaydi. Eng yaxshi mos kelgan loyihani qaytaradi (yo'q bo'lsa None).
    """
    q = _norm(question)
    if not q:
        return None
    q_words = [w for w in q.split() if w not in _STOPWORDS and len(w) >= 2]
    best = None
    best_score = 0.0
    for p in _load():
        score = 0.0
        for alias in p.get("aliases", []):
            a = _norm(alias)
            if not a or len(a) < 2:
                continue
            # 1) Aniq substring moslik — eng kuchli.
            if re.search(rf"(?<!\w){re.escape(a)}(?!\w)", q):
                score = max(score, 100 + len(a))
                continue
            # 2) Fuzzy: alias so'z(lar)ini savol so'zlari bilan solishtiramiz.
            a_words = a.split()
            if len(a_words) == 1:
                for w in q_words:
                    sim = _similar(a, w)
                    if sim >= 0.8:                 # "xotin"≈"xodim" (0.8+)
                        score = max(score, 50 + sim * 10)
            else:
                # ko'p so'zli alias: nechta so'zi savolda fuzzy bor.
                hit = sum(1 for aw in a_words
                          if any(_similar(aw, w) >= 0.82 for w in q_words))
                if hit >= max(1, len(a_words) - 1):
                    score = max(score, 60 + hit * 5)
        # 3) Sarlavhadagi o'ziga xos so'zlar (fuzzy ham).
        for tw in _norm(p["title"]).split():
            if len(tw) >= 4 and tw not in _STOPWORDS:
                for w in q_words:
                    if _similar(tw, w) >= 0.85:
                        score = max(score, 40 + len(tw))
        if score > best_score:
            best_score, best = score, p
    return best if best_score >= 30 else None


def _llm_route(question: str):
    """Kalit so'z topilmasa — qwen3:8b sarlavha+xulosa ichidan loyiha tanlaydi."""
    projects = _load()
    if not projects:
        return None
    catalog = "\n".join(f"{p['n']}. {p['title'].strip(chr(34)+'“”')} — {p['summary']}"
                        for p in projects)
    sys_prompt = (
        "Quyida DASUTY kompaniyasi loyihalari ro'yxati (raqam. nomi — qisqacha). "
        "Foydalanuvchi savoliga QAYSI loyiha tegishli ekanini aniqla. "
        "FAQAT bitta raqam qaytar (1-19). Agar hech qaysi loyihaga aniq mos kelmasa, 0 qaytar. "
        "Boshqa hech narsa yozma — faqat raqam.\n\n" + catalog
    )
    try:
        out = _complete(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": question}],
            temperature=0.0, max_tokens=8,
        )
    except Exception:
        return None
    m = re.search(r"\d+", out or "")
    if not m:
        return None
    n = int(m.group())
    for p in projects:
        if p["n"] == n:
            return p
    return None


def route(question: str):
    """Savolni bitta loyihaga yo'naltiradi (kalit so'z → LLM fallback). Topilmasa None.

    (status, project) qaytaradi:
      "exact"   — kalit so'z/alias aniq mos keldi (ishonchli → javob ber).
      "guess"   — kalit so'z yo'q, LLM taxmin qildi (noaniq → aniqlashtirishni so'ra).
      "none"    — hech narsa mos kelmadi.
    """
    kw = _keyword_route(question)
    if kw is not None:
        return "exact", kw
    guess = _llm_route(question)
    if guess is not None:
        return "guess", guess
    return "none", None


_ANSWER_SYS = (
    "Sen DASUTY kompaniyasi loyihalari bo'yicha yordamchisan. Quyida foydalanuvchi "
    "so'ragan loyiha haqida ma'lumot berilgan. Shu loyihani tushuntir.\n"
    "QATTIQ QOIDALAR:\n"
    "- Foydalanuvchi shu loyiha haqida so'rayapti — DOIM shu loyihani qisqacha "
    "tushuntirib ber (savoldagi so'z matnda aynan bo'lmasa ham, loyihani tasvirla).\n"
    "- Javobni DOIM lotin o'zbek tilida yoz.\n"
    "- Faqat shu loyiha haqida gapir. Boshqa loyihalarni eslatma.\n"
    "- FAQAT oddiy gaplar yoz. Markdown, yulduzcha (*), qalin matn, raqamli yoki "
    "belgili ro'yxat MUTLAQO ISHLATMA — javob ovoz bilan o'qiladi.\n"
    "- QISQA: eng ko'pi 2 ta qisqa jumla — loyihani qisqacha tushuntir. Ortiqcha "
    "cho'zma (javob video bo'ladi). Agar 'batafsil' so'rasa, 3 jumlagacha.\n\n"
    "LOYIHA: {title}\n\n{body}"
)

_NOMATCH_PREFIX = "Bu haqda ma'lumotim yo'q. DASUTY loyihalari: "


def answer(question: str, max_tokens: int = 300) -> dict:
    """Savolga javob beradi. Loyihaga yo'naltirib, FAQAT o'sha matndan javob quradi.

    Qaytaradi: {"text": str, "project": id|None, "matched": bool}
    """
    projects = _load()
    if not projects:
        return {"text": "Loyihalar bazasi yuklanmagan.", "project": None, "matched": False}

    q = _norm(question)
    # "Qanday loyihalar bor / ro'yxat" — qisqa OG'ZAKI xulosa (hammasini sanamaymiz:
    # 19 ta nom = uzun audio = sekin video). Bir nechta misol + soni + taklif.
    if any(kw in q for kw in ("qanday loyiha", "qaysi loyiha", "loyihalar ro'yxat",
                              "nechta loyiha", "barcha loyiha", "loyihalaringiz")):
        names = list_projects()
        examples = ", ".join(names[:4])
        return {"text": f"DASUTY {len(names)} ta loyiha yaratgan, masalan: {examples}. "
                        f"Qaysi biri haqida batafsil bilmoqchisiz?",
                "project": None, "matched": True}

    status, proj = route(question)
    if status == "none":
        # Hech qaysi loyihaga mos kelmadi → qisqa rad (to'qib chiqarmaydi).
        ex = ", ".join(list_projects()[:4])
        return {"text": f"Kechirasiz, bu haqda ma'lumotim yo'q. Men DASUTY loyihalari "
                        f"haqida gapiraman, masalan: {ex}.",
                "project": None, "matched": False}
    # status "exact" YOKI "guess" — ikkalasida ham JAVOB beramiz (aniqlashtirish
    # so'ramaymiz: foydalanuvchi nomni aytdi, ortiqcha qaytib so'rash bezovta qiladi).

    sys_prompt = _ANSWER_SYS.format(title=proj["title"], body=proj["full_text"])
    # Javobni QISQA ushlab turamiz (uzun javob = uzun video = sekin). Avatar
    # bergan max_tokens katta bo'lsa ham, portfolio uchun 90 tokenga cheklaymiz.
    # 2 jumla uchun ~110 token (qisqa javob = qisqa video = tez). 'batafsil' → 3 jumla.
    detail = any(w in q for w in ("batafsil", "to'liq", "to'liqroq", "ko'proq"))
    cap = min(max_tokens, 180 if detail else 110)
    try:
        text = _complete(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": question}],
            temperature=0.3, max_tokens=cap,
        )
    except Exception as e:  # noqa: BLE001
        return {"text": f"Javob xatosi: {e}", "project": proj["id"], "matched": True}
    text = _clean_for_voice(text)
    return {"text": text, "project": proj["id"], "matched": True}


def answer_stream(question: str, max_tokens: int = 300):
    """answer()'ning OQIMLI varianti — javob matnini bo'lak-bo'lak yieldlaydi.

    Routing + maxsus holatlar (ro'yxat / mos kelmadi) bitta tayyor bo'lak bo'lib
    qaytadi; mos loyiha bo'lsa qwen3 javobi OQIM bilan keladi (ask_gpt_stream <think>
    ni tozalaydi). tts_streaming bu bo'laklarni jumlalarga yig'ib, GPT yozayotganda
    parallel sintez qiladi → kechikish GPT+TTS o'rniga ~max(GPT, TTS).
    """
    projects = _load()
    if not projects:
        yield "Loyihalar bazasi yuklanmagan."
        return

    q = _norm(question)
    if any(kw in q for kw in ("qanday loyiha", "qaysi loyiha", "loyihalar ro'yxat",
                              "nechta loyiha", "barcha loyiha", "loyihalaringiz")):
        names = list_projects()
        examples = ", ".join(names[:4])
        yield (f"DASUTY {len(names)} ta loyiha yaratgan, masalan: {examples}. "
               f"Qaysi biri haqida batafsil bilmoqchisiz?")
        return

    status, proj = route(question)
    if status == "none":
        ex = ", ".join(list_projects()[:4])
        yield (f"Kechirasiz, bu haqda ma'lumotim yo'q. Men DASUTY loyihalari "
               f"haqida gapiraman, masalan: {ex}.")
        return

    sys_prompt = _ANSWER_SYS.format(title=proj["title"], body=proj["full_text"])
    detail = any(w in q for w in ("batafsil", "to'liq", "to'liqroq", "ko'proq"))
    cap = min(max_tokens, 180 if detail else 110)
    # Har chaqiruv uchun YANGI (bo'sh) suhbat tarixi — loyihalararo "oqib ketish"
    # bo'lmasligi uchun (har javob faqat o'sha loyiha matnidan). Tugagach tozalaymiz.
    import uuid as _uuid
    from app.services.gpt import ask_gpt_stream, clear_history
    hk = "pf_" + _uuid.uuid4().hex[:12]
    try:
        for piece in ask_gpt_stream(question, system_prompt=sys_prompt,
                                    temperature=0.3, max_tokens=cap, history_key=hk):
            # ask_gpt_stream <think>'ni tozalagan; markdown belgilarini ham olib tashlaymiz.
            p = piece.replace("*", "").replace("`", "")
            if p:
                yield p
    finally:
        try:
            clear_history(hk)
        except Exception:  # noqa: BLE001
            pass


def _clean_for_voice(text: str) -> str:
    """<think> bloklari + markdown belgilarini olib tashlaydi (TTS toza o'qisin)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\*+", "", text)            # **qalin** / *kursiv* yulduzchalari
    text = re.sub(r"(?m)^\s*[-•]\s*", "", text)  # ro'yxat belgilari
    text = re.sub(r"`+", "", text)
    return text.strip()
