"""Avatar do'koni (CRUD) + analitika — per-avatar fayl tuzilmasi.

Saqlash tuzilmasi (paths.py ga mos):
    data/registry.json                 → {"version":1,"avatars":[id, ...]} (tartib)
    data/avatars/<id>/avatar.json      → to'liq konfiguratsiya
    data/avatars/<id>/stats.json       → {sessions, avgLatency, cacheRate, csat}
    data/avatars/<id>/events.jsonl     → shu avatar suhbat loglari

Konfiguratsiya (avatar.json) STATistikadan (stats.json) ajratilgan — shunda
suhbat statistikasi yangilanishi konfiguratsiya bilan to'qnashmaydi (race yo'q).

Eslatma: talking-head VIDEO faqat `madina_lp` artefakti uchun mavjud.
Boshqa avatarlar shu yuzni ulashadi, lekin OVOZ + PERSONALITY har avatarga xos.
"""
import json
import threading
from datetime import datetime, timezone, timedelta

from app.core.paths import (
    REGISTRY_FILE,
    avatar_dir,
    avatar_config_file,
    avatar_stats_file,
    avatar_events_file,
)

_lock = threading.RLock()

# stats.json ga ketadigan maydonlar (qolgan hammasi avatar.json — konfiguratsiya).
_STAT_KEYS = ("sessions", "avgLatency", "cacheRate", "csat")

# ── Seed: flagman avatarlar (config + boshlang'ich stats) ──
_SEED = [
    {
        "id": "madina_lp",
        "name": "Madina",
        "role": "Virtual yordamchi",
        "brand": "O‘zbekiston Temir Yo‘llari",
        "brandShort": "UTY",
        "status": "live",
        "accent": "#B98944",
        "portrait": {"from": "#1C3A5E", "to": "#0F2540", "initials": "M"},
        "voice": "madina",
        "language": "uz",
        "extraMargin": 16,
        "fps": 25,
        "blinkRate": 4,
        "headMotion": 0.45,
        "persona": "",
        "respLen": "short",
        "temperature": 0.4,
        "speechRate": 0,
        "hasPhoto": True,
        "real": True,
        "suggestions": ["Chipta narxi qancha?", "Toshkent–Samarqand poyezdi", "Bagaj qoidalari"],
        "sessions": 0, "avgLatency": 0, "cacheRate": 0, "csat": 4.7,
        "updated": "Hozir",
    },
    {
        "id": "sardor_bank",
        "name": "Sardor",
        "role": "Bank konsultanti",
        "brand": "Milliy Bank",
        "brandShort": "NBU",
        "status": "draft",
        "accent": "#1F8A5B",
        "portrait": {"from": "#16624A", "to": "#0C3A2C", "initials": "S"},
        "voice": "sardor",
        "language": "uz",
        "extraMargin": 12,
        "fps": 25,
        "blinkRate": 5,
        "headMotion": 0.30,
        "persona": "Siz Milliy Bank konsultantisiz. Rasmiy va ishonchli ohangda, kartalar, "
                   "kreditlar va omonatlar bo‘yicha qisqa javob bering.",
        "respLen": "short",
        "temperature": 0.4,
        "speechRate": 0,
        "hasPhoto": False,
        "real": False,
        "suggestions": ["Karta ochish", "Kredit shartlari", "Valyuta kursi"],
        "sessions": 0, "avgLatency": 0, "cacheRate": 0, "csat": 0,
        "updated": "Hozir",
    },
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _split(avatar: dict):
    """Bitta avatar dict'ini (config, stats) juftligiga ajratadi."""
    stats = {k: avatar.get(k, 0) for k in _STAT_KEYS}
    config = {k: v for k, v in avatar.items() if k not in _STAT_KEYS}
    return config, stats


def _atomic_write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ── Registry ──
def _read_registry():
    if not REGISTRY_FILE.exists():
        return None
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        return list(data.get("avatars", []))
    except Exception:
        return None


def _write_registry(ids):
    _atomic_write(REGISTRY_FILE, {"version": 1, "avatars": list(ids)})


def _ensure_seed():
    """Registry yo'q bo'lsa, flagman avatarlarni yozadi."""
    if _read_registry() is not None:
        return
    ids = []
    for av in _SEED:
        _save_avatar(av)
        ids.append(av["id"])
    _write_registry(ids)


def _save_avatar(avatar: dict):
    """Bitta avatar'ni config + stats fayllariga yozadi (registry'ga tegmaydi)."""
    config, stats = _split(avatar)
    aid = config["id"]
    _atomic_write(avatar_config_file(aid), config)
    _atomic_write(avatar_stats_file(aid), stats)


def _load_avatar(avatar_id):
    """config + stats ni o'qib, bitta birlashgan dict qaytaradi (yo'q bo'lsa None)."""
    cfg_path = avatar_config_file(avatar_id)
    if not cfg_path.exists():
        return None
    try:
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    stats = {k: 0 for k in _STAT_KEYS}
    sp = avatar_stats_file(avatar_id)
    if sp.exists():
        try:
            stats.update(json.loads(sp.read_text(encoding="utf-8")))
        except Exception:
            pass
    return {**config, **stats}


# ── CRUD ──
def list_avatars():
    with _lock:
        _ensure_seed()
        ids = _read_registry() or []
        out = []
        for aid in ids:
            av = _load_avatar(aid)
            if av:
                out.append(av)
        return out


def get_avatar(avatar_id):
    with _lock:
        _ensure_seed()
        return _load_avatar(avatar_id)


def _gen_id(name, existing_ids):
    """Nomdan o'qiladigan, to'qnashuvsiz id yasaydi.

    'av_' + nomning alfa-raqamli qismi (10 belgigacha). Agar shu id band bo'lsa,
    '-2', '-3' ... qo'shib bo'sh variant topiladi (registry'ga qarab).
    """
    slug = "".join(c for c in (name or "").lower() if c.isalnum())[:10] or "avatar"
    base = f"av_{slug}"
    taken = set(existing_ids)
    if base not in taken:
        return base
    i = 2
    while f"{base}-{i}" in taken:
        i += 1
    return f"{base}-{i}"


def create_avatar(data):
    with _lock:
        _ensure_seed()
        ids = _read_registry() or []
        new = dict(data)
        new["id"] = _gen_id(data.get("name", "avatar"), ids)
        new["real"] = False           # yangi avatar — preprocessing kerak (video yo'q)
        new["updated"] = "Hozir"
        for k in _STAT_KEYS:
            new.setdefault(k, 0)
        _save_avatar(new)
        ids.insert(0, new["id"])
        _write_registry(ids)
        return _load_avatar(new["id"])


def update_avatar(avatar_id, data):
    with _lock:
        _ensure_seed()
        existing = _load_avatar(avatar_id)
        if existing is None:
            return None
        merged = {**existing, **data, "id": avatar_id, "updated": "Hozir"}
        merged["real"] = existing.get("real", False)
        # Statistikani so'rovdan emas, mavjud qiymatdan saqlaymiz.
        for k in _STAT_KEYS:
            merged[k] = existing.get(k, 0)
        _save_avatar(merged)
        return _load_avatar(avatar_id)


def set_photo(avatar_id, has_photo: bool):
    """Avatar config'ida hasPhoto bayrog'ini o'rnatadi (rasm yuklangach).

    Faqat config'ga tegadi; stats va boshqa maydonlarga ta'sir qilmaydi.
    Avatar topilmasa None qaytaradi.
    """
    with _lock:
        existing = _load_avatar(avatar_id)
        if existing is None:
            return None
        merged = {**existing, "hasPhoto": bool(has_photo), "updated": "Hozir"}
        _save_avatar(merged)
        return _load_avatar(avatar_id)


def set_ready(avatar_id, ready: bool = True):
    """Avatar 'tayyor' holatini o'rnatadi (MuseTalk artefakt yasalgach).

    ready=True → real=True, hasArtifact=True, status="live". Avatar endi o'z
    yuzi bilan lip-sync qila oladi. Avatar topilmasa None qaytaradi.
    """
    with _lock:
        existing = _load_avatar(avatar_id)
        if existing is None:
            return None
        if ready:
            merged = {**existing, "real": True, "hasArtifact": True,
                      "status": "live", "updated": "Hozir"}
        else:
            merged = {**existing, "real": False, "hasArtifact": False, "updated": "Hozir"}
        _save_avatar(merged)
        return _load_avatar(avatar_id)


def set_build(avatar_id, state: str, stage: str = None, error: str = None):
    """Avatar config'ida 'build' holatini yangilaydi (idle/MuseTalk generatsiya bosqichi).

    state: "idle" | "processing" | "done" | "error"
    stage: qaysi bosqich ("idle_gen" | "musetalk" | None)
    Frontend shu maydonni polling qilib jarayonni kuzatadi. Avatar yo'q → None.
    """
    with _lock:
        existing = _load_avatar(avatar_id)
        if existing is None:
            return None
        build = {"state": state, "stage": stage, "error": error, "updated": _now_iso()}
        merged = {**existing, "build": build}
        _save_avatar(merged)
        return _load_avatar(avatar_id)


def delete_avatar(avatar_id):
    with _lock:
        _ensure_seed()
        ids = _read_registry() or []
        if avatar_id not in ids:
            return False
        ids = [i for i in ids if i != avatar_id]
        _write_registry(ids)
        # Avatar papkasini butunlay o'chiramiz (config, stats, events, voices/).
        import shutil
        shutil.rmtree(avatar_dir(avatar_id), ignore_errors=True)
        return True


def _bump_stats(avatar_id, total, cached):
    """Avatar jonli statistikasini yangilash (sessiya, o'rtacha latency, cache %)."""
    sp = avatar_stats_file(avatar_id)
    stats = {k: 0 for k in _STAT_KEYS}
    if sp.exists():
        try:
            stats.update(json.loads(sp.read_text(encoding="utf-8")))
        except Exception:
            pass
    n = stats.get("sessions", 0) or 0
    prev_lat = stats.get("avgLatency", 0) or 0
    prev_cache = stats.get("cacheRate", 0) or 0
    new_n = n + 1
    if cached:
        new_lat = prev_lat
    else:
        new_lat = round((prev_lat * n + total) / new_n, 2) if n else round(total, 2)
    new_cache = round((prev_cache * n + (100 if cached else 0)) / new_n)
    stats["sessions"] = new_n
    stats["avgLatency"] = new_lat
    stats["cacheRate"] = new_cache
    _atomic_write(sp, stats)


# ── Analitika ──
def log_event(avatar_id, query, cached, gpt=0, tts=0, video=0, total=0):
    aid = avatar_id or "madina_lp"
    ev = {
        "ts": _now_iso(),
        "avatar_id": aid,
        "query": query,
        "cached": bool(cached),
        "gpt": round(gpt, 3), "tts": round(tts, 3),
        "video": round(video, 3), "total": round(total, 3),
    }
    with _lock:
        path = avatar_events_file(aid)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        try:
            _bump_stats(aid, total, cached)
        except Exception as e:
            print(f"[avatar_store] stat yangilash xato: {e}")


def _read_events_for(avatar_id):
    path = avatar_events_file(avatar_id)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def _read_all_events(ids):
    out = []
    for aid in ids:
        out.extend(_read_events_for(aid))
    return out


# Eventlar bo'sh bo'lganda (yangi o'rnatish) ko'rsatiladigan demo analitika.
_DEMO_ANALYTICS = {
    "seed": True,
    "totals": {"sessions": 0, "avgLatency": 0, "cacheRate": 0, "csat": 4.6, "uptime": 99.7},
    "latencyBreakdown": [
        {"stage": "GPT", "value": 0.6, "color": "var(--brass)"},
        {"stage": "Ovoz", "value": 0.7, "color": "var(--brass-2)"},
        {"stage": "Video", "value": 1.1, "color": "var(--navy)"},
    ],
    "daily": [],
    "topQueries": [],
}


def analytics():
    with _lock:
        _ensure_seed()
        ids = _read_registry() or []
        avatars = [a for a in (_load_avatar(i) for i in ids) if a]
        events = _read_all_events(ids)

    total_sessions = sum(a.get("sessions", 0) for a in avatars)
    if not events:
        demo = dict(_DEMO_ANALYTICS)
        demo["totals"] = dict(demo["totals"])
        demo["totals"]["sessions"] = total_sessions
        return demo

    n = len(events)
    non_cached = [e for e in events if not e["cached"]]
    cached_n = n - len(non_cached)

    def _avg(key):
        vals = [e[key] for e in non_cached if e.get(key)]
        return round(sum(vals) / len(vals), 2) if vals else 0

    avg_total = _avg("total")
    cache_rate = round(cached_n / n * 100) if n else 0

    g, t, v = _avg("gpt"), _avg("tts"), _avg("video")
    latency_breakdown = [
        {"stage": "GPT", "value": g, "color": "var(--brass)"},
        {"stage": "Ovoz", "value": t, "color": "var(--brass-2)"},
        {"stage": "Video", "value": v, "color": "var(--navy)"},
    ]

    today = datetime.now(timezone.utc).date()
    buckets = {}
    for e in events:
        try:
            d = datetime.fromisoformat(e["ts"]).date()
        except Exception:
            continue
        buckets.setdefault(d, []).append(e)
    daily = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        evs = buckets.get(day, [])
        lats = [x["total"] for x in evs if not x["cached"] and x.get("total")]
        daily.append({
            "d": day.strftime("%d"),
            "sessions": len(evs),
            "latency": round(sum(lats) / len(lats), 2) if lats else 0,
        })

    counts = {}
    cached_flag = {}
    for e in events:
        q = (e.get("query") or "").strip()
        if not q:
            continue
        counts[q] = counts.get(q, 0) + 1
        cached_flag[q] = cached_flag.get(q, False) or e["cached"]
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
    top_queries = [{"q": q, "n": c, "cached": cached_flag.get(q, False)} for q, c in top]

    csat = next((a.get("csat") for a in avatars if a.get("csat")), 4.6)

    return {
        "seed": False,
        "totals": {
            "sessions": total_sessions or n,
            "avgLatency": avg_total,
            "cacheRate": cache_rate,
            "csat": csat,
            "uptime": 99.7,
        },
        "latencyBreakdown": latency_breakdown,
        "daily": daily,
        "topQueries": top_queries,
    }
