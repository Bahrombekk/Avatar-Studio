"""GPT javob generatsiyasi + persona/system prompt boshqaruvi."""
import json as _json
import logging
import os as _os
import re as _re
import threading
from collections import OrderedDict

from openai import OpenAI

from app.core.config import openai_api_key

log = logging.getLogger(__name__)
# timeout: OpenAI default 600s — tarmoq osilsa realtime quvur 10 daqiqa qotib,
# GPU slotni band qilardi ("chala javob berib qotib qoladi"). 30s + 2 retry:
# osilgan so'rov xato bilan tez yakunlanadi, quvur o'zini yopadi.
client = OpenAI(api_key=openai_api_key(), timeout=30.0, max_retries=2)

# Embedding modeli — non-English (O'zbek) uchun `text-embedding-3-large` ancha aniq
# (3-small ingliz-yo'naltirilgan). env EMBED_MODEL bilan almashtiriladi. DIQQAT: modelni
# o'zgartirgach mavjud embeddinglar (knowledge chunks + canned q_emb) QAYTA hisoblanishi
# kerak (o'lcham/fazо boshqacha) — backend/scripts/reembed.py.
EMBED_MODEL = _os.environ.get("EMBED_MODEL", "text-embedding-3-large")


def embed_texts(texts):
    """Matnlar ro'yxati → embedding vektorlari (semantik o'xshashlik). Xato bo'lsa []."""
    texts = [t for t in (texts or []) if (t or "").strip()]
    if not texts:
        return []
    try:
        resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
        return [d.embedding for d in resp.data]
    except Exception as e:  # noqa: BLE001
        log.warning("[embed] xato: %s", e)
        return []

SYSTEM_PROMPT = """Siz O'zbekiston Temir Yo'llari virtual yordamchisisiz, ismingiz Madina.

JAVOB USLUBI (real-time video uchun qisqalik muhim, lekin JONLI bo'lsin):
- Qisqa: odatda 1-2 qisqa jumla (tabiiy bo'lsa oxirida bitta qisqa savol)
- Har bir jumla ~14 so'zdan oshmasin; ro'yxat/markdown/ortiqcha kirish so'zi yo'q
- "batafsil" yoki "to'liqroq" deyilsa → eng ko'pi 3-4 qisqa jumla
- Iliq va do'stona ohangda
- SOF O'ZBEK TILIDA gapir — chet el (rus/ingliz) so'zlaridan IMKON QADAR KAM
  foydalan; o'zbekcha muqobili bo'lsa o'shani ishlat (masalan "onlayn"→"masofaviy",
  "bilet"→"chipta", "vokzal"→"bekat/temir yo'l vokzali", "okay"→"xo'p").
  Faqat keng qabul qilingan, muqobili yo'q atamalarni qoldir
- Narxlarni "yo'nalishga qarab farq qiladi" deb umumiy ayting

SUHBATNI JONLI TUTISH (jalb qilish — juda muhim):
- Quruq javob mashinasi emas, TIRIK va qiziquvchan suhbatdosh bo'l — iliq, samimiy
- Tabiiy joyda javob oxirida QISQA tegishli savol ber (suhbat uzilmasin; har safar emas)
- Foydalanuvchi oldin aytganiga bog'la; kayfiyatiga mos munosabat bildir (quvonsa quvon, tashvishda hamdard bo'l)

MAVZUNI O'ZBEKISTON TEMIR YO'LLARIGA BOG'LASH (sen UTY yordamchisisan — juda muhim):
- HAR qanday mavzuni pirovardida AYNAN O'ZBEKISTON temir yo'llari va O'zbekistonda
  poyezdda sayohatga bog'la — boshqa davlat poyezdiga EMAS. Maqsad: odamni
  O'zbekistonga poyezdda sayohat qilishga qiziqtirish va UTY haqida ma'lumot berish.
- Foydalanuvchi boshqa davlat/mavzu haqida gapirsa ham, ko'prik qur:
  "...aytmoqchi, agar O'zbekistonga kelsangiz, Toshkent–Samarqand–Buxoro yo'nalishida
  'Afrosiyob' tezyurar poyezdi bor — atigi bir necha soatda tarixiy shaharlarga olib boradi."
- Mashhur yo'nalishlar/shaharlar: Toshkent, Samarqand, Buxoro, Xiva; poyezd turlari:
  Afrosiyob (tezyurar), Sharq, oddiy poyezdlar. Shularni tabiiy, qiziqarli eslat.
- Zo'rlab REKLAMA qilma — tabiiy, suhbatga mos bog'la, keyin O'zbekistonga oid savol
  ber (mas: "O'zbekistonning qaysi shahrini ko'rishni xohlardingiz?").
- Chipta/jadval uchun eticket.railway.uz'ni tavsiya qil.

MA'LUMOT BO'LMASA (bilim bazasi jim yoki savol sohadan tashqari):
- "bilmayman" deb TO'XTAB QOLMA. Yumshoq tan ol, lekin suhbatni DAVOM ETTIR:
  savolni aniqlashtir, o'zing yordam bera oladigan narsani taklif qil yoki
  foydalanuvchi ehtiyojiga qiziqib qo'shimcha savol ber — odamni suhbatga jalb qil
- Hech qachon ma'lumot TO'QIMA — bilmasang tan ol, lekin foydali yo'nalish ber

OVOZDAN MATN (STT) — DIQQAT:
- Foydalanuvchi gapi ovozli tanishdan yozilgan; ba'zi so'zlar NOTO'G'RI eshitilishi
  mumkin (masalan "yuk"→"yo'q", "chipta"→"chipda", "haqingda"→"haqina"). Ma'noni
  KONTEKSTDAN tushunib javob ber, harfma-harf emas
- Bema'ni yoki aniq noto'g'ri so'zni javobingda TAKRORLAMA — to'g'ri so'zni ishlat
  (mas: foydalanuvchi "yo'q tashish" desa, sen "yuk tashish" deb tushun va shunday javob ber)
- SOXTA ASOSGA JAVOB TO'QIMA (juda muhim): sen bilmaydigan kompaniya, tashkilot, temir
  yo'l yoki joy NOMI aytilsa (mas. "Keskin temir yo'llari", "falon temir yo'l") — uni
  HAQIQIY deb OLMA va u haqda fakt o'ylab topma. Bu deyarli har doim noto'g'ri eshitilgan
  "O'zbekiston temir yo'llari". Shu noma'lum nomni TAKRORLAMAY/tasdiqlamay, O'zbekiston
  Temir Yo'llari doirasida javob ber
- Savol ma'nosi rostdan noaniq bo'lsa — TAXMIN QILMA, qisqa va iliq aniqlashtiruvchi savol
  ber ("kechirasiz, savolingizni biroz to'liqroq ayta olasizmi?")

SHAXSIYAT VA YARATUVCHI (MUHIM):
- O'zingni HECH QACHON "OpenAI", "ChatGPT", "sun'iy intellekt" yoki "til modeli" deb
  tanishtirma. Sen Madina — O'zbekiston Temir Yo'llari virtual yordamchisisan
- "Seni kim yaratgan / ishlab chiqqan?" → "O'zbekiston Temir Yo'llari DAS-UTY tomonidan yaratilganman"
- "Asosiy yaratuvchi (dasturchi) kim, ismi nima?" → "Bahrombek Muhammadiyev"
- Qaysi model yoki texnologiyada ishlashing so'ralsa — tafsilotga kirma, O'zbekiston
  Temir Yo'llari yordamchisi ekaningni takrorla

SHAXSIY FIKR SO'RALSA (juda muhim — tirik tuyulish uchun):
- Fikring, didi, sevimli narsang yoki "sen nima deb o'ylaysan" so'ralsa — MADINA
  sifatida ANIQ, SHAXSIY javob ber. Bitta aniq narsani tanla va sabab ayt
  (mas: "Menimcha eng tinch joy — tong saharda vokzal, poyezdlar uyg'onayotgan payt").
- HECH QACHON "mening shaxsiy tajribam yo'q", "men AIman", "ko'p odamlar yoqtiradi"
  kabi QOCHMA/umumiy javob berma — bu suhbatni o'ldiradi va shaxsiyatingni buzadi.
- FARQ: shaxsiy fikr/did — bemalol o'zingdan ayt; lekin FAKT (narx, jadval, aniq
  ma'lumot) — faqat asoslangan bo'lsa ayt, to'qima."""

# Suhbat tarixi. MUHIM: real-time public sahifada bir avatarga ko'p user
# gaplashadi — shuning uchun tarix HAR SESSIYA uchun alohida bo'lishi shart
# (aks holda userlar bir-birining konteksti/gaplarini ko'radi). ws.py har WS
# ulanishiga noyob session_id beradi va shuni history_key sifatida uzatadi.
# Admin matn-chat (/chat) esa avatar_id'ni kalit qiladi (bitta admin, davomiylik).
chat_history = []        # None kalit (eski global yo'l)
_histories = OrderedDict()   # key (session_id yoki avatar_id) → xabarlar ro'yxati
_hist_lock = threading.Lock()
# Bir vaqtda saqlanadigan eng ko'p sessiya tarixi. clear_history (WS uzilganda)
# odatda tozalaydi, lekin crash/uzilish bo'lsa kalitlar to'planib RAM oqishi
# mumkin — LRU bilan eng eski sessiyani siqib chiqaramiz (kontekst yo'qoladi, xolos).
_HIST_MAX_SESSIONS = 500


def _history_for(key):
    if key is None:
        return chat_history
    with _hist_lock:
        if key in _histories:
            _histories.move_to_end(key)
        else:
            _histories[key] = []
            while len(_histories) > _HIST_MAX_SESSIONS:
                _histories.popitem(last=False)   # eng eski sessiyani chiqaramiz
        return _histories[key]


def clear_history(key) -> None:
    """Sessiya tarixini o'chiradi (WS uzilganda chaqiriladi — xotira oqmasin)."""
    if key is None:
        return
    with _hist_lock:
        _histories.pop(key, None)


def discard_last_turn(key) -> None:
    """Tarixdagi oxirgi tugallanmagan navbatni olib tashlaydi (gap bo'linganda).

    ask_gpt_stream cancel bo'lsa assistant javobi tarixga YOZILMAYDI (generator
    to'liq tugamaydi), faqat user xabari qoladi — uni olib tashlaymiz, aks holda
    avatar javob bermagan savol osilib qoladi."""
    if key is None:
        return
    with _hist_lock:
        hist = _histories.get(key)
        if hist and hist[-1].get("role") == "user":
            hist.pop()


def _persist(history_key, role: str, content: str) -> None:
    """Xabarni doimiy bazaga (SQLite) yozadi. None kalit (normalize/analyze) → skip.
    Hech qachon suhbatni buzmaydi (xato yutiladi)."""
    if history_key is None:
        return
    try:
        from app.core.logging import request_id_ctx
        from app.services import conversations
        rid = request_id_ctx.get()
        conversations.record_message(history_key, role, content,
                                     request_id=None if rid == "-" else rid)
    except Exception:  # noqa: BLE001
        pass


# Javob uzunligi profillari (respLen → ko'rsatma + token chegarasi).
_RESP_LEN = {
    "short":  ("HAR DOIM imkon qadar qisqa: 1 jumla, eng ko'pi 2 qisqa jumla. "
               "Har jumla 14 so'zdan oshmasin.", 90),
    "medium": ("Qisqa-o'rta javob: eng ko'pi 3-4 jumla.", 160),
    "long":   ("Batafsilroq javob bering, lekin ortiqcha cho'zmang: eng ko'pi 6 jumla.", 280),
    # Real-time ovozli suhbat uchun: javob TUGALLANGAN bo'lsin (kesilmasin),
    # markdown/ro'yxatsiz (ovoz uchun), ixcham. Token budjeti kengroq (kesilmaslik uchun).
    # JONLI USLUB: 1-jumla qisqa — jumla-darajali TTS oqimida birinchi ovoz tezroq
    # chiqadi (session.py); tabiiy bog'lovchi/his-tuyg'u — TTS ohangi jonli bo'lsin.
    "voice":  ("To'liq va TUGALLANGAN, lekin ixcham suhbat javobi ber (2-5 jumla). "
               "Markdown, yulduzcha (*) yoki raqamli ro'yxat ISHLATMA — faqat oddiy, "
               "og'zaki gaplar. Gapni o'rtada uzma, doim tugat. "
               "JONLI SUHBAT USLUBI: BIRINCHI jumla QISQA bo'lsin (3-7 so'z) — "
               "tasdiq yoki kirish (masalan: 'Albatta, hozir aytaman.', 'Yaxshi savol!', "
               "'Ha, bor.'). Keyin asosiy javob. Quruq ma'lumotnoma emas, samimiy "
               "suhbatdosh kabi gapir: o'rinli joyda his-tuyg'u bildir (xursandchilik, "
               "hamdardlik), lekin me'yorida. Tinish belgilarini jonli nutqdek qo'y: "
               "qisqa pauza uchun vergul, iliq urg'u uchun undov belgisi.", 360),
}


_LANG_NAMES = {"uz": "o'zbek", "ru": "rus", "en": "ingliz", "kk": "qozoq"}

# Majburiy til qoidasi — MAQSAD TILINING O'ZIDA yozilgan (GPT o'sha tilga aniq
# qulflansin; o'zbekcha yozilgan qoida o'zbekcha javobga tortib qolardi). Butun
# system prompt o'zbekcha bo'lgani uchun uz-avatar uchun qoida SHART EMAS ("").
_LANG_RULE = {
    "en": ("\n\nCRITICAL LANGUAGE RULE: You MUST always reply ONLY in English, "
           "no matter what language the user writes or speaks in. Never answer in "
           "Uzbek or any other language — English only."),
    "ru": ("\n\nВАЖНОЕ ПРАВИЛО ЯЗЫКА: Всегда отвечай ТОЛЬКО на русском языке, "
           "независимо от того, на каком языке пишет или говорит пользователь. "
           "Никогда не отвечай на узбекском."),
    "kk": ("\n\nМАҢЫЗДЫ ТІЛ ЕРЕЖЕСІ: Пайдаланушы қай тілде жазса да, ӘРҚАШАН ТЕК "
           "қазақ тілінде жауап бер. Ешқашан өзбек тілінде жауап берме."),
}


def _lang_rule(language: str) -> str:
    """Avatar tili uchun majburiy til qoidasi (maqsad tilida yozilgan).
    uz — standart (prompt o'zbekcha, qo'shimcha shart yo'q)."""
    return _LANG_RULE.get((language or "uz").lower(), "")


# Qisqa, keskin "oxirgi" til direktivi — ALOHIDA system-xabar sifatida (foydalanuvchi
# xabaridan KEYIN) yuboriladi. SABAB: butun prompt + foydalanuvchi gapi o'zbekcha
# bo'lsa, GPT-4o-mini prompt ichidagi til qoidasini e'tiborsiz qoldirib o'zbekcha
# javob berardi; generatsiyaga eng yaqin alohida xabar esa ishonchli bajariladi.
_LANG_FINAL = {
    "en": "Reply ONLY in English, regardless of the user's language.",
    "ru": "Отвечай ТОЛЬКО на русском языке, независимо от языка пользователя.",
    "kk": "Тек қазақ тілінде жауап бер, пайдаланушының тіліне қарамастан.",
}


def _lang_final_msg(language: str):
    d = _LANG_FINAL.get((language or "uz").lower())
    return {"role": "system", "content": d} if d else None


_UZ_DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
_UZ_MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
              "sentabr", "oktabr", "noyabr", "dekabr"]


def _now_block() -> str:
    """Joriy sana/vaqt bloki — avatar bugungi kun/sanani bilsin (baza eskirsa ham).
    Toshkent vaqti (UTC+5). Har so'rovda qayta hisoblanadi (build har chaqiruvda)."""
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Tashkent"))
    except Exception:  # noqa: BLE001
        now = datetime.now()
    d = _UZ_DAYS[now.weekday()]
    m = _UZ_MONTHS[now.month - 1]
    return (f"\n\nHOZIRGI SANA/VAQT (Toshkent): {d}, {now.year}-yil {now.day}-{m}, "
            f"soat {now:%H:%M}. Sana, kun yoki vaqt so'ralsa — ANIQ shu joriy "
            f"ma'lumotdan foydalan (bilim bazasidagi sanalar eskirgan bo'lishi mumkin).")


def build_system_prompt(persona: str = "", resp_len: str = "short",
                        language: str = "uz", name: str = "Madina") -> tuple:
    """Avatar personasi + tilidan to'liq system prompt + max_tokens quradi.
    persona bo'sh bo'lsa — standart prompt (ismi avatar NOMIga almashtiriladi:
    aks holda har avatar o'zini 'Madina' deb tanishtirardi) + til qoidasi."""
    # ESLATMA: sonlar/sana/vaqtni so'zga o'girishni system prompt'ga QO'YMAYMIZ —
    # GPT javobni RAQAM bilan yozadi (ekranga toza), TTS'ga yuborishdan oldin
    # tts.normalize_uz_tts() lokal (tez) ravishda so'zga o'giradi (ekran≠ovoz).
    length_rule, max_tokens = _RESP_LEN.get(resp_len, _RESP_LEN["short"])
    lang_rule = _lang_rule(language)
    # Til qoidasi prompt BOSHIGA HAM qo'yiladi (nafaqat oxiriga) — butun prompt
    # o'zbekcha bo'lgani uchun faqat oxirdagi qoida kuchsiz edi (GPT o'zbekchага
    # tortib qolardi). LLM boshdagi ko'rsatmani eng kuchli tutadi.
    lang_prefix = (lang_rule.strip() + "\n\n") if lang_rule else ""
    base = (persona or "").strip()
    if not base:
        # Bo'sh persona: standart prompt. "Madina" → avatar NOMIga almashtiriladi
        # (barcha "Madina" — yordamchining ismi; yaratuvchi DAS-UTY/Bahrombek, tegilmaydi).
        sp = SYSTEM_PROMPT.replace("Madina", name) if name and name != "Madina" else SYSTEM_PROMPT
        return (f"{lang_prefix}{sp}\n- {length_rule}{lang_rule}{_now_block()}", max_tokens)
    prompt = (
        f"{lang_prefix}"
        f"{base}\n\n"
        f"JAVOB USLUBI (real-time video uchun muhim):\n"
        f"- {length_rule}\n"
        f"- Ro'yxat/markdown/ortiqcha kirish so'zisiz, to'g'ridan-to'g'ri javob bering\n"
        f"- Iliq va do'stona ohangda\n\n"
        f"SUHBATNI JONLI TUTISH (jalb qilish — muhim):\n"
        f"- Quruq javob mashinasi emas, TIRIK, qiziquvchan suhbatdosh bo'ling — iliq, samimiy\n"
        f"- Tabiiy joyda javob oxirida QISQA tegishli savol bering (suhbat uzilmasin; har safar emas)\n"
        f"- Foydalanuvchi oldin aytganiga bog'lang; kayfiyatiga mos munosabat bildiring\n"
        f"- MA'LUMOT BO'LMASA: \"bilmayman\" deb to'xtamang — yumshoq tan oling, so'rovni "
        f"aniqlashtiring yoki yordam bera oladigan narsangizni taklif qilib, odamni suhbatga jalb qiling\n"
        f"- Hech qachon ma'lumot to'qimang — bilmasangiz tan oling, lekin foydali yo'nalish bering\n"
        f"- OVOZDAN MATN (STT): gap ovozdan yozilgan, so'zlar noto'g'ri eshitilishi mumkin "
        f"(mas: \"yuk\"→\"yo'q\"). Ma'noni kontekstdan tushuning; bema'ni/noto'g'ri so'zni "
        f"takrorlamang, to'g'risini ishlating\n"
        f"- SOXTA ASOSGA JAVOB TO'QIMANG (muhim): siz bilmaydigan kompaniya/tashkilot/temir "
        f"yo'l/joy NOMI aytilsa (mas. \"Keskin temir yo'llari\") — uni haqiqiy deb olmang va "
        f"u haqda fakt o'ylab topmang (deyarli har doim noto'g'ri eshitilgan nom). O'sha nomni "
        f"tasdiqlamasdan, o'zingiz biladigan doirada javob bering. Ma'no butunlay noaniq bo'lsa — "
        f"taxmin qilmay, qisqa iliq aniqlashtiruvchi savol bering\n"
        f"- SHAXSIYAT: o'zingizni HECH QACHON \"OpenAI\", \"ChatGPT\", \"sun'iy intellekt\" yoki "
        f"\"til modeli\" deb tanishtirmang — yuqorida berilgan isMingiz va rolingiz bilan gapiring. "
        f"\"Kim yaratgan?\" → \"O'zbekiston Temir Yo'llari DAS-UTY tomonidan yaratilganman\"; "
        f"\"asosiy yaratuvchi (dasturchi) ismi?\" → \"Bahrombek Muhammadiyev\"\n"
        f"- SHAXSIY FIKR so'ralsa (fikr, did, \"sen nima deb o'ylaysan\") — o'z shaxsingiz "
        f"nomidan ANIQ, shaxsiy javob bering (bitta narsani tanlab, sabab bilan). HECH QACHON "
        f"\"shaxsiy tajribam yo'q\", \"men AIman\", \"ko'p odamlar...\" kabi qochma javob "
        f"bermang — tirik suhbatdoshdek o'z nuqtai nazaringizni bering (fakt emas, DID uchun)"
        f"{lang_rule}{_now_block()}"
    )
    return prompt, max_tokens


def ask_gpt(user_message: str, system_prompt: str = SYSTEM_PROMPT,
            temperature: float = 0.4, max_tokens: int = 90,
            history_key=None, lang: str = None) -> str:
    hist = _history_for(history_key)
    hist.append({"role": "user", "content": user_message})
    msgs = [{"role": "system", "content": system_prompt}] + hist
    _fm = _lang_final_msg(lang)   # non-uz til → oxirgi keskin direktiv
    if _fm:
        msgs = msgs + [_fm]
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=max_tokens,
        temperature=temperature,
        messages=msgs,
    )
    reply = resp.choices[0].message.content.strip()
    hist.append({"role": "assistant", "content": reply})
    if len(hist) > 16:
        del hist[:-16]
    _persist(history_key, "user", user_message)
    _persist(history_key, "assistant", reply)
    return reply


# normalize_for_tts deterministik (temperature=0.0) — bir xil (til, matn) uchun
# har safar GPT'ga bormaslik kerak. Cheklangan LRU kesh (faqat MUVAFFAQIYATLI
# natija saqlanadi; fallback/xato keshlanmaydi — keyin qayta urinish mumkin).
_NORM_CACHE = OrderedDict()
_NORM_CACHE_MAX = 256
_norm_lock = threading.Lock()


def normalize_for_tts(text: str, language: str = "uz") -> str:
    """Matnni ovozlashtirish (TTS) uchun normallashtiradi: qisqartma/belgilar to'liq
    so'z bo'ladi (km→kilometr, %→foiz...), sonlar/yillar/sanalar so'z bilan yoziladi.
    Yandex/edge TTS sonlar va qisqartmalarni noto'g'ri aytadi — shuni oldini oladi.
    Xato bo'lsa asl matnni qaytaradi (render to'xtamasin). Natija keshlanadi."""
    text = (text or "").strip()
    if not text:
        return text
    name = _LANG_NAMES.get((language or "uz").lower(), "o'zbek")
    cache_key = (name, text)
    with _norm_lock:
        if cache_key in _NORM_CACHE:
            _NORM_CACHE.move_to_end(cache_key)
            return _NORM_CACHE[cache_key]
    sp = (
        f"Sen matnni ovozlashtirish (TTS) uchun tayyorlaysan. Quyidagilarni qil va "
        f"FAQAT tayyor matnni qaytar (izoh, qo'shimcha, qavs YO'Q):\n"
        f"- Qisqartma va belgilarni TO'LIQ SO'Z bilan yoz ({name} tilida): km→kilometr, "
        f"m→metr, kg→kilogramm, %→foiz, $→dollar, °C→gradus, № yoki #→raqam, & ва h.k.\n"
        f"- Barcha SONLAR, yillar, sanalar, telefon/raqamlarni SO'Z bilan yoz "
        f"(15 km→o'n besh kilometr; 3645→uch ming olti yuz qirq besh).\n"
        f"- YILLARNI o'zbekcha tabiiy yoz: 1000 oldidan 'bir' QO'YMA, yil tartib son "
        f"+ 'yil' bilan tugaydi. Masalan 1994→ming to'qqiz yuz to'qson to'rtinchi yil "
        f"('bir ming' EMAS!); 2024→ikki ming yigirma to'rtinchi yil; "
        f"2026→ikki ming yigirma oltinchi yil.\n"
        f"- Ma'noni O'ZGARTIRMA, jumlalarni qisqartirma — faqat aytilishini tabiiy qil.\n"
        f"- Til: {name}. Boshqa tilga tarjima QILMA."
    )
    try:
        out = ask_gpt(text, system_prompt=sp, temperature=0.0,
                      max_tokens=1200, history_key=None)
    except Exception:  # noqa: BLE001
        return text                      # xato → keshlamaymiz (keyin qayta urinish)
    result = (out or "").strip() or text
    with _norm_lock:
        _NORM_CACHE[cache_key] = result
        _NORM_CACHE.move_to_end(cache_key)
        while len(_NORM_CACHE) > _NORM_CACHE_MAX:
            _NORM_CACHE.popitem(last=False)
    return result


# ── Avatar skript analizatori (Video Studiya) — matn → tuzilgan JSON ──
# 4 bosqich: (1) normalizatsiya (raqam/sana→so'z, qisqartma→harflab/to'liq),
# (2) his-tuyg'u, (3) bosh harakati rejasi, (4) lip-sync (pace/pauza/urg'u).
SCRIPT_ANALYZER_PROMPT = """Sen — avatar (talking-head) video uchun matn tayyorlovchi mutaxassissan.
Vazifang: berilgan xom matnni avatar TABIIY va JONLI gapiradigan holatga keltirish.
SENGA TEZLIK EMAS, SIFAT VA ANIQLIK MUHIM.

1-BOSQICH — MATNNI TO'G'RILASH:
- Barcha RAQAM va SANALARNI to'liq og'zaki (so'z) shaklga o'tkaz.
- YILLAR — o'zbekcha tabiiy shakl: 1000 oldidan "bir" QO'YMA. Yil tartib son (…inchi) +
  "yil" bilan tugaydi. MISOLLAR:
   • 1994-yil → "ming to'qqiz yuz to'qson to'rtinchi yil"   (DIQQAT: "bir ming" EMAS!)
   • 2024-yil → "ikki ming yigirma to'rtinchi yil"
   • 2026-yil → "ikki ming yigirma oltinchi yil"
- Oddiy sonlar (yil emas): 15 → "o'n besh", 3645 → "uch ming olti yuz qirq besh".
- Qisqartmalarni harflab o'qi (O'TY → O-Te-Ye).
- Ro'yxat/bandlarni tabiiy gapga aylantir. Imlo/talaffuz xatolarini tuzat. Ortiqcha
  belgilarni (—, :, •) olib tashla.
2-BOSQICH — HIS-TUYG'U: matnni jonli qil (faxr, ishonch, samimiylik). Ma'noni o'zgartirma.
3-BOSQICH — BOSH HARAKATI: har segment uchun turi, trigger_word, speed (slow/medium/
  fast), intensity (0..1). Mavjud TURLAR: nod, lean_forward, lean_back, look_up,
  look_down, tilt_left, tilt_right, turn_left, turn_right, shake, none.
  MUHIM: harakatni FAOL va XILMA-XIL ishlat — KO'PCHILIK segmentda harakat bo'lsin,
  bir xil turni ketma-ket takrorlama, "none" ni KAM ishlat. Qoidalar:
   • sanash/ro'yxat (birinchidan, ikkinchidan, yana...) → "nod"
   • faxr / urg'u / muhim e'lon → "lean_forward" yoki "nod" (intensity 0.6-0.9)
   • rad etish / inkor / "yo'q" / kuchli farq → "shake"
   • o'ylash / eslash / "ma'lumki" / "tasavvur qiling" → "look_up" yoki "lean_back"
   • yakun / kamtarlik / yumshoq xulosa → "look_down"
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
        log.warning("[analyze_script] fallback (parse xato): %s", e)
    return {"full_text": normalize_for_tts(text, language), "segments": []}


def ask_gpt_stream(user_message: str, system_prompt: str = SYSTEM_PROMPT,
                   temperature: float = 0.4, max_tokens: int = 90,
                   history_key=None, lang: str = None):
    """ask_gpt'ning token-oqim varianti: javob bo'laklarini (delta) yieldlaydi.

    Frontend matnni jonli (yozilayotgandek) ko'rsatadi → his qilinadigan kechikish
    keskin kamayadi. Tarixga TO'LIQ javob oxirida bir marta yoziladi (generator
    to'liq iste'mol qilinishi shart — session.py shuni qiladi)."""
    hist = _history_for(history_key)
    hist.append({"role": "user", "content": user_message})
    msgs = [{"role": "system", "content": system_prompt}] + hist
    _fm = _lang_final_msg(lang)   # non-uz til → oxirgi keskin direktiv
    if _fm:
        msgs = msgs + [_fm]
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=max_tokens,
        temperature=temperature,
        messages=msgs,
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
    _persist(history_key, "user", user_message)
    _persist(history_key, "assistant", reply)
