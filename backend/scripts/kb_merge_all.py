"""Barcha avatarlarning bilim bazasini BIRLASHTIRADI — har avatar hammasini bilsin.

Har avatar index.json'idan hujjat (doc) va FAQ'larni MAZMUN bo'yicha (sha1) yig'ib,
yagona to'plam yasaydi; keyin har avatarga yetishmayotganlarini QO'SHADI.
Embedding QAYTA HISOBLANMAYDI — mavjud chunk emb'lari ko'chiriladi (OpenAI shart
emas, tez). Yozishdan oldin har index.json zaxiraga olinadi (.bak_<ts>).

Ishga tushirish (repo ildizidan):
  <python> backend/scripts/kb_merge_all.py            # dry-run (faqat ko'rsatadi)
  <python> backend/scripts/kb_merge_all.py --apply    # haqiqatan yozadi
"""
import hashlib
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # backend/
AV_DIR = ROOT / "data" / "avatars"
APPLY = "--apply" in sys.argv

AVATARS = [p.name for p in AV_DIR.iterdir()
           if (p / "knowledge" / "index.json").exists()]


def load(av):
    p = AV_DIR / av / "knowledge" / "index.json"
    return json.loads(p.read_text(encoding="utf-8"))


def raw_text(av, src_id):
    """Hujjatning XOM matni (sources/<id>.txt) — bo'lmasa None (chunk-tiklama
    overlap tufayli matnni buzadi, uni identifikatsiyaga ISHLATMAYMIZ)."""
    f = AV_DIR / av / "knowledge" / "sources" / f"{src_id}.txt"
    return f.read_text(encoding="utf-8") if f.exists() else None


def h(t):
    return hashlib.sha1(t.strip().encode("utf-8")).hexdigest()[:16]


def chunk_key(chunks):
    """Hujjat identifikatsiyasi CHUNK MAZMUNI bo'yicha (barcha avatarlarda chunk'lar
    bir xil; xom .txt yo'qolgan bo'lsa ham to'g'ri taqqoslanadi)."""
    return h("\n".join(c["text"] for c in chunks))


# ── 1) Yig'ish: chunk-mazmun kaliti → {name, text, added, chunks} ──
variants = {}   # chunk_key -> {"name","text"(xom yoki None),"added","chunks":[...]}
faqs = {}       # h(q+a)  -> {"q","a","chunks":[...]}
have = {}       # av -> {"docs": set(key), "faqs": set(key)}
dims = set()
for av in AVATARS:
    idx = load(av)
    have[av] = {"docs": set(), "faqs": set()}
    for s in idx.get("sources", []):
        ch = [c for c in idx["chunks"] if c["src_id"] == s["id"]]
        key = chunk_key(ch)
        have[av]["docs"].add(key)
        for c in ch:
            dims.add(len(c.get("emb") or []))
        t = raw_text(av, s["id"])
        # Xom matni BOR nusxa afzal (audit uchun); bo'lmasa chunk'lidan qolaveradi.
        if key not in variants or (t is not None and variants[key]["text"] is None):
            variants[key] = {"name": s.get("name", "doc.txt"), "text": t,
                             "added": s.get("added", ""), "chunks": ch}
    for fq in idx.get("faqs", []):
        key = h(fq["q"] + "\n" + fq["a"])
        have[av]["faqs"].add(key)
        ch = [c for c in idx["chunks"] if c["src_id"] == fq["id"]]
        if key not in faqs or len(ch) > len(faqs[key]["chunks"]):
            faqs[key] = {"q": fq["q"], "a": fq["a"], "chunks": ch}

# ── 1b) KANONIKLASH: bir xil NOMdagi hujjat versiyalaridan ENG YANGISI qoladi
# (masalan "Afrosiyob..." 1478 va 1580 belgili ikki variant yurardi — eskisi
# hamma joydan olib tashlanadi, chalkash duplikat RAG'ni ifloslamaydi). ──
by_name = {}
for k, d in variants.items():
    by_name.setdefault(d["name"].strip(), []).append(k)
docs = {}        # kanonik to'plam: key -> doc
drop = set()     # olib tashlanadigan variant kalitlari
for name, keys in by_name.items():
    keys.sort(key=lambda k: variants[k]["added"] or "", reverse=True)
    docs[keys[0]] = variants[keys[0]]
    for old in keys[1:]:
        drop.add(old)
        print(f"eski variant tashlanadi: {name!r} "
              f"({len(variants[old]['chunks'])} chunk, added={variants[old]['added'] or '?'}) "
              f"→ qoladi {len(variants[keys[0]]['chunks'])} chunk ({variants[keys[0]]['added'] or '?'})")

print(f"\nAvatarlar: {AVATARS}")
print(f"Yagona KANONIK to'plam: {len(docs)} hujjat, {len(faqs)} FAQ; emb o'lchamlari: {sorted(dims)}")
if len(dims) > 1:
    print("OGOHLANTIRISH: har xil embedding o'lchami — aralashtirish qidiruvni buzadi!")
    print("Bunday holatda --apply O'RNIGA reembed.py bilan qayta indekslang.")
    sys.exit(2)

def doc_text(d):
    """Yozish uchun matn: xom bo'lsa o'sha, bo'lmasa chunk'lardan (faqat audit)."""
    return d["text"] if d["text"] is not None else "\n".join(c["text"] for c in d["chunks"])


# ── 2) Har avatar: eski variantlarni O'CHIRISH + yetishmaganini QO'SHISH
#      (+ yo'qolgan sources/<id>.txt fayllarini TIKLASH) ──
for av in AVATARS:
    idx = load(av)
    kdir = AV_DIR / av / "knowledge"
    del_ids = []
    repair = []   # (src_id, key) — hujjat bor lekin xom .txt yo'qolgan
    for s in idx.get("sources", []):
        ch = [c for c in idx["chunks"] if c["src_id"] == s["id"]]
        key = chunk_key(ch)
        if key in drop:
            del_ids.append(s["id"])
        elif key in docs and raw_text(av, s["id"]) is None:
            repair.append((s["id"], key))
    miss_d = [k for k in docs if k not in have[av]["docs"]]
    miss_f = [k for k in faqs if k not in have[av]["faqs"]]
    print(f"\n{av}: -{len(del_ids)} eski variant, +{len(miss_d)} hujjat, "
          f"+{len(miss_f)} FAQ, {len(repair)} .txt tiklanadi")
    for k in miss_d:
        print(f"   + doc: {docs[k]['name']} ({len(docs[k]['chunks'])} chunk)")
    if miss_f:
        print(f"   + {len(miss_f)} FAQ")
    if not APPLY or (not del_ids and not miss_d and not miss_f and not repair):
        continue
    shutil.copy2(kdir / "index.json",
                 kdir / f"index.json.bak_{time.strftime('%Y%m%d_%H%M%S')}")
    # o'chirish
    idx["sources"] = [s for s in idx["sources"] if s["id"] not in del_ids]
    idx["chunks"] = [c for c in idx["chunks"] if c["src_id"] not in del_ids]
    for sid in del_ids:
        f = kdir / "sources" / f"{sid}.txt"
        if f.exists():
            f.unlink()
    # yo'qolgan xom .txt tiklash
    (kdir / "sources").mkdir(exist_ok=True)
    for sid, key in repair:
        (kdir / "sources" / f"{sid}.txt").write_text(doc_text(docs[key]), encoding="utf-8")
    # qo'shish
    for k in miss_d:
        d = docs[k]
        sid = "src_" + uuid.uuid4().hex[:8]
        t = doc_text(d)
        idx["sources"].append({
            "id": sid, "type": "file", "name": d["name"],
            "added": d["added"] or time.strftime("%Y-%m-%dT%H:%M:%S"),
            "chars": len(t), "n_chunks": len(d["chunks"]),
        })
        for c in d["chunks"]:
            idx["chunks"].append({"id": "c_" + uuid.uuid4().hex[:10], "src_id": sid,
                                  "kind": c.get("kind", "doc"), "text": c["text"],
                                  "emb": c["emb"]})
        (kdir / "sources" / f"{sid}.txt").write_text(t, encoding="utf-8")
    for k in miss_f:
        fq = faqs[k]
        fid = "faq_" + uuid.uuid4().hex[:8]
        idx["faqs"].append({"id": fid, "q": fq["q"], "a": fq["a"],
                            "added": time.strftime("%Y-%m-%dT%H:%M:%S")})
        for c in fq["chunks"]:
            idx["chunks"].append({"id": "c_" + uuid.uuid4().hex[:10], "src_id": fid,
                                  "kind": c.get("kind", "faq"), "text": c["text"],
                                  "emb": c["emb"]})
    tmp = kdir / "index.json.tmp"
    tmp.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    tmp.replace(kdir / "index.json")
    print(f"   YOZILDI: endi {len(idx['sources'])} hujjat, {len(idx['faqs'])} FAQ, "
          f"{len(idx['chunks'])} chunk")

print("\n" + ("TAYYOR (yozildi)." if APPLY else "DRY-RUN — yozish uchun --apply qo'shing."))
