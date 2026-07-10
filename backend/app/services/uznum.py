"""O'zbekcha TTS normalizatori — matndagi RAQAM/sana/vaqt/klass kodlarini SO'Zga
o'giradi (Yandex/edge TTS to'g'ri o'qishi uchun). LOKAL va TEZ (GPT chaqiruvi yo'q).

Maqsad: ekranda RAQAM ko'rinadi (toza), TTS'ga SO'Z ketadi (to'g'ri talaffuz).
Misol: "311000 so'm" → "uch yuz o'n bir ming so'm"; "1С" → "bir si";
       "08:00" → "soat sakkiz"; "10.06.2026" → "10-iyun"; "768Ф" → "yetti yuz oltmish sakkiz ef".
"""
import re

_ONES = ["", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz"]
_TENS = ["", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson"]
# Ko'p harfli / belgili birliklar (SONdan keyin → to'liq so'z). Bir harfli m/g/l/t
# alohida (_UNITS1) — faqat BO'SHLIQ bilan (tasodifiy so'zga tegmasin).
_UNITS = {"km/soat": "kilometr soatiga", "km/h": "kilometr soatiga",
          "km": "kilometr", "kg": "kilogramm", "sm": "santimetr", "mm": "millimetr",
          "ml": "millilitr", "kv.m": "kvadrat metr", "m2": "kvadrat metr",
          "m²": "kvadrat metr", "m3": "kub metr", "m³": "kub metr",
          "gb": "gigabayt", "mb": "megabayt", "tb": "terabayt",
          "°c": "daraja", "°": "daraja"}
# Bir harfli birliklar — faqat "SON␠birlik" (bo'shliq shart): "5 m" → "besh metr".
_UNITS1 = {"m": "metr", "g": "gramm", "l": "litr", "t": "tonna"}
# Belgilar → so'z (raqamlardan oldin bajariladi).
_SYMBOLS = {"№": " raqam ", "&": " va "}
# Nuqtali qisqartmalar (manzil/unvon) → to'liq so'z. Registrsiz, nuqta bilan.
_ABBR_DOT = {"ko'ch.": "ko'chasi", "koʻch.": "ko'chasi", "prof.": "professor",
             "dots.": "dotsent", "vil.": "viloyat", "tum.": "tuman",
             "sh.": "shahar", "mkr.": "mikrorayon", "d.": "dona",
             "h.k.": "hokazo", "sh.k.": "shu kabilar", "v.b.": "va boshqalar",
             "mln.": "million", "mlrd.": "milliard", "trln.": "trillion"}

# Ma'lum qisqartmalar → o'zbekcha talaffuz (Yandex "IT" ni "it" deb o'qib qo'yardi).
# Faqat SHU RO'YXATDAGILAR o'zgaradi (UTY/DAS kabi brend nomlariga tegmaydi).
# Ko'p ishlatiladigan qisqartmalar to'liq o'zbekcha atamaga ochiladi (eng tabiiy
# talaffuz — Yandex qisqartmani buzmaydi). Qolganlari harflab o'qiladi.
_ABBR = {"IT": "axborot texnologiyalari", "AI": "sun'iy intellekt",
         "IP": "ay-pi", "GPS": "ji-pi-es", "SMS": "es-em-es", "USB": "yu-es-bi",
         "PDF": "pi-di-ef", "HR": "eych-ar", "VIP": "vi-ay-pi", "SMM": "es-em-em",
         "UZS": "so'm", "AQSh": "Amerika Qo'shma Shtatlari",
         "BMT": "Birlashgan Millatlar Tashkiloti",
         "MDH": "Mustaqil Davlatlar Hamdo'stligi",
         "O'zR": "O'zbekiston Respublikasi"}

# Yandex o'zbek ovozi ba'zi so'zlarni buzib o'qiydi — TTS uchun to'g'ri talaffuzga
# yoziladi (ekranda ASL so'z qoladi). Registrsiz, to'liq so'z sifatida.
_PRON = {"virtual": "virtuual"}
_MONTHS = {1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel", 5: "may", 6: "iyun",
           7: "iyul", 8: "avgust", 9: "sentyabr", 10: "oktyabr", 11: "noyabr", 12: "dekabr"}
# Klass/poyezd kodidagi harf → o'qilishi (kiril va lotin).
_LETTER = {"С": "si", "C": "si", "В": "ve", "B": "ve", "П": "pe", "P": "pe", "Л": "el",
           "Е": "ye", "E": "ye", "У": "u", "U": "u", "К": "ka", "K": "ka", "Д": "de",
           "D": "de", "М": "em", "M": "em", "Г": "ge", "Ф": "ef", "F": "ef", "Н": "en",
           "Т": "te", "T": "te", "А": "a", "A": "a", "Р": "er", "R": "er"}


# Apostrof/okina variantlari → yagona ' (U+0027). SABAB: GPT matni o'/oʻ/o`/o‘/o’
# turli belgilar bilan keladi; TTS ba'zilarini "oʻ" digrafi deb tanimay so'zni
# buzib o'qiydi. Hammasini bitta shaklga keltiramiz (bizning so'z jadvallarimiz ' ishlatadi).
_APOSTROPHES = "`´‘’ʹʻʼʽˈ′"
_APOS_RE = re.compile("[" + _APOSTROPHES + "]")


def _canon_apostrophe(text: str) -> str:
    """Barcha apostrof/okina variantlarini oddiy ' (U+0027) ga keltiradi."""
    return _APOS_RE.sub("'", text)


def _three(n: int) -> str:
    """0..999 → o'zbekcha so'z."""
    out = []
    h, r = divmod(n, 100)
    if h:
        out.append(f"{_ONES[h]} yuz")   # 100 → "bir yuz" (aniqroq talaffuz)
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


# Oy nomlari (ikkala imlo: sentyabr/sentabr, oktyabr/oktabr).
_MONTH_NAMES = ("yanvar|fevral|mart|aprel|may|iyun|iyul|avgust|"
                "sentyabr|sentabr|oktyabr|oktabr|noyabr|dekabr")


def _day_month(m):
    """'1-iyul' → 'birinchi iyul' (kun tartib son)."""
    return f"{_ordinal(num_to_uz(int(m.group(1))))} {m.group(2)}"


def _year(m):
    """'2026-yil(da/dan/gacha/i/ning...)' → tartib son + 'yil' + qo'shimcha.
    '1994-yilda' → 'bir ming to'qqiz yuz to'qson to'rtinchi yilda'."""
    return f"{_ordinal(num_to_uz(int(m.group(1))))} yil{m.group(2)}"


def _time(m):
    h, mi = int(m.group(1)), int(m.group(2))
    if mi == 0:
        return f"soat {num_to_uz(h)}"
    return f"soat {num_to_uz(h)} {num_to_uz(mi)} daqiqa"


def _ord_word(m):
    """'5-uy' → 'beshinchi uy', '2-qavat' → 'ikkinchi qavat' (umumiy tartib son)."""
    return f"{_ordinal(num_to_uz(int(m.group(1))))} {m.group(2)}"


def _range(m):
    """'10-15' → 'o'ndan o'n beshgacha' (ablativ + gacha bevosita qo'shiladi)."""
    a, b = int(m.group(1)), int(m.group(2))
    return f"{num_to_uz(a)}dan {num_to_uz(b)}gacha"


def _decimal(m):
    """'3,5' / '3.5' → 'uch butun besh' (o'zbekcha kasr: X butun Y; nol saqlanadi)."""
    whole, frac = m.group(1), m.group(2)
    fw = " ".join("nol" if d == "0" else _ONES[int(d)] for d in frac)
    return f"{num_to_uz(int(whole))} butun {fw}"


def _num(m):
    s = m.group(0).replace(" ", "").replace(" ", "")
    return num_to_uz(int(s))


def normalize_uz_tts(text: str) -> str:
    """Matndagi raqam/sana/vaqt/valyuta/kasr/belgi/qisqartmalarni o'zbekcha so'zga
    o'giradi. Tartib MUHIM — eng aniq naqshlar oldin (keyingi qoida yeb qo'ymasin)."""
    if not text:
        return text
    # 0) Apostrof/okina variantlarini yagona ' ga (so'z buzilib talaffuz qilinmasin).
    text = _canon_apostrophe(text)
    # 1) Klass/poyezd kodi: raqam + bitta KIRIL harf (1С, 2В, 768Ф) — RAQAMLARDAN OLDIN.
    #    Faqat kiril (haqiqiy vagon kodlari kiril): lotin "3D/4K/5G/1080p" buzilmaydi.
    text = re.sub(r"\b(\d{1,4})([А-Яа-яЁё])\b", _seat, text)
    # 2) Sana: dd.mm.yyyy / dd.mm / yyyy-mm-dd → "kun-oy".
    text = re.sub(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", _date, text)
    text = re.sub(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", _date_iso, text)
    # Bare "dd.mm" — oy 2 RAQAMLI bo'lsagina sana ("10.06"); "4.5" esa kasr (keyin).
    text = re.sub(r"\b(\d{1,2})\.(\d{2})\b(?!\d)", _date, text)
    # 2b) "N-oy" → tartib son + oy ("1-iyul" → "birinchi iyul").
    text = re.sub(rf"\b(\d{{1,2}})-({_MONTH_NAMES})\b", _day_month, text)
    # 2c) "N-yil" → tartib son + yil ("2026-yil" → "... oltinchi yil").
    # "N-yil" + kelishik qo'shimchasi (yil/yilda/yildan/yilgacha/yili/yilning...).
    text = re.sub(r"\b(\d{3,4})-yil(\w*)\b", _year, text)
    # 2d) Umumiy tartib son: "N-so'z" (5-uy, 2-qavat). Harflar KELISHI shart →
    #     "10-15" (raqam-raqam) tegilmaydi, u keyingi qoidada oraliq bo'ladi.
    text = re.sub(r"\b(\d{1,3})-([A-Za-z][A-Za-z']{1,})\b", _ord_word, text)
    # 2e) Oraliq: "N-N" (10-15) → "...dan ...gacha".
    text = re.sub(r"\b(\d{1,4})-(\d{1,4})\b", _range, text)
    # 2f) Manfiy son: "-5" → "minus besh" (oraliq/tartib allaqachon yeyilgan; harf/
    #     raqam/nuqtadan keyingi "-" tegilmaydi, faqat sof manfiy).
    text = re.sub(r"(?<![\w.])-(?=\d)", "minus ", text)
    # 3) Vaqt: HH:MM → "soat ..." (oldindagi ortiqcha "soat" ni yutadi — "soat soat" bo'lmasin).
    text = re.sub(r"\b(?:soat\s+)?([01]?\d|2[0-3]):([0-5]\d)\b", _time, text)
    # 3a) Qolgan "son:son" (hisob 2:1, yaroqsiz vaqt 24:00) → ":" o'rniga bo'shliq
    #     (aks holda ":" TTS'da o'qilmasdan qolardi: "ikki:bir").
    text = re.sub(r"(?<=\d):(?=\d)", " ", text)
    # 3b) Vergul-ajratkichli mingliklar (4,000 / 1,234,567) → vergulni olib tashlaymiz
    #     ("4,000" -> "4000" -> keyin "to'rt ming"). Faqat vergul + AYNAN 3 raqam guruhi
    #     (o'nlik kasr "3,5" tegilmaydi — undan keyin 3 raqam kelmaydi).
    text = re.sub(r"\d{1,3}(?:,\d{3})+", lambda m: m.group(0).replace(",", ""), text)
    # 3b') Bo'shliq-ajratkichli mingliklar (12 500 / 311 000) → yaxlit son. KASRdan
    #      OLDIN bo'lishi shart — aks holda "12 500,50" da kasr "500,50" ni olib, "12"
    #      ajralib qolardi ("o'n ikki ... besh yuz butun ...").
    text = re.sub(r"\d{1,3}(?:[    ]\d{3})+",
                  lambda m: re.sub(r"[    ]", "", m.group(0)), text)
    # 3c) Foiz: "50%" → "50 foiz" (son keyin so'zga aylanadi).
    text = re.sub(r"(?<=\d)\s*%", " foiz", text)
    # 3d) Belgilar: № → "raqam", & → "va".
    for _sym, _w in _SYMBOLS.items():
        text = text.replace(_sym, _w)
    # 3e) Birliklar SONdan keyin → to'liq so'z. Ko'p harfli/belgili (uzun avval, registrsiz),
    #     so'ng bir harfli (m/g/l/t) — FAQAT bo'shliq bilan (tasodifiy so'zga tegmasin).
    _u_pat = "|".join(re.escape(k) for k in sorted(_UNITS, key=len, reverse=True))
    text = re.sub(r"(?<=\d)\s*(" + _u_pat + r")\b",
                  lambda m: " " + _UNITS[m.group(1).lower()], text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=\d)\s+([mglt])\b",
                  lambda m: " " + _UNITS1[m.group(1).lower()], text, flags=re.IGNORECASE)
    # 3f) O'nlik kasr: "3,5" / "3.5" → "uch butun besh" (mingliklar/sana allaqachon yeyilgan).
    #     Old/ket nuqta-raqam bo'lsa TEGILMAYDI — yaroqsiz sana "00.06.2026" da "00.06"
    #     ni kasr deb olmasin (aks holda ".2026" nuqtali qolib buzilardi).
    text = re.sub(r"(?<![\d.])(\d+)[,.](\d+)(?!\.?\d)", _decimal, text)
    # 3g) Nuqtali qisqartmalar (ko'ch.→ko'chasi). Uzun avval; registrsiz.
    for _ab in sorted(_ABBR_DOT, key=len, reverse=True):
        text = re.sub(re.escape(_ab), _ABBR_DOT[_ab], text, flags=re.IGNORECASE)
    # 3d) Ma'lum qisqartmalar → talaffuz (IT→"ay-ti"). Faqat _ABBR ro'yxatidagilar,
    #     to'liq so'z sifatida (registrga sezgir — kichik "it" so'ziga tegmaydi).
    text = re.sub(r"\b(" + "|".join(_ABBR) + r")\b",
                  lambda m: _ABBR[m.group(1)], text)
    # 3e) So'z talaffuzini tuzatish (virtual→virtuual). Registrsiz, to'liq so'z.
    text = re.sub(r"\b(" + "|".join(_PRON) + r")\b",
                  lambda m: _PRON[m.group(0).lower()], text, flags=re.IGNORECASE)
    # 3h) Raqamga yopishgan lotin harfini ajratamiz (5G, 3D, 1080p) — son so'zga
    #     aylanganda "beshG" bo'lib yopishib qolmasin (birliklar allaqachon yeyilgan).
    text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)
    # 4) Narx/son: bo'shliqli guruh (300 560) yoki oddiy son → so'z.
    text = re.sub(r"\d{1,3}(?:[  ]\d{3})+|\d+", _num, text)
    # 5) Belgi almashtirishlardan qolgan ortiqcha bo'shliqni yig'amiz + chetlarni tozalash
    #     (№ → " raqam " kabi bosh/oxir bo'shliq qolmasin).
    text = re.sub(r"  +", " ", text).strip()
    return text
