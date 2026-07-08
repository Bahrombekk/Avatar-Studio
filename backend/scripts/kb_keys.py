"""KB mazmun-kalitlarini chiqaradi (mashinalararo solishtirish uchun).
Har hujjat: chunk-mazmun sha1 + nomi; har FAQ: q+a sha1. Saralangan."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AV_DIR = ROOT / "data" / "avatars"


def h(t):
    return hashlib.sha1(t.strip().encode("utf-8")).hexdigest()[:16]


seen_d, seen_f = {}, set()
for p in sorted(AV_DIR.iterdir()):
    f = p / "knowledge" / "index.json"
    if not f.exists():
        continue
    idx = json.loads(f.read_text(encoding="utf-8"))
    for s in idx.get("sources", []):
        ch = [c for c in idx["chunks"] if c["src_id"] == s["id"]]
        seen_d[h("\n".join(c["text"] for c in ch))] = s.get("name", "?")
    for fq in idx.get("faqs", []):
        seen_f.add(h(fq["q"] + "\n" + fq["a"]))

for k in sorted(seen_d):
    print("DOC", k, seen_d[k])
for k in sorted(seen_f):
    print("FAQ", k)
