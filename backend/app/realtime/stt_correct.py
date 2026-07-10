"""STT transkriptini DOMEN bo'yicha tuzatish (o'zbek).

Yandex SpeechKit v3'da fraza-kontekst / lug'at biasing YO'Q (RecognitionModelOptions
faqat model/format/til/normalizatsiya) — shuning uchun STT ba'zi domen nomlarini buzib
eshitganda (mas. "O'zbekiston temir yo'llari" → "keskin temir yo'llari") yakuniy matnni
DETERMINISTIK to'g'rilaymiz. Bu ham ekranga ko'rinadigan transkriptni, ham GPT ko'radigan
matnni tuzatadi (natijada avatar noto'g'ri narsaga javob bermaydi).

Ro'yxat oson kengaytiriladi: foydalanuvchi yangi noto'g'ri eshitishni aytsa — shu yerga
(naqsh, to'g'ri shakl) qo'shiladi. Faqat ANIQ domen naqshlari (yolg'on tuzatish bo'lmasin).
"""
import logging
import re

from app.services.knowledge import norm_uz

log = logging.getLogger(__name__)

# (regex, almashtiruv) — registrsiz, apostrof-kanonik ("'" = U+0027) matnda ishlaydi.
# Naqshlar ANIQ bo'lsin (kontekst bilan), aks holda to'g'ri so'zni buzadi.
_RULES_UZ = [
    # Kompaniya nomi — "O'zbekiston temir yo'llari" noto'g'ri eshitilgan variantlari.
    # "kes..." (keskin/kesin/kesim...) + "temir yo'l" → deyarli har doim shu nom.
    (re.compile(r"\bkes\w*\s+temir\s+yo'?l\w*", re.IGNORECASE), "O'zbekiston temir yo'llari"),
    # "o'zbekistan/uzbekiston" imlo variantlari + "temir yo'l" → kanonik nom.
    (re.compile(r"\b(o'?zbekist[oa]n|uzbekist[oa]n)\s+temir\s+yo'?l\w*", re.IGNORECASE),
     "O'zbekiston temir yo'llari"),
    # Afrosiyob poyezdi noto'g'ri eshitilgan variantlari.
    (re.compile(r"\bafro?sib\b|\bafrosiyop\b|\bafrasiyob\b", re.IGNORECASE), "Afrosiyob"),
]


def correct_transcript(text: str, lang: str = "uz") -> str:
    """STT matnini domen bo'yicha to'g'rilaydi. Faqat o'zbek uchun (hozircha).
    O'zgarish bo'lsa log qiladi. Xavfsiz: naqsh mos kelmasa matn o'zgarmaydi."""
    text = (text or "").strip()
    if not text or (lang or "uz").lower() not in ("uz", "uz-uz"):
        return text
    out = norm_uz(text)
    for rx, repl in _RULES_UZ:
        out = rx.sub(repl, out)
    if out != text:
        log.info("[stt-correct] %r -> %r", text, out)
    return out
