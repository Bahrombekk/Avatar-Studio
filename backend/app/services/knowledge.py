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
