"""O'zbekcha TTS normalizatori — matndagi RAQAM/sana/vaqt/klass kodlarini SO'Zga
o'giradi (Yandex/edge TTS to'g'ri o'qishi uchun). LOKAL va TEZ (GPT chaqiruvi yo'q).

Maqsad: ekranda RAQAM ko'rinadi (toza), TTS'ga SO'Z ketadi (to'g'ri talaffuz).
Misol: "311000 so'm" → "uch yuz o'n bir ming so'm"; "1С" → "bir si";
       "08:00" → "soat sakkiz"; "10.06.2026" → "10-iyun"; "768Ф" → "yetti yuz oltmish sakkiz ef".
"""
import re

_ONES = ["", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz"]
_TENS = ["", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson"]
_MONTHS = {1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel", 5: "may", 6: "iyun",
           7: "iyul", 8: "avgust", 9: "sentyabr", 10: "oktyabr", 11: "noyabr", 12: "dekabr"}
# Klass/poyezd kodidagi harf → o'qilishi (kiril va lotin).
_LETTER = {"С": "si", "C": "si", "В": "ve", "B": "ve", "П": "pe", "P": "pe", "Л": "el",
           "Е": "ye", "E": "ye", "У": "u", "U": "u", "К": "ka", "K": "ka", "Д": "de",
           "D": "de", "М": "em", "M": "em", "Г": "ge", "Ф": "ef", "F": "ef", "Н": "en",
           "Т": "te", "T": "te", "А": "a", "A": "a", "Р": "er", "R": "er"}


def _three(n: int) -> str:
    """0..999 → o'zbekcha so'z."""
    out = []
    h, r = divmod(n, 100)
    if h:
        out.append("yuz" if h == 1 else f"{_ONES[h]} yuz")
    t, o = divmod(r, 10)
    if t:
        out.append(_TENS[t])
    if o:
        out.append(_ONES[o])
    return " ".join(out)


def num_to_uz(n: int) -> str:
    """Butun son → o'zbekcha so'z (milliardgача)."""
    if n == 0:
        return "nol"
    parts = []
    for val, name in ((1_000_000_000, "milliard"), (1_000_000, "million"), (1_000, "ming")):
        q, n = divmod(n, val)
        if q:
            parts.append(f"{_three(q)} {name}")
    if n:
        parts.append(_three(n))
    return " ".join(parts).strip()


def _ordinal(word: str) -> str:
    """O'zbekcha tartib son: oxirgi so'zga '-inchi'/'-nchi' qo'shadi (unli uyg'unligi).
    o'n→o'ninchi, yigirma→yigirmanchi, besh→beshinchi, 'o'n bir'→'o'n birinchi'."""
    parts = word.split()
    last = parts[-1]
    suff = "nchi" if last[-1] in "aeiouʻ’'" else "inchi"
    parts[-1] = last + suff
    return " ".join(parts)


def _seat(m):
    return f"{num_to_uz(int(m.group(1)))} {_LETTER.get(m.group(2), m.group(2))}"


def _date(m):
    d, mo = int(m.group(1)), int(m.group(2))
    if 1 <= mo <= 12 and 1 <= d <= 31:
        return f"{_ordinal(num_to_uz(d))} {_MONTHS[mo]}"   # "o'ninchi iyun"
    return m.group(0)


def _date_iso(m):
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1 <= mo <= 12 and 1 <= d <= 31:
        return f"{_ordinal(num_to_uz(d))} {_MONTHS[mo]}"
    return m.group(0)


def _time(m):
    h, mi = int(m.group(1)), int(m.group(2))
    if mi == 0:
        return f"soat {num_to_uz(h)}"
    return f"soat {num_to_uz(h)} {num_to_uz(mi)} daqiqa"


def _num(m):
    s = m.group(0).replace(" ", "").replace(" ", "")
    return num_to_uz(int(s))


def normalize_uz_tts(text: str) -> str:
    """Matndagi raqam/sana/vaqt/klass kodlarini o'zbekcha so'zga o'giradi."""
    if not text:
        return text
    # 1) Klass/poyezd kodi: raqam + bitta harf (1С, 2В, 768Ф) — RAQAMLARDAN OLDIN.
    text = re.sub(r"\b(\d{1,4})([A-Za-zА-Яа-яЁё])\b", _seat, text)
    # 2) Sana: dd.mm.yyyy / dd.mm / yyyy-mm-dd → "kun-oy".
    text = re.sub(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", _date, text)
    text = re.sub(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", _date_iso, text)
    text = re.sub(r"\b(\d{1,2})\.(\d{1,2})\b(?!\d)", _date, text)
    # 3) Vaqt: HH:MM → "soat ...".
    text = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", _time, text)
    # 4) Narx/son: bo'shliqli guruh (300 560) yoki oddiy son → so'z.
    text = re.sub(r"\d{1,3}(?:[  ]\d{3})+|\d+", _num, text)
    return text
