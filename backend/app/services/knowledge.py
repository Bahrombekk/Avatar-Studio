"""Per-avatar bilim bazasi (RAG) — hujjat/FAQ asosida GPT javobini asoslash.

Admin avatar uchun hujjat (txt/md) yoki FAQ (savol-javob) qo'shadi. Matn bo'laklarga
(chunk) bo'linadi, OpenAI embedding'lari hisoblanadi va `knowledge/index.json` ga
inline saqlanadi (canned.py namunasi kabi). Suhbat paytida foydalanuvchi savoli
embed qilinib, eng yaqin bo'laklar topiladi (cosine) va system prompt'ga qo'shiladi —
GPT faqat shu ma'lumotga tayanadi (to'qib chiqarmaydi).

Saqlash:
  data/avatars/<id>/knowledge/index.json   → {sources, faqs, chunks[{id,src_id,kind,text,emb}]}
  data/avatars/<id>/knowledge/sources/<src_id>.txt  → xom matn (audit / qayta-chunk)

Degradatsiya: kalit yo'q / korpus bo'sh / API xato → retrieve() [] qaytaradi va
chaqiruvchi avvalgidek (asoslashsiz) ishlaydi.
"""
import json
import logging
import math
import re
import threading
import time
import uuid
from collections import Counter

import numpy as np

from app.core.paths import (
    avatar_knowledge_dir,
    avatar_knowledge_index,
    avatar_knowledge_sources_dir,
)

log = logging.getLogger(__name__)
_lock = threading.RLock()

# Chunking parametrlari (belgi bo'yicha — tilga bog'liq emas).
_CHUNK_TARGET = 500
_CHUNK_MAX = 800
_CHUNK_OVERLAP = 80

# Retrieval xotira keshi: avatar_id → (mtime, matrix(np), chunks(list), lex(dict)).
_CACHE: dict = {}

# ── O'zbek matn normalizatsiyasi ──
# Turli apostrof variantlari (oʻ, o', o`, oʼ ...) bir xilga keltiriladi — aks holda
# embedding VA kalit-so'z mosligi jimgina buziladi (bir xil so'z boshqacha ko'rinadi).
_APOS = {"ʻ": "'", "ʼ": "'", "‘": "'", "’": "'",
         "´": "'", "`": "'"}


def norm_uz(s: str) -> str:
    """Apostroflarni birlashtiradi + ortiqcha bo'shliqni yig'adi (registr saqlanadi —
    embedding registrga chidamli). Hujjat, FAQ va so'rov BIR XIL normallashtiriladi."""
    s = s or ""
    for a, b in _APOS.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s: str) -> list:
    """Kalit-so'z tokenlari (latin+kiril+raqam, so'z ichidagi apostrof saqlanadi)."""
    s = norm_uz(s).lower()
    return re.findall(r"[a-z0-9'Ѐ-ӿ]+", s)


def _bm25(query_tokens, tf_list, dl_list, df, avgdl, k1: float = 1.5, b: float = 0.75):
    """BM25 lexical ballari (har chunk uchun). df=term→hujjatlar soni, avgdl=o'rtacha uzunlik."""
    n = len(tf_list)
    scores = np.zeros(n, dtype=np.float32)
    if n == 0 or avgdl == 0:
        return scores
    for t in set(query_tokens):
        n_t = df.get(t, 0)
        if n_t == 0:
            continue
        idf = math.log(1.0 + (n - n_t + 0.5) / (n_t + 0.5))
        for i in range(n):
            f = tf_list[i].get(t, 0)
            if not f:
                continue
            dl = dl_list[i] or 1
            scores[i] += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
    return scores


# ── Index I/O ──
def _empty_index() -> dict:
    return {"version": 1, "sources": [], "faqs": [], "chunks": []}


def _load(avatar_id: str) -> dict:
    p = avatar_knowledge_index(avatar_id)
    if not p.exists():
        return _empty_index()
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for k in ("sources", "faqs", "chunks"):
            data.setdefault(k, [])
        return data
    except Exception:
        return _empty_index()


def _save(avatar_id: str, idx: dict) -> None:
    avatar_knowledge_dir(avatar_id).mkdir(parents=True, exist_ok=True)
    p = avatar_knowledge_index(avatar_id)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    tmp.replace(p)
    _CACHE.pop(avatar_id, None)            # kesh eskirdi


# ── Chunking ──
def chunk_text(text: str) -> list:
    """Paragraf-asosli, ~_CHUNK_TARGET belgili bo'laklar (~_CHUNK_OVERLAP overlap)."""
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for para in paras:
        # Juda uzun paragraf — gaplarga bo'lamiz.
        pieces = re.split(r"(?<=[.!?…])\s+", para) if len(para) > _CHUNK_MAX else [para]
        for piece in pieces:
            if not cur:
                cur = piece
            elif len(cur) + 1 + len(piece) <= _CHUNK_TARGET:
                cur += " " + piece
            else:
                chunks.append(cur.strip())
                tail = cur[-_CHUNK_OVERLAP:] if len(cur) > _CHUNK_OVERLAP else ""
                cur = (tail + " " + piece).strip()
            while len(cur) > _CHUNK_MAX:        # xavfsizlik kafolati
                chunks.append(cur[:_CHUNK_MAX].strip())
                cur = cur[_CHUNK_MAX - _CHUNK_OVERLAP:].strip()
    if cur.strip():
        chunks.append(cur.strip())
    return [c for c in chunks if c]


def _embed(texts: list) -> list:
    """gpt.embed_texts ustida yupqa o'ram (lazy import — test'da monkeypatch oson)."""
    if not texts:
        return []
    from app.services.gpt import embed_texts
    return embed_texts(texts)


# ── CRUD ──
def add_file_source(avatar_id: str, filename: str, text: str) -> dict:
    """Hujjat matnini chunk + embed qilib bilim bazasiga qo'shadi."""
    pieces = chunk_text(text)
    if not pieces:
        raise ValueError("Hujjat bo'sh yoki o'qib bo'lmadi")
    # Normallashtirilgan matnni embed qilamiz (so'rov ham normallashtiriladi → mos);
    # ko'rinadigan chunk["text"] esa ASL matn (prompt'da o'qiladi).
    embs = _embed([norm_uz(p) for p in pieces])
    if len(embs) != len(pieces):
        raise RuntimeError("Embedding olinmadi (OpenAI kaliti/limit?)")
    src_id = "src_" + uuid.uuid4().hex[:8]
    with _lock:
        idx = _load(avatar_id)
        idx["sources"].append({
            "id": src_id, "type": "file", "name": filename,
            "added": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "chars": len(text), "n_chunks": len(pieces),
        })
        for piece, emb in zip(pieces, embs):
            idx["chunks"].append({
                "id": "c_" + uuid.uuid4().hex[:10], "src_id": src_id,
                "kind": "doc", "text": piece, "emb": emb,
            })
        _save(avatar_id, idx)
        # Xom matnni ham saqlaymiz (audit / qayta-chunk).
        try:
            sdir = avatar_knowledge_sources_dir(avatar_id)
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / f"{src_id}.txt").write_text(text, encoding="utf-8")
        except Exception as e:
            log.warning("[knowledge] xom matn saqlanmadi: %s", e)
    return {"id": src_id, "n_chunks": len(pieces)}


def add_faq(avatar_id: str, question: str, answer: str) -> dict:
    """FAQ (savol-javob) juftligini qo'shadi (chunk sifatida embed qilinadi)."""
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        raise ValueError("Savol va javob bo'sh bo'lmasligi kerak")
    embed_text = f"Savol: {question}\nJavob: {answer}"
    embs = _embed([norm_uz(embed_text)])
    if not embs:
        raise RuntimeError("Embedding olinmadi (OpenAI kaliti/limit?)")
    faq_id = "faq_" + uuid.uuid4().hex[:8]
    with _lock:
        idx = _load(avatar_id)
        idx["faqs"].append({
            "id": faq_id, "q": question, "a": answer,
            "added": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        idx["chunks"].append({
            "id": "c_" + uuid.uuid4().hex[:10], "src_id": faq_id,
            "kind": "faq", "text": embed_text, "answer": answer, "emb": embs[0],
        })
        _save(avatar_id, idx)
    return {"id": faq_id}


def list_knowledge(avatar_id: str) -> dict:
    idx = _load(avatar_id)
    return {"sources": idx.get("sources", []), "faqs": idx.get("faqs", [])}


def delete_source(avatar_id: str, src_id: str) -> bool:
    with _lock:
        idx = _load(avatar_id)
        n0 = len(idx["sources"])
        idx["sources"] = [s for s in idx["sources"] if s.get("id") != src_id]
        idx["chunks"] = [c for c in idx["chunks"] if c.get("src_id") != src_id]
        if len(idx["sources"]) == n0:
            return False
        _save(avatar_id, idx)
    try:
        (avatar_knowledge_sources_dir(avatar_id) / f"{src_id}.txt").unlink()
    except OSError:
        pass
    return True


def delete_faq(avatar_id: str, faq_id: str) -> bool:
    with _lock:
        idx = _load(avatar_id)
        n0 = len(idx["faqs"])
        idx["faqs"] = [f for f in idx["faqs"] if f.get("id") != faq_id]
        idx["chunks"] = [c for c in idx["chunks"] if c.get("src_id") != faq_id]
        if len(idx["faqs"]) == n0:
            return False
        _save(avatar_id, idx)
    return True


def get_source(avatar_id: str, src_id: str) -> dict | None:
    """Manba metasi + XOM matni (ko'rish/tahrirlash uchun). Yo'q bo'lsa None.
    Xom matn (sources/<id>.txt) yo'q bo'lsa — chunk'lardan taxminan tiklanadi
    (overlap tufayli takror bo'lishi mumkin, lekin ko'rish uchun yetarli)."""
    idx = _load(avatar_id)
    meta = next((s for s in idx.get("sources", []) if s.get("id") == src_id), None)
    if meta is None:
        return None
    text = ""
    p = avatar_knowledge_sources_dir(avatar_id) / f"{src_id}.txt"
    if p.exists():
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            text = ""
    if not text:
        text = "\n\n".join(
            c.get("text", "") for c in idx.get("chunks", []) if c.get("src_id") == src_id
        )
    return {**meta, "text": text}


def update_source(avatar_id: str, src_id: str, text: str, name: str | None = None) -> dict:
    """Manba matnini yangilaydi — qayta chunk + embed (src_id o'zgarmaydi).
    Manba topilmasa KeyError."""
    pieces = chunk_text(text)
    if not pieces:
        raise ValueError("Hujjat bo'sh yoki o'qib bo'lmadi")
    embs = _embed([norm_uz(p) for p in pieces])
    if len(embs) != len(pieces):
        raise RuntimeError("Embedding olinmadi (OpenAI kaliti/limit?)")
    with _lock:
        idx = _load(avatar_id)
        meta = next((s for s in idx["sources"] if s.get("id") == src_id), None)
        if meta is None:
            raise KeyError(src_id)
        idx["chunks"] = [c for c in idx["chunks"] if c.get("src_id") != src_id]
        for piece, emb in zip(pieces, embs):
            idx["chunks"].append({
                "id": "c_" + uuid.uuid4().hex[:10], "src_id": src_id,
                "kind": "doc", "text": piece, "emb": emb,
            })
        if name:
            meta["name"] = name
        meta["chars"] = len(text)
        meta["n_chunks"] = len(pieces)
        meta["added"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _save(avatar_id, idx)
        try:
            sdir = avatar_knowledge_sources_dir(avatar_id)
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / f"{src_id}.txt").write_text(text, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log.warning("[knowledge] xom matn saqlanmadi: %s", e)
    return {"id": src_id, "n_chunks": len(pieces)}


def update_faq(avatar_id: str, faq_id: str, question: str, answer: str) -> bool:
    """FAQ savol/javobini yangilaydi + tegishli chunk'ni qayta embed qiladi.
    FAQ topilmasa False."""
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        raise ValueError("Savol va javob bo'sh bo'lmasligi kerak")
    embed_text = f"Savol: {question}\nJavob: {answer}"
    embs = _embed([norm_uz(embed_text)])
    if not embs:
        raise RuntimeError("Embedding olinmadi (OpenAI kaliti/limit?)")
    with _lock:
        idx = _load(avatar_id)
        faq = next((f for f in idx["faqs"] if f.get("id") == faq_id), None)
        if faq is None:
            return False
        faq["q"] = question
        faq["a"] = answer
        ch = next((c for c in idx["chunks"] if c.get("src_id") == faq_id), None)
        if ch is not None:
            ch["text"] = embed_text
            ch["answer"] = answer
            ch["emb"] = embs[0]
        else:
            idx["chunks"].append({
                "id": "c_" + uuid.uuid4().hex[:10], "src_id": faq_id,
                "kind": "faq", "text": embed_text, "answer": answer, "emb": embs[0],
            })
        _save(avatar_id, idx)
    return True


# ── Retrieval ──
def _build_lex(chunks: list) -> dict:
    """BM25 uchun lexical struktura: har chunk token-chastotasi, uzunligi, df, avgdl."""
    tf_list, dl_list, df = [], [], {}
    for c in chunks:
        toks = _tokens(c.get("text", ""))
        tf = Counter(toks)
        tf_list.append(tf)
        dl_list.append(len(toks))
        for t in tf:
            df[t] = df.get(t, 0) + 1
    avgdl = (sum(dl_list) / len(dl_list)) if dl_list else 0.0
    return {"tf": tf_list, "dl": dl_list, "df": df, "avgdl": avgdl}


def _matrix(avatar_id: str):
    """(mtime-keshlangan) normallashgan embedding matritsasi + chunklar + lexical (BM25)."""
    p = avatar_knowledge_index(avatar_id)
    if not p.exists():
        return None, [], None
    mtime = p.stat().st_mtime
    cached = _CACHE.get(avatar_id)
    if cached and cached[0] == mtime:
        return cached[1], cached[2], cached[3]
    idx = _load(avatar_id)
    chunks = [c for c in idx.get("chunks", []) if c.get("emb")]
    if not chunks:
        _CACHE[avatar_id] = (mtime, None, [], None)
        return None, [], None
    mat = np.array([c["emb"] for c in chunks], dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat = mat / norms
    lex = _build_lex(chunks)
    _CACHE[avatar_id] = (mtime, mat, chunks, lex)
    return mat, chunks, lex


def retrieve(avatar_id: str, query: str, k: int = 4, min_score: float = 0.30) -> list:
    """GIBRID retrieval: dense (embedding cosine) + lexical (BM25), RRF bilan birlashtirilgan.
    Dense — ma'no o'xshashligi; BM25 — aniq atamalar (ism, raqam, bekat nomi, kod) —
    O'zbekda ikkalasi birga recall'ni sezilarli oshiradi. Xatoda/bo'shda []."""
    if not avatar_id or not (query or "").strip():
        return []
    try:
        mat, chunks, lex = _matrix(avatar_id)
        if mat is None:
            return []
        n = len(chunks)
        # ── Dense (embedding) ──
        dense = np.zeros(n, dtype=np.float32)
        qv = _embed([norm_uz(query)])
        if qv:
            q = np.array(qv[0], dtype=np.float32)
            qn = np.linalg.norm(q)
            if qn:
                dense = mat @ (q / qn)
        # ── Lexical (BM25) ──
        bm = _bm25(_tokens(query), lex["tf"], lex["dl"], lex["df"], lex["avgdl"]) if lex else np.zeros(n)
        if not qv and not bm.any():
            return []
        # ── RRF birlashtirish (reciprocal rank fusion) ──
        C = 60
        d_rank = {int(i): r for r, i in enumerate(np.argsort(-dense))}
        b_rank = {int(i): r for r, i in enumerate(np.argsort(-bm))}
        fused = []
        for i in range(n):
            s = 1.0 / (C + d_rank[i])            # dense har doim hisobga olinadi
            if bm[i] > 0:                          # lexical faqat so'z mos kelsa
                s += 1.0 / (C + b_rank[i])
            fused.append((i, s))
        fused.sort(key=lambda x: -x[1])
        hits = []
        for i, _ in fused:
            # Relevantlik darvozasi: yo ma'no yaqin (dense), yo so'z mos (bm25).
            if not (dense[i] >= min_score or bm[i] > 0):
                continue
            c = chunks[i]
            hits.append({"text": c.get("answer") or c["text"], "kind": c.get("kind", "doc"),
                         "src_id": c.get("src_id"), "score": round(float(dense[i]), 3),
                         "bm25": round(float(bm[i]), 2)})
            if len(hits) >= k:
                break
        return hits
    except Exception as e:  # noqa: BLE001
        log.warning("[knowledge] retrieve xato: %s", e)
        return []


def build_context_block(hits: list) -> str:
    """Topilgan bo'laklardan system-prompt qo'shimchasini quradi ('' agar bo'sh)."""
    if not hits:
        return ""
    lines = ["MA'LUMOT BAZASI (javobni shu ma'lumotga asosla, ma'lumot to'qima; "
             "agar to'liq mos kelmasa — \"bilmayman\" deb to'xtama, balki yumshoq "
             "tan olib aniqlashtiruvchi savol ber yoki yordam taklif qil, suhbatni "
             "davom ettir):"]
    for h in hits:
        tag = "FAQ" if h.get("kind") == "faq" else "hujjat"
        lines.append(f"- [{tag}] {h['text']}")
    return "\n".join(lines)


# ── Meta / qobiliyat savollari ("nimani bilasan", "qanday yordam berasan") ──
# Semantik retrieval bu savollarga ishlamaydi (savol so'zlari KB mazmuniga o'xshamaydi)
# — o'rniga KB "katalogi" (mavzu nomlari + namuna FAQ) beriladi, GPT undan javob quradi.
_CAP_PATTERNS = re.compile(
    r"nima(lar)?ni?\s+bilas"                     # nimani/nimalarni/nima bilasan (bilan EMAS)
    r"|qanday\s+yordam|qanaqa\s+yordam"          # qanday yordam bera olasan
    r"|yordam\s+bera\s*ol"                        # ... yordam bera olasan(mi)
    r"|nima(lar)?\s+(qila|qilib)\s*ol"           # nima qila olasan
    r"|nima\s+ish\s+qil"                          # nima ish qilasan
    r"|qanday\s+savol|qanaqa\s+savol"            # qanday savol berishim mumkin
    r"|nima(lar)?ga\s+javob\s+ber"               # nimalarga javob berasan
    r"|sen\s+kimsan|sen\s+kim\b|o'zing\s+kim|kimsan"
    r"|vazifang|imkoniyating|imkoniyatlaring"
    r"|nima(lar)?\s+haqida\s+(gaplash|so'zlash|ma'lumot|yordam|so'ra)"
    r"|qaysi\s+mavzu|qanaqa\s+mavzu|qaysi\s+soha"
    r"|what\s+(can|do)\s+you|how\s+can\s+you\s+help"
    r"|что\s+ты\s+(зна|уме)|чем\s+.*помо",
    re.IGNORECASE)


def is_capability_query(text: str) -> bool:
    """Foydalanuvchi umumiy 'nimani bilasan / qanday yordam bera olasan' deb so'radimi?"""
    t = norm_uz(text or "").lower()
    return bool(t and _CAP_PATTERNS.search(t))


def overview(avatar_id: str, max_faqs: int = 18) -> dict:
    """KB mavzular katalogi: manba nomlari (mavzular) + namuna FAQ savollari (teng
    oraliqda — kenglik uchun). Embedding/API talab qilmaydi (faqat index o'qiydi)."""
    idx = _load(avatar_id)
    topics, seen = [], set()
    for s in idx.get("sources", []):
        name = re.sub(r"\.(txt|md|pdf|docx?)$", "", (s.get("name") or "").strip(),
                      flags=re.IGNORECASE).strip()
        # Sof fayl-nomga o'xshaganlarni (bo'shliqsiz, kichik harf) tashlab ketamiz.
        if not name or name.lower() in seen:
            continue
        if " " not in name and name.islower() and len(name) <= 16:
            continue
        seen.add(name.lower())
        topics.append(name)
    qs = [(f.get("q") or "").strip() for f in idx.get("faqs", []) if (f.get("q") or "").strip()]
    if len(qs) > max_faqs:
        step = len(qs) / max_faqs
        qs = [qs[int(i * step)] for i in range(max_faqs)]
    return {"topics": topics, "faqs": qs,
            "n_sources": len(idx.get("sources", [])), "n_faqs": len(idx.get("faqs", []))}


def build_overview_block(ov: dict) -> str:
    """Meta-savol uchun system-prompt qo'shimchasi (KB qamrovi). '' agar bo'sh."""
    if not ov or (not ov.get("topics") and not ov.get("faqs")):
        return ""
    lines = ["BILIM BAZASI QAMROVI — foydalanuvchi sening NIMANI bilishing yoki QANDAY "
             "yordam bera olishingni so'radi. Quyida bilim bazangdagi HAQIQIY mavzular. "
             "Shulardan kelib chiqib TABIIY, QISQA javob ber: 4-7 ta asosiy yo'nalishni "
             "suhbat ohangida sanab, yordam taklif qil. Ro'yxatni quruq o'qib berma va "
             "o'zingdan mavzu to'qima — faqat shu ro'yxatga asoslan."]
    if ov.get("topics"):
        lines.append("Mavzular: " + "; ".join(ov["topics"]))
    if ov.get("faqs"):
        lines.append("Namuna savollar (shu turdagilarga javob bera olasan): "
                     + " | ".join(ov["faqs"]))
    return "\n".join(lines)
