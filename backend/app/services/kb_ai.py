"""Bilim bazasi ustida GPT amallari — (1) hujjatdan avto-FAQ taklifi (admin ko'rib
tasdiqlaydi), (2) manba+FAQ'larni RU/EN ga AYNAN tarjima qilib embed qilish (ko'p tilli
retrieval). Ikkalasi ham knowledge.py ichki tuzilmasidan foydalanadi.

Tarjima uzoq (100+ element × 2 til) — in-process fon thread'ida progress bilan bajariladi
(`start_translation` / `translation_status`). Avatarlar bir xil KB'ga tayanadi, lekin bu
amallar tanlangan avatar KB'siga yoziladi (kerak bo'lsa kb_merge_all.py bilan tarqatiladi).
"""
import json as _json
import logging
import re
import threading
import time
import uuid

from app.services import knowledge as kb

log = logging.getLogger(__name__)

# Til kodi → (to'liq nom, ko'rsatma tili) tarjima prompti uchun.
_LANGS = {
    "ru": "rus (Russian)",
    "en": "ingliz (English)",
    "uz": "o'zbek (Uzbek)",
}


def _gpt():
    """OpenAI klienti (lazy — test'da import torch-siz qoladi)."""
    from app.services.gpt import client
    return client


def _chat_json(system: str, user: str, max_tokens: int = 1500, temperature: float = 0.2) -> dict:
    """GPT'dan JSON javob (```-fence yoki ortiqcha matnga chidamli). Xato → {}."""
    from app.services.gpt import _parse_json_block
    resp = _gpt().chat.completions.create(
        model="gpt-4o-mini", max_tokens=max_tokens, temperature=temperature,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
    )
    raw = resp.choices[0].message.content or ""
    try:
        return _parse_json_block(raw)
    except Exception:  # noqa: BLE001
        return {}


def _chat_text(system: str, user: str, max_tokens: int = 2000, temperature: float = 0.1) -> str:
    resp = _gpt().chat.completions.create(
        model="gpt-4o-mini", max_tokens=max_tokens, temperature=temperature,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
    )
    return (resp.choices[0].message.content or "").strip()


# ══════════════════════════════════════════════════════════════════════════
# (1) HUJJATDAN AVTO-FAQ TAKLIFI
# ══════════════════════════════════════════════════════════════════════════
_FAQ_SYS = (
    "Sen bilim bazasi uchun savol-javob (FAQ) tuzuvchisan. Foydalanuvchi bir HUJJAT "
    "matnini beradi. Shu matnga TAYANIB, odam so'rashi mumkin bo'lgan tabiiy savollar va "
    "ularga aniq javoblar tuz.\n"
    "QAT'IY QOIDALAR:\n"
    "- Faqat matnDA BOR faktlardan foydalanaman — hech narsa TO'QIMA, taxmin qo'shma.\n"
    "- Savol qisqa va tabiiy (foydalanuvchi tilida). Javob 1-3 jumla, matnga sodiq.\n"
    "- Raqam/sana/nom/narxlarni matndagidek aniq ko'chir.\n"
    "- Matn tilida yoz (odatda o'zbekcha). Takroriy/bir xil savol chiqarma.\n"
    "- Faqat JSON qaytar: {\"faqs\":[{\"q\":\"...\",\"a\":\"...\"}, ...]}"
)


def suggest_faqs(avatar_id: str, src_id: str, n: int = 8) -> list:
    """Manba matnidan n tagacha FAQ nomzodi (SAQLANMAYDI — admin ko'rib tanlaydi).
    Mavjud FAQ savollariga o'xshaganlari (normallashtirilgan) chiqarib tashlanadi."""
    src = kb.get_source(avatar_id, src_id)
    if not src or not (src.get("text") or "").strip():
        return []
    text = src["text"].strip()
    if len(text) > 12000:                     # tokenlarni cheklaymiz (bir chaqiruv)
        text = text[:12000]
    n = max(1, min(int(n or 8), 15))
    user = f"Kerakli FAQ soni: {n} ta.\n\nHUJJAT:\n{text}"
    data = _chat_json(_FAQ_SYS, user, max_tokens=2200)
    faqs = data.get("faqs") if isinstance(data.get("faqs"), list) else []
    # Mavjud savollar (dedup uchun).
    idx = kb._load(avatar_id)
    have = {kb.norm_uz(f.get("q", "")).lower() for f in idx.get("faqs", [])}
    out, seen = [], set()
    for f in faqs:
        q = (f.get("q") or "").strip()
        a = (f.get("a") or "").strip()
        if not q or not a:
            continue
        key = kb.norm_uz(q).lower()
        if key in have or key in seen:
            continue
        seen.add(key)
        out.append({"q": q, "a": a})
    return out[:n]


def add_faqs_bulk(avatar_id: str, pairs: list) -> dict:
    """Bir nechta FAQ'ni birato'la qo'shadi (embeddinglar bitta partiyada). pairs=[{q,a}]."""
    clean = [(p.get("q", "").strip(), p.get("a", "").strip())
             for p in (pairs or []) if p.get("q", "").strip() and p.get("a", "").strip()]
    if not clean:
        return {"added": 0}
    embed_texts = [kb.norm_uz(f"Savol: {q}\nJavob: {a}") for q, a in clean]
    embs = kb._embed(embed_texts)
    if len(embs) != len(clean):
        raise RuntimeError("Embedding olinmadi (OpenAI kaliti/limit?)")
    with kb._lock:
        idx = kb._load(avatar_id)
        for (q, a), emb in zip(clean, embs):
            faq_id = "faq_" + uuid.uuid4().hex[:8]
            idx["faqs"].append({"id": faq_id, "q": q, "a": a,
                                "added": time.strftime("%Y-%m-%dT%H:%M:%S")})
            idx["chunks"].append({"id": "c_" + uuid.uuid4().hex[:10], "src_id": faq_id,
                                  "kind": "faq", "text": f"Savol: {q}\nJavob: {a}",
                                  "answer": a, "emb": emb, "lang": "uz"})
        kb._save(avatar_id, idx)
    return {"added": len(clean)}


# ══════════════════════════════════════════════════════════════════════════
# (2) RU/EN TARJIMA (AYNAN, embed bilan) — ko'p tilli retrieval
# ══════════════════════════════════════════════════════════════════════════
def _translate_faithful(text: str, lang: str) -> str:
    """Matnni `lang` ga AYNAN tarjima qiladi (fakt/raqam/nom o'zgarmaydi)."""
    text = (text or "").strip()
    if not text:
        return ""
    sys = (
        f"You are a professional translator. Translate the user's text into natural, fluent "
        f"{_LANGS[lang]}. Translate ALL words — including domain terms (e.g. 'chipta' -> "
        "ticket/билет, 'bekat' -> station/станция). Do NOT add, remove, or change any FACT. "
        "Keep UNCHANGED only: numbers, dates, prices, and proper names (people, places, "
        "organizations, product/brand names). Keep the same meaning and tone; preserve "
        "paragraph breaks. Output ONLY the translation — no notes, no quotes, no explanations."
    )
    return _chat_text(sys, text, max_tokens=min(4000, len(text) + 800))


def _translate_long(text: str, lang: str, limit: int = 3500) -> str:
    """Uzun matnni paragraf-guruhlarga bo'lib tarjima qiladi (token cheklovi uchun)."""
    text = (text or "").strip()
    if len(text) <= limit:
        return _translate_faithful(text, lang)
    paras = re.split(r"\n\s*\n", text)
    groups, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 2 > limit:
            groups.append(cur)
            cur = p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        groups.append(cur)
    return "\n\n".join(_translate_faithful(g, lang) for g in groups)


def _translate_faq(q: str, a: str, lang: str) -> tuple:
    """FAQ savol+javobini `lang` ga aynan tarjima (bitta chaqiruv, JSON)."""
    sys = (
        f"Translate the FAQ into natural, fluent {_LANGS[lang]}. Translate ALL words "
        "including domain terms (chipta->ticket/билет, bekat->station/станция). Keep "
        "UNCHANGED only numbers, dates, prices and proper names. Do not change any fact. "
        "Output ONLY JSON: {\"q\":\"<translated question>\",\"a\":\"<translated answer>\"}"
    )
    data = _chat_json(sys, _json.dumps({"q": q, "a": a}, ensure_ascii=False), max_tokens=1200)
    return (data.get("q") or "").strip(), (data.get("a") or "").strip()


# ── Fon-job holati (progress polling uchun) ──
_TJ: dict = {}                      # avatar_id -> holat dict
_TJ_LOCK = threading.Lock()


def translation_status(avatar_id: str) -> dict:
    with _TJ_LOCK:
        return dict(_TJ.get(avatar_id) or {"state": "idle"})


def _set_tj(avatar_id: str, **kw):
    with _TJ_LOCK:
        st = _TJ.get(avatar_id) or {}
        st.update(kw)
        _TJ[avatar_id] = st


def start_translation(avatar_id: str, langs: list) -> bool:
    """RU/EN tarjima + embed'ni fon thread'ida boshlaydi. Allaqachon ishlayotgan bo'lsa False."""
    langs = [l for l in (langs or []) if l in ("ru", "en")]
    if not langs:
        langs = ["ru", "en"]
    with _TJ_LOCK:
        cur = _TJ.get(avatar_id)
        if cur and cur.get("state") == "running":
            return False
        idx = kb._load(avatar_id)
        total = (len(idx.get("sources", [])) + len(idx.get("faqs", []))) * len(langs)
        _TJ[avatar_id] = {"state": "running", "done": 0, "total": total,
                          "langs": langs, "stage": "boshlanmoqda", "error": ""}

    def worker():
        try:
            _run_translation(avatar_id, langs)
            _set_tj(avatar_id, state="done", stage="tugadi")
        except Exception as e:  # noqa: BLE001
            log.warning("[kb_ai] tarjima xato: %s", e)
            _set_tj(avatar_id, state="error", error=str(e))

    threading.Thread(target=worker, daemon=True, name=f"kb-tr-{avatar_id}").start()
    return True


def _run_translation(avatar_id: str, langs: list) -> None:
    """Har manba matnini + har FAQ'ni RU/EN ga tarjima → chunk → embed → lang-belgili
    chunk qo'shadi. IDEMPOTENT: avval eski tarjima chunklari (lang!=uz) o'chiriladi."""
    idx = kb._load(avatar_id)
    sources = list(idx.get("sources", []))
    faqs = list(idx.get("faqs", []))
    done = 0

    for lang in langs:
        # Manbalar.
        for s in sources:
            src_id = s.get("id")
            _set_tj(avatar_id, stage=f"{lang}: {s.get('name','manba')[:30]}")
            full = kb.get_source(avatar_id, src_id)
            body = (full or {}).get("text", "").strip() if full else ""
            new_chunks = []
            if body:
                tr = _translate_long(body, lang)
                pieces = kb.chunk_text(tr)
                embs = kb._embed([kb.norm_uz(p) for p in pieces]) if pieces else []
                if pieces and len(embs) == len(pieces):
                    for p, e in zip(pieces, embs):
                        new_chunks.append({"id": "c_" + uuid.uuid4().hex[:10],
                                           "src_id": src_id, "kind": "doc",
                                           "text": p, "emb": e, "lang": lang})
            with kb._lock:
                cur = kb._load(avatar_id)
                # shu manba + shu til eski tarjima chunklarini o'chiramiz (idempotent).
                cur["chunks"] = [c for c in cur["chunks"]
                                 if not (c.get("src_id") == src_id and c.get("lang") == lang)]
                cur["chunks"].extend(new_chunks)
                kb._save(avatar_id, cur)
            done += 1
            _set_tj(avatar_id, done=done)

        # FAQ'lar.
        for f in faqs:
            fid = f.get("id")
            _set_tj(avatar_id, stage=f"{lang}: FAQ")
            tq, ta = _translate_faq(f.get("q", ""), f.get("a", ""), lang)
            new_chunks = []
            if tq and ta:
                emb = kb._embed([kb.norm_uz(f"Savol: {tq}\nJavob: {ta}")])
                if emb:
                    new_chunks.append({"id": "c_" + uuid.uuid4().hex[:10], "src_id": fid,
                                       "kind": "faq", "text": f"Savol: {tq}\nJavob: {ta}",
                                       "answer": ta, "emb": emb[0], "lang": lang})
            with kb._lock:
                cur = kb._load(avatar_id)
                cur["chunks"] = [c for c in cur["chunks"]
                                 if not (c.get("src_id") == fid and c.get("lang") == lang)]
                cur["chunks"].extend(new_chunks)
                kb._save(avatar_id, cur)
            done += 1
            _set_tj(avatar_id, done=done)
