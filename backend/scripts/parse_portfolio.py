#!/usr/bin/env python3
"""DASUTY loyihalar PDF'ini → projects.json ga ajratuvchi (bir martalik, offline).

PDF tuzilmasi: HAR BIR SAHIFA = bitta loyiha (2-20 sahifalar; 1 va oxirgi muqova).
Shuning uchun loyiha chegarasi = sahifa chegarasi — chunklash YO'Q, loyihalar
ARALASHMAYDI (foydalanuvchining asosiy talabi). Har sahifa bitta atomik yozuv.

Foydalanish:
    pdftotext "Barcha loyihalar yangi.pdf" /tmp/portfolio_raw.txt
    python scripts/parse_portfolio.py /tmp/portfolio_raw.txt data/portfolio/projects.json

Natija (projects.json): [{id, title, aliases[], summary, full_text}, ...]
"""
import json
import re
import sys
from pathlib import Path

# Loyiha id'lari + qo'shimcha lotin/inglizcha aliaslar (lotin tilida yozilgan
# savol kirill sarlavhaga mos kelishi uchun). title PDF'dan avtomatik olinadi;
# bu jadval faqat ALIAS qo'shadi (qidiruv kengroq bo'lsin).
# Aliaslar: har loyiha uchun O'ZIGA XOS kalit so'zlar + STT noto'g'ri eshitishi
# mumkin bo'lgan FONETIK variantlar (uz lotin nutqi turlicha yoziladi).
# Bittagina o'ziga xos so'z (xodim, nakl, depo, ...) mosligi yetarli — fuzzy
# moslik bilan birga "eh xodim", "xotin", "hodim" kabilar ham E-Xodim'ga tushadi.
_ALIASES = {
    1:  ["e-nakl", "enakl", "nakl", "naqil", "yuk tashish", "э-накл"],
    2:  ["e-xodim", "exodim", "xodim", "hodim", "xotin", "xodimlar", "kadrlar", "hr",
         "face control", "э-ходим"],
    3:  ["smart depo", "smartdepo", "depo", "lokomotiv ta'mir", "lokomotiv tamir"],
    4:  ["railway observer", "observer", "obzerver", "obxodchi", "yo'l nazorati"],
    5:  ["marshrut", "marshurt", "mashrut", "marshrut varaqasi", "mashinist"],
    6:  ["tarozi", "tarozisi", "tarozisi tizimi", "vagon tortish", "aqlli tarozi"],
    7:  ["kesishma", "kesishmasi", "shlagbaum", "pereezd", "aqlli kesishma"],
    8:  ["telegraf", "telegramma", "tezkor telegraf"],
    9:  ["kmo", "ka me o", "oylik ko'rik", "oylik nazorat", "oylik ko'rigi"],
    10: ["metrologiya", "metrolog", "qiyoslov", "kalibrovka"],
    11: ["mehnat muhofazasi", "mehnat", "muhofaza", "mehnat xavfsizligi"],
    12: ["railway smart build", "smart build", "qurilish", "kapital qurilish",
         "rasmbuilt", "smart bild"],
    13: ["digital energy", "digital enerji", "energiya", "energetika", "asue", "enerji"],
    14: ["kpi", "ka pe i", "kape"],
    15: ["railmap", "reylmap", "rail map", "xarita", "raqamli boshqaruv"],
    16: ["yoshlar portali", "yoshlar", "yoshlar portal", "innovatsiya",
         "ratsionalizator"],
    17: ["railwayai", "railway ai", "chat railwayai", "chat ai", "reylvey ai",
         "ai chatbot", "intellektual chat"],
    18: ["normativ", "huquqiy hujjat", "normativ hujjatlar", "huquqiy hujjatlar",
         "hujjatlar bazasi", "arxiv"],
    19: ["telefon", "telefonlar", "telefon bazasi", "telefon raqamlari",
         "yagona telefon", "raqamlar bazasi"],
}


# ── Kirill → lotin o'zbek transliteratsiyasi (deterministik, modelга tashlanmaydi) ──
# Uzun birikmalar avval (ts, ch, sh, ...), keyin bitta harflar. UTY o'zbek lotin.
_CYR2LAT = [
    ("ё", "yo"), ("ж", "j"), ("ч", "ch"), ("ш", "sh"), ("щ", "sh"),
    ("ю", "yu"), ("я", "ya"), ("ц", "ts"), ("ў", "o'"), ("қ", "q"),
    ("ғ", "g'"), ("ҳ", "h"), ("ъ", "'"),
    ("а", "a"), ("б", "b"), ("в", "v"), ("г", "g"), ("д", "d"),
    ("е", "e"), ("з", "z"), ("и", "i"), ("й", "y"), ("к", "k"),
    ("л", "l"), ("м", "m"), ("н", "n"), ("о", "o"), ("п", "p"),
    ("р", "r"), ("с", "s"), ("т", "t"), ("у", "u"), ("ф", "f"),
    ("х", "x"), ("ь", ""), ("э", "e"),
]


def cyr2lat(text: str) -> str:
    """Kirill o'zbekni lotinga o'giradi (bosh harf holatini saqlaydi)."""
    out = []
    for ch in text:
        low = ch.lower()
        rep = None
        for c, l in _CYR2LAT:
            if low == c:
                rep = l
                break
        if rep is None:
            out.append(ch)
        elif ch.isupper():
            out.append(rep.capitalize() if len(rep) > 1 else rep.upper())
        else:
            out.append(rep)
    return "".join(out)


def _slug(title: str, idx: int) -> str:
    """Sarlavhadan o'qiladigan id (lotin, alfa-raqamli)."""
    t = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return t[:30] or f"loyiha_{idx}"


def parse(raw_text: str) -> list:
    # Form-feed (\f) — pdftotext sahifa ajratuvchisi.
    pages = raw_text.split("\f")
    # Muqova (1) va oxirgi "rahmat" sahifasini tashlaymiz: faqat haqiqiy loyihalar.
    projects = []
    idx = 0
    for page in pages:
        text = page.strip()
        if not text:
            continue
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        title = lines[0]
        # Muqova/yopilish sahifalarini o'tkazib yuboramiz (loyiha emas).
        if ("ЎЗБЕКИСТОН" in title and "ТЕМИР" in title) or "Этиборингиз" in text:
            continue
        idx += 1
        # Lotinga o'giramiz: model FAQAT lotin ko'radi → javob ham lotin bo'ladi
        # (transliteratsiyani modelga tashlamaymiz — deterministik, ishonchli).
        title_lat = cyr2lat(title).strip(" “”\"")
        summary = cyr2lat(" ".join(lines[1:3]))[:220]
        full_text = cyr2lat("\n".join(lines))
        projects.append({
            "id": _slug(title_lat, idx),
            "n": idx,
            "title": title_lat,            # lotin sarlavha (ko'rsatish + ro'yxat)
            "title_cyr": title.strip(" “”\""),  # asl kirill (zaxira)
            "aliases": _ALIASES.get(idx, []),
            "summary": summary,
            "full_text": full_text,
        })
    return projects


def main():
    if len(sys.argv) < 3:
        print("Foydalanish: python parse_portfolio.py <raw.txt> <out.json>", file=sys.stderr)
        sys.exit(2)
    raw = Path(sys.argv[1]).read_text(encoding="utf-8")
    projects = parse(raw)
    out = Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(projects)} ta loyiha yozildi → {out}")
    for p in projects:
        print(f"  [{p['n']:2}] {p['id']:30} ← {p['title'][:50]}")


if __name__ == "__main__":
    main()
