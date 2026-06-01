"""Eski tekis JSON saqlashdan per-avatar / per-voice tuzilmaga migratsiya.

Eski (flat):
    data/avatars.json
    data/events.jsonl
    checkpoints/cache_index.json
    static/videos/cache/<id>.mp4

Yangi (per-avatar/voice — paths.py ga mos):
    data/registry.json
    data/avatars/<id>/avatar.json
    data/avatars/<id>/stats.json
    data/avatars/<id>/events.jsonl
    data/avatars/<id>/voices/<voice>/cache.json
    data/avatars/<id>/voices/<voice>/videos/<eid>.mp4

Ishlatish (musetalk muhitida, backend/ ichidan):
    python scripts/migrate_storage.py            # quruq yurish (dry-run)
    python scripts/migrate_storage.py --apply     # haqiqiy yozish

Eski cache yozuvi videosi topilmasa — o'sha yozuv TASHLAB yuboriladi (chunki
videosi yo'q kesh 404 beradi). Eski fayllar O'CHIRILMAYDI (.bak ga qoldiriladi).
"""
import json
import re
import shutil
import sys
from pathlib import Path

# backend/ ni sys.path ga qo'shamiz (app import qilish uchun).
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.paths import (  # noqa: E402
    DATA_DIR,
    CHECKPOINTS_DIR,
    STATIC_DIR,
    DEFAULT_SCOPE,
    REGISTRY_FILE,
    avatar_config_file,
    avatar_stats_file,
    avatar_events_file,
    voice_cache_file,
    voice_videos_dir,
)
from app.services.avatar_store import _STAT_KEYS  # noqa: E402
from app.services.cache import _normalize  # noqa: E402
from app.services.tts import VOICES, DEFAULT_VOICE  # noqa: E402

# Eski fayllar
OLD_AVATARS = DATA_DIR / "avatars.json"
OLD_EVENTS = DATA_DIR / "events.jsonl"
OLD_CACHE_INDEX = CHECKPOINTS_DIR / "cache_index.json"
OLD_VIDEO_DIR = STATIC_DIR / "videos" / "cache"

_KNOWN_VOICES = set(VOICES.keys())
_PREFIX_RE = re.compile(r"^\[([^\]]*)\]\s*(.*)$", re.DOTALL)


def _atomic_write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _parse_old_key(query: str):
    """Eski kesh kalitidan (scope, voice, toza_savol) ni ajratadi.

    Ko'rinishlar:
        "[scope|voice] savol"  → (scope, voice, savol)
        "[voice] savol"        → (_default, voice, savol)   # voice tanilsa
        "[xxx] savol"          → (_default, DEFAULT, savol)  # tanilmasa
        "savol"                → (_default, DEFAULT, savol)
    """
    m = _PREFIX_RE.match(query.strip())
    if not m:
        return DEFAULT_SCOPE, DEFAULT_VOICE, query.strip()
    inside, rest = m.group(1).strip(), m.group(2).strip()
    if "|" in inside:
        scope, voice = (p.strip() for p in inside.split("|", 1))
        scope = DEFAULT_SCOPE if scope in ("", "def", "default") else scope
        voice = voice if voice in _KNOWN_VOICES else DEFAULT_VOICE
        return scope, voice, rest
    if inside in _KNOWN_VOICES:
        return DEFAULT_SCOPE, inside, rest
    return DEFAULT_SCOPE, DEFAULT_VOICE, rest


def migrate_avatars(apply: bool):
    if not OLD_AVATARS.exists():
        print(f"  [avatars] {OLD_AVATARS.name} yo'q — o'tkazib yuborildi")
        return []
    avatars = json.loads(OLD_AVATARS.read_text(encoding="utf-8"))
    ids = []
    for av in avatars:
        aid = av["id"]
        ids.append(aid)
        stats = {k: av.get(k, 0) for k in _STAT_KEYS}
        config = {k: v for k, v in av.items() if k not in _STAT_KEYS}
        print(f"  [avatar] {aid}: config + stats")
        if apply:
            _atomic_write(avatar_config_file(aid), config)
            _atomic_write(avatar_stats_file(aid), stats)
    print(f"  [registry] {len(ids)} avatar: {ids}")
    if apply:
        _atomic_write(REGISTRY_FILE, {"version": 1, "avatars": ids})
    return ids


def migrate_events(apply: bool):
    if not OLD_EVENTS.exists():
        print(f"  [events] {OLD_EVENTS.name} yo'q — o'tkazib yuborildi")
        return
    by_avatar = {}
    for line in OLD_EVENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        aid = ev.get("avatar_id") or "madina_lp"
        by_avatar.setdefault(aid, []).append(line)
    for aid, lines in by_avatar.items():
        print(f"  [events] {aid}: {len(lines)} hodisa")
        if apply:
            path = avatar_events_file(aid)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def migrate_cache(apply: bool):
    if not OLD_CACHE_INDEX.exists():
        print(f"  [cache] {OLD_CACHE_INDEX.name} yo'q — o'tkazib yuborildi")
        return
    data = json.loads(OLD_CACHE_INDEX.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    # (scope, voice) → yangi yozuvlar ro'yxati
    buckets = {}
    kept = dropped = 0
    for e in entries:
        old_q = e.get("query", "")
        scope, voice, clean_q = _parse_old_key(old_q)
        old_id = e.get("id")
        old_video = OLD_VIDEO_DIR / f"{old_id}.mp4"
        if not old_video.exists():
            dropped += 1
            continue  # videosiz yozuv keraksiz (404 berardi)
        new_e = dict(e)
        new_e["query"] = clean_q
        new_e["query_normalized"] = _normalize(clean_q)
        new_e["video"] = f"/videos/{scope}/{voice}/{old_id}.mp4"
        buckets.setdefault((scope, voice), []).append((new_e, old_video))
        kept += 1
    print(f"  [cache] {kept} yozuv ko'chiriladi, {dropped} tashlandi (videosiz)")
    for (scope, voice), items in buckets.items():
        print(f"    → {scope}/{voice}: {len(items)} yozuv")
        if not apply:
            continue
        vdir = voice_videos_dir(scope, voice)
        vdir.mkdir(parents=True, exist_ok=True)
        new_entries = []
        for new_e, old_video in items:
            shutil.copy2(old_video, vdir / f"{new_e['id']}.mp4")
            new_entries.append(new_e)
        _atomic_write(voice_cache_file(scope, voice),
                      {"version": 1, "entries": new_entries})


def backup_old(apply: bool):
    """Eski fayllarni .bak ga ko'chiradi (o'chirmaydi)."""
    for old in (OLD_AVATARS, OLD_EVENTS, OLD_CACHE_INDEX):
        if old.exists():
            bak = old.with_suffix(old.suffix + ".bak")
            print(f"  [backup] {old.name} → {bak.name}")
            if apply:
                shutil.move(str(old), str(bak))


def main():
    apply = "--apply" in sys.argv
    mode = "QO'LLASH (--apply)" if apply else "QURUQ YURISH (dry-run)"
    print(f"=== Migratsiya: {mode} ===\n")
    print("1) Avatarlar (registry + config + stats):")
    migrate_avatars(apply)
    print("\n2) Hodisalar (per-avatar events.jsonl):")
    migrate_events(apply)
    print("\n3) Kesh (per avatar/voice + videolar):")
    migrate_cache(apply)
    print("\n4) Eski fayllarni zaxiralash:")
    backup_old(apply)
    if apply:
        print("\n✓ Migratsiya tugadi.")
    else:
        print("\n(Bu quruq yurish edi. Haqiqiy yozish: python scripts/migrate_storage.py --apply)")


if __name__ == "__main__":
    main()
