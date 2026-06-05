"""Tayyor javoblar (pre-rendered Q&A) — real-time savol mosligi uchun.

Admin oldindan savol+javob videolarini generatsiya qiladi (Video Studiya quvuri bilan).
Real-time'da foydalanuvchi savoli biror tayyor javobning savol-variantlariga mos kelsa,
tayyor video DARROV o'ynaladi (GPT+TTS+jonli-gen o'rniga) — tez va idle bilan silliq
(render lead-in sukunat + oxirida idle'ga crossfade tufayli boshi/oxiri idle pozasida).

Saqlash:
  data/canned/index.json   → [{id, questions[], text, avatar_id, voice, state, ...}]
  data/canned/<id>.mp4      → tayyor video
"""
import difflib
import json
import os
import re
import subprocess
import threading
import time
import uuid

from app.core.paths import CANNED_DIR, CANNED_INDEX, canned_file, TEMP_DIR
from app.services import avatar_store, musetalk, render
from app.services.gpt import analyze_script
from app.services.tts import DEFAULT_VOICE, VOICES, tts

_lock = threading.Lock()
_JOBS = {}                  # cid → {state, error, meta}
MAX_CHARS = 2000
# Savol mosligi chegarasi (0..1). Variantga shu darajadan yuqori o'xshashlik → mos.
_MATCH_RATIO = float(os.environ.get("CANNED_MATCH_RATIO", "0.82"))
# Semantik (embedding) moslik chegarasi (cosine). Parafrazalar uchun. Past=ko'proq mos
# (xato mos xavfi), yuqori=qattiqroq. 0.55 ≈ ma'no bir xil, lekin boshqa so'zlar.
_SEM_THRESHOLD = float(os.environ.get("CANNED_SEM_THRESHOLD", "0.58"))


def _cos(a, b) -> float:
    """Ikki vektor kosinus o'xshashligi (numpy'siz)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sa = sb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        sa += x * x
        sb += y * y
    if sa <= 0 or sb <= 0:
        return 0.0
    return dot / ((sa ** 0.5) * (sb ** 0.5))


# ── Index ──
def _load() -> list:
    if not CANNED_INDEX.exists():
        return []
    try:
        with open(CANNED_INDEX, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(items: list) -> None:
    CANNED_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CANNED_INDEX.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    tmp.replace(CANNED_INDEX)


def _index_upsert(meta: dict) -> None:
    with _lock:
        items = [it for it in _load() if it.get("id") != meta["id"]]
        items.insert(0, meta)
        _save(items)


def list_canned() -> list:
    """Tayyor (index) + faol (processing/error) tayyor javoblar — frontend jarayonni ko'radi."""
    idx = _load()
    ids = {it.get("id") for it in idx}
    active = [j["meta"] for j in _JOBS.values()
              if j.get("state") in ("processing", "error")
              and j.get("meta", {}).get("id") not in ids]
    active.sort(key=lambda m: m.get("created", ""), reverse=True)
    return active + idx


def get_status(cid: str) -> dict:
    job = _JOBS.get(cid)
    if job:
        return job
    for it in _load():
        if it.get("id") == cid:
            return {"state": it.get("state", "done"), "error": None, "meta": it}
    return {"state": "unknown", "error": "topilmadi"}


def delete_canned(cid: str) -> bool:
    with _lock:
        items = _load()
        new = [it for it in items if it.get("id") != cid]
        found = len(new) != len(items)
        if found:
            _save(new)
    f = canned_file(cid)
    try:
        if f.exists():
            f.unlink()
            found = True
    except OSError:
        pass
    _JOBS.pop(cid, None)
    return found


def update_questions(cid: str, questions: list) -> bool:
    """Mavjud yozuvning savol variantlarini yangilaydi (video qayta qurilmaydi)."""
    qs = _clean_questions(questions)
    with _lock:
        items = _load()
        for it in items:
            if it.get("id") == cid:
                it["questions"] = qs
                _save(items)
                return True
    return False


# ── Matching (real-time savol → tayyor javob) ──
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("‘", "'").replace("’", "'").replace("ʻ", "'")
    s = _PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _clean_questions(questions) -> list:
    out, seen = [], set()
    for q in (questions or []):
        q = (q or "").strip()
        n = _norm(q)
        if q and n and n not in seen:
            seen.add(n)
            out.append(q)
    return out[:12]


def match(avatar_id: str, text: str):
    """Foydalanuvchi savoli (text) biror tayyor javobga mos kelsa, o'sha yozuvni
    qaytaradi (aks holda None). Variantlar bo'yicha: aniq / qism / fuzzy o'xshashlik."""
    n = _norm(text)
    if not n or len(n) < 2:
        return None
    items = [it for it in _load()
             if it.get("avatar_id") == avatar_id and it.get("state") == "done"]
    if not items:
        return None
    # 1) Tez yo'l — aniq / qism / fuzzy (API'siz, darrov).
    best, best_score = None, 0.0
    for it in items:
        for q in it.get("questions", []):
            qn = _norm(q)
            if not qn:
                continue
            if qn == n:
                return it
            score = difflib.SequenceMatcher(None, qn, n).ratio()
            if qn in n or n in qn:
                score = max(score, 0.9)
            if score > best_score:
                best_score, best = score, it
    if best_score >= _MATCH_RATIO:
        return best
    # 2) Semantik yo'l — parafrazalar (boshqa so'z, bir ma'no). 1 embedding chaqiruv
    #    (~80ms) faqat fuzzy topmaganda; topmasa jonli GPT'ga tushadi (kechikish yo'q).
    try:
        from app.services.gpt import embed_texts
        qv = embed_texts([text])
    except Exception:  # noqa: BLE001
        qv = []
    if qv:
        qvec = qv[0]
        bsem, bscore = None, 0.0
        for it in items:
            for emb in it.get("q_emb", []):
                c = _cos(qvec, emb)
                if c > bscore:
                    bscore, bsem = c, it
        if bsem and bscore >= _SEM_THRESHOLD:
            return bsem
    return None


def video_url(cid: str) -> str:
    return f"/api/canned/{cid}/video"


# ── Generatsiya (render quvuri) ──
def start_generate(avatar_id: str, questions: list, text: str = "", voice: str = None,
                   mode: str = "script", prompt: str = "", title: str = "",
                   hd: bool = False) -> str:
    avatar = avatar_store.get_avatar(avatar_id)
    if avatar is None:
        raise ValueError("Avatar topilmadi")
    if not avatar.get("real"):
        raise ValueError("Avatar tayyor emas (idle + artefakt qurilmagan)")
    qs = _clean_questions(questions)
    if not qs:
        raise ValueError("Kamida bitta savol varianti kerak")
    use_voice = voice or avatar.get("voice") or DEFAULT_VOICE
    if use_voice not in VOICES:
        raise ValueError(f"Noma'lum ovoz: {use_voice}")
    if mode == "script":
        text = (text or "").strip()
        if not text:
            raise ValueError("Javob matni bo'sh")
        if len(text) > MAX_CHARS:
            raise ValueError(f"Javob juda uzun (maks {MAX_CHARS} belgi)")
    elif not (prompt or "").strip():
        raise ValueError("GPT uchun mavzu/prompt bo'sh")

    cid = uuid.uuid4().hex[:12]
    fps = int(avatar.get("fps", 25)) or 25
    meta = {
        "id": cid, "title": (title or "").strip() or qs[0][:40],
        "avatar_id": avatar_id, "avatar_name": avatar.get("name", avatar_id),
        "voice": use_voice, "mode": mode, "hd": bool(hd),
        "questions": qs, "text": text if mode == "script" else "", "prompt": prompt,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "state": "processing",
    }
    _JOBS[cid] = {"state": "processing", "error": None, "meta": meta}
    threading.Thread(target=_run, args=(cid, avatar, use_voice, mode, text, prompt, fps, meta),
                     daemon=True).start()
    return cid


def _run(cid, avatar, voice, mode, text, prompt, fps, meta):
    """Render quvurini takrorlaydi (analyze → TTS → motion → musetalk_infer), lekin
    chiqishni canned/<id>.mp4 ga yozadi. Boshi/oxiri idle pozada (real-time bilan mos)."""
    avatar_id = avatar["id"]
    language = avatar.get("language", "uz")
    wav = str(TEMP_DIR / f"canned_{cid}.wav")
    wav_pad = str(TEMP_DIR / f"canned_{cid}_pad.wav")
    try:
        # Savol variantlarining embeddinglari (semantik matching uchun, bir marta).
        try:
            from app.services.gpt import embed_texts
            meta["q_emb"] = embed_texts(meta.get("questions", []))
        except Exception as e:  # noqa: BLE001
            print(f"[canned {cid}] embed o'tkazildi: {e}")
            meta["q_emb"] = []
        if mode == "gpt":
            text = render._script_from_gpt(prompt, avatar)
        plan = analyze_script(text, language)
        full_text = plan.get("full_text") or text
        segments = plan.get("segments") or []
        meta["text"] = full_text
        _JOBS[cid]["meta"] = meta

        motion_mode = bool(segments) and musetalk.has_motion(avatar_id, "neutral")
        seg_frames = []
        if motion_mode:
            ok_tts, seg_frames = render._synth_segments_timed(segments, voice, wav, fps)
            motion_mode = ok_tts
        if not motion_mode:
            done = render._synth_segments(segments, voice, wav) if len(segments) >= 2 else False
            if not done:
                tts(full_text, wav, voice=voice)

        # Lead-in + lead-out sukunat (real-time idle bilan silliq ulanishi uchun).
        lead_sec, trail_sec = 0.85, 1.0
        src_wav = wav
        try:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-af",
                            f"adelay={int(lead_sec*1000)},apad=pad_dur={trail_sec:.3f}",
                            "-ar", "16000", "-ac", "1", wav_pad],
                           capture_output=True, timeout=60)
            if os.path.exists(wav_pad) and os.path.getsize(wav_pad) > 0:
                src_wav = wav_pad
        except Exception:  # noqa: BLE001
            pass

        out = canned_file(cid)
        art = None
        if motion_mode:
            try:
                lead_frames = round(lead_sec * fps)
                trail_frames = round(trail_sec * fps)
                units = render._build_motion_units(avatar_id, segments, seg_frames,
                                                   lead_frames, trail_frames, fps)
                art = musetalk.assemble_motion_timeline(avatar_id, units)
                meta["motion_units"] = [[u[0], int(u[1])] for u in units]
            except Exception as e:  # noqa: BLE001
                print(f"[canned {cid}] motion assemble xato → oddiy idle: {e}")
                art = None
        ok = musetalk.musetalk_infer(src_wav, str(out), fps=fps, avatar_id=avatar_id,
                                     hd=bool(meta.get("hd")), artifact=art,
                                     max_dim=musetalk.use_max_dim(avatar))
        if not ok or not out.exists():
            raise RuntimeError("Video generatsiya qilinmadi")
        meta["state"] = "done"
        meta["size"] = out.stat().st_size
        _index_upsert(meta)
        _JOBS[cid] = {"state": "done", "error": None, "meta": meta}
    except Exception as e:  # noqa: BLE001
        meta["state"] = "error"
        _JOBS[cid] = {"state": "error", "error": str(e), "meta": meta}
        print(f"[canned {cid}] XATO: {e}")
    finally:
        for p in (wav, wav_pad):
            try:
                os.remove(p)
            except OSError:
                pass
