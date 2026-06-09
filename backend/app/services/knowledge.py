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
import re
import threading
import time
import uuid

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

# Retrieval xotira keshi: avatar_id → (mtime, matrix(np), chunks(list)).
_CACHE: dict = {}


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
    embs = _embed(pieces)
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
    embs = _embed([embed_text])
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
def _matrix(avatar_id: str):
    """(mtime-keshlangan) normallashtirilgan embedding matritsasi + chunklar."""
    p = avatar_knowledge_index(avatar_id)
    if not p.exists():
        return None, []
    mtime = p.stat().st_mtime
    cached = _CACHE.get(avatar_id)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    idx = _load(avatar_id)
    chunks = [c for c in idx.get("chunks", []) if c.get("emb")]
    if not chunks:
        _CACHE[avatar_id] = (mtime, None, [])
        return None, []
    mat = np.array([c["emb"] for c in chunks], dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat = mat / norms
    _CACHE[avatar_id] = (mtime, mat, chunks)
    return mat, chunks


def retrieve(avatar_id: str, query: str, k: int = 4, min_score: float = 0.30) -> list:
    """So'rovga eng yaqin bilim bo'laklari (cosine top-k). Xatoda/bo'shda []."""
    if not avatar_id or not (query or "").strip():
        return []
    try:
        mat, chunks = _matrix(avatar_id)
        if mat is None:
            return []
        qv = _embed([query])
        if not qv:
            return []
        q = np.array(qv[0], dtype=np.float32)
        qn = np.linalg.norm(q)
        if qn == 0:
            return []
        scores = mat @ (q / qn)
        order = np.argsort(-scores)[:k]
        hits = []
        for i in order:
            sc = float(scores[i])
            if sc < min_score:
                continue
            c = chunks[i]
            hits.append({"text": c.get("answer") or c["text"], "kind": c.get("kind", "doc"),
                         "src_id": c.get("src_id"), "score": round(sc, 3)})
        return hits
    except Exception as e:  # noqa: BLE001
        log.warning("[knowledge] retrieve xato: %s", e)
        return []


def build_context_block(hits: list) -> str:
    """Topilgan bo'laklardan system-prompt qo'shimchasini quradi ('' agar bo'sh)."""
    if not hits:
        return ""
    lines = ["MA'LUMOT BAZASI (faqat shu ma'lumotga tayan; mos kelmasa "
             "\"aniq ma'lumotim yo'q\" deb ayt — o'ylab topma):"]
    for h in hits:
        tag = "FAQ" if h.get("kind") == "faq" else "hujjat"
        lines.append(f"- [{tag}] {h['text']}")
    return "\n".join(lines)
