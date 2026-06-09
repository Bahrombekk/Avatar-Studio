"""Javob/video keshi — savol → tayyor video.

Kesh har bir (avatar, ovoz) juftligi uchun ALOHIDA:
    data/avatars/<aid>/voices/<voice>/cache.json    → indeks
    data/avatars/<aid>/voices/<voice>/videos/<eid>.mp4 → kesh videolari

Bu aniqlikni oshiradi: bir xil savol har avatar+ovozda o'z javob/videosini oladi,
"qayta ayt" o'sha avatar+ovozning oxirgi yozuvini qaytaradi, va video FAQAT BIR
MARTA saqlanadi (tmp dan ko'chiriladi — nusxa emas, move).

Bosqichlar:
  1. Exact match (hozir)
  2. Embedding semantic search (kelajak)
  3. GPT router (kelajak)
"""
import hashlib
import json
import logging
import re
import shutil
import threading
import time
from typing import Optional, Dict, Any, List

from app.core.paths import DEFAULT_SCOPE, voice_cache_file, voice_videos_dir

log = logging.getLogger(__name__)


def _normalize(query: str) -> str:
    """Lowercase, trim, punktuatsiya olib tashlash, bo'shliqlar bittaga."""
    q = query.strip().lower()
    q = q.replace("ʻ", "'").replace("ʼ", "'").replace("`", "'")
    q = re.sub(r"[!?.,;:\"()\[\]{}<>—–-]+", "", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


# "Qayta ayt" tipidagi so'rovlar — oxirgi javobni qaytarish kerak
_REPEAT_PATTERNS = [
    "eshitmadim", "yaxshi eshitmadim", "tushunmadim", "tushinmadim",
    "qayta", "qaytaring", "qaytarib", "qaytaribyubor",
    "yana ayt", "yana bir bor", "qayta ayt", "boshqatdan",
    "takror", "takrorlang", "yana", "yana ber",
    "ovoz yo'q", "ovozi yo'q", "nima deding", "nima dedingiz",
]


def is_repeat_request(query: str) -> bool:
    """Foydalanuvchi 'qayta ayting' tipidagi so'rov yuborganmi?"""
    q = _normalize(query)
    if not q:
        return False
    if len(q) <= 30:
        for pattern in _REPEAT_PATTERNS:
            if pattern in q:
                return True
    return False


class ResponseCache:
    """Thread-safe (avatar, ovoz)'ga bog'langan kesh + diskdagi indeks."""

    def __init__(self, scope: str, voice: str):
        self.scope = scope                       # avatar id yoki DEFAULT_SCOPE
        self.voice = voice
        self.index_path = voice_cache_file(scope, voice)
        self.videos_dir = voice_videos_dir(scope, voice)
        self._lock = threading.RLock()
        self.entries: List[Dict[str, Any]] = []
        self._last_entry: Optional[Dict[str, Any]] = None
        self._load()

    def _video_url(self, entry_id: str) -> str:
        return f"/videos/{self.scope}/{self.voice}/{entry_id}.mp4"

    def _load(self):
        if not self.index_path.exists():
            return
        try:
            with self.index_path.open(encoding="utf-8") as f:
                data = json.load(f)
            self.entries = data.get("entries", [])
            if self.entries:
                self._last_entry = self.entries[-1]
            log.info("[cache] %s/%s: %d ta entry yuklandi", self.scope, self.voice, len(self.entries))
        except Exception as e:
            log.warning("[cache] %s/%s yuklab bo'lmadi: %s", self.scope, self.voice, e)

    def _save(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(
                {"version": 1, "entries": self.entries, "stats": self.stats()},
                f, indent=2, ensure_ascii=False,
            )
        tmp.replace(self.index_path)

    def exact_match(self, query: str) -> Optional[Dict[str, Any]]:
        norm = _normalize(query)
        with self._lock:
            for entry in self.entries:
                if not entry.get("reusable", True):
                    continue
                if entry.get("query_normalized") == norm:
                    return entry
        return None

    def add(self, query: str, response: str, video_src_path: str,
            intent_tags: Optional[List[str]] = None, topic: Optional[str] = None,
            contextual: bool = False, reusable: bool = True, confidence: float = 1.0,
            embedding: Optional[List[float]] = None,
            gen_time: Optional[float] = None) -> Optional[Dict[str, Any]]:
        entry_id = hashlib.md5(f"{query}_{time.time()}".encode()).hexdigest()[:10]
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        cached_video = self.videos_dir / f"{entry_id}.mp4"
        try:
            # Video FAQAT BIR MARTA saqlanadi — tmp dan ko'chiramiz (nusxa emas).
            shutil.move(str(video_src_path), str(cached_video))
        except Exception as e:
            log.error("[cache] video move fail: %s", e)
            return None

        entry = {
            "id": entry_id,
            "query": query,
            "query_normalized": _normalize(query),
            "response": response,
            "video": self._video_url(entry_id),
            "intent_tags": intent_tags or [],
            "topic": topic or "",
            "contextual": contextual,
            "reusable": reusable,
            "confidence": confidence,
            "meta": {
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "hit_count": 0,
                "last_used": None,
                "gen_time": gen_time,
            },
        }
        if embedding is not None:
            entry["embedding"] = embedding

        with self._lock:
            self.entries.append(entry)
            self._last_entry = entry
            self._save()

        log.info("[cache] add %s/%s id=%s q='%s'", self.scope, self.voice, entry_id, query[:40])
        return entry

    def get_last_entry(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._last_entry

    def record_hit(self, entry: Dict[str, Any]):
        with self._lock:
            entry["meta"]["hit_count"] = entry["meta"].get("hit_count", 0) + 1
            entry["meta"]["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self._save()

    def stats(self) -> Dict[str, Any]:
        total = len(self.entries)
        hits = sum(e.get("meta", {}).get("hit_count", 0) for e in self.entries)
        return {
            "total_entries": total,
            "total_hits": hits,
            "hit_rate": round(hits / (hits + total), 3) if (hits + total) > 0 else 0,
        }

    def list_entries(self, include_embedding: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            if include_embedding:
                return list(self.entries)
            return [{k: v for k, v in e.items() if k != "embedding"} for e in self.entries]

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            for i, e in enumerate(self.entries):
                if e["id"] == entry_id:
                    try:
                        (self.videos_dir / f"{entry_id}.mp4").unlink()
                    except Exception:
                        pass
                    self.entries.pop(i)
                    self._save()
                    return True
        return False

    def clear(self) -> int:
        with self._lock:
            n = len(self.entries)
            for e in self.entries:
                try:
                    (self.videos_dir / f"{e['id']}.mp4").unlink()
                except Exception:
                    pass
            self.entries.clear()
            self._last_entry = None
            self._save()
        return n


# ── Scope'ga bog'langan kesh instansiyalari (lazy singleton) ──
_instances: Dict[tuple, ResponseCache] = {}
_instances_lock = threading.Lock()


def get_cache(avatar_id: Optional[str] = None, voice: str = "madina") -> ResponseCache:
    """(avatar, ovoz) juftligi uchun keshni qaytaradi (lazy yaratadi)."""
    scope = avatar_id or DEFAULT_SCOPE
    key = (scope, voice)
    inst = _instances.get(key)
    if inst is None:
        with _instances_lock:
            inst = _instances.get(key)
            if inst is None:
                inst = ResponseCache(scope, voice)
                _instances[key] = inst
    return inst


def _discover_scopes() -> List[tuple]:
    """Diskda mavjud barcha (scope, voice) juftliklarini topadi."""
    from app.core.paths import AVATARS_DIR
    found = []
    if not AVATARS_DIR.exists():
        return found
    for scope_dir in AVATARS_DIR.iterdir():
        voices_dir = scope_dir / "voices"
        if not voices_dir.is_dir():
            continue
        for vdir in voices_dir.iterdir():
            if (vdir / "cache.json").exists():
                found.append((scope_dir.name, vdir.name))
    return found


def aggregate_stats() -> Dict[str, Any]:
    """Barcha (avatar, ovoz) keshlari bo'yicha umumiy statistika."""
    seen = set(_instances.keys()) | set(_discover_scopes())
    total_entries = total_hits = 0
    for scope, voice in seen:
        c = get_cache(None if scope == DEFAULT_SCOPE else scope, voice)
        s = c.stats()
        total_entries += s["total_entries"]
        total_hits += s["total_hits"]
    denom = total_hits + total_entries
    return {
        "total_entries": total_entries,
        "total_hits": total_hits,
        "hit_rate": round(total_hits / denom, 3) if denom > 0 else 0,
        "scopes": len(seen),
    }


def clear_all() -> int:
    """Barcha keshlarni tozalaydi, o'chirilgan yozuvlar sonini qaytaradi."""
    seen = set(_instances.keys()) | set(_discover_scopes())
    n = 0
    for scope, voice in seen:
        c = get_cache(None if scope == DEFAULT_SCOPE else scope, voice)
        n += c.clear()
    return n
