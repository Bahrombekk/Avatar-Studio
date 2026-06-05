"""Video Studiya — offline video render (HeyGen uslubi).

Matn manbasi: 'script' (admin yozgan matn, AYNAN gapiriladi) yoki 'gpt' (prompt'dan
GPT skript yozadi). Quvur: matn → TTS → MuseTalk (to'liq fayl) → kutubxonaga saqlash.
Real-time emas — offline, shuning uchun sifatga ustuvorlik (kelajakda HD yuz tiklash).

Saqlash:
  data/renders/index.json     → render meta ro'yxati (eng yangi birinchi)
  data/renders/<id>.mp4        → tayyor video
"""
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
import wave

from app.core.paths import RENDERS_DIR, RENDERS_INDEX, render_file, TEMP_DIR
from app.services import avatar_store, musetalk
from app.services.gpt import analyze_script, ask_gpt, build_system_prompt
from app.services.tts import tts, VOICES, DEFAULT_VOICE

_lock = threading.Lock()
_JOBS = {}   # render_id → {state, error, progress, meta}  (jonli holat)

MAX_SCRIPT_CHARS = 2000


def _load_index() -> list:
    if not RENDERS_INDEX.exists():
        return []
    try:
        with open(RENDERS_INDEX, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_index(items: list) -> None:
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = RENDERS_INDEX.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    tmp.replace(RENDERS_INDEX)


def _index_add(meta: dict) -> None:
    with _lock:
        items = _load_index()
        items = [it for it in items if it.get("id") != meta["id"]]
        items.insert(0, meta)
        _save_index(items)


def list_renders() -> list:
    return _load_index()


def render_status(render_id: str) -> dict:
    job = _JOBS.get(render_id)
    if job:
        return job
    for it in _load_index():
        if it.get("id") == render_id:
            return {"state": it.get("state", "done"), "error": None, "meta": it}
    return {"state": "unknown", "error": "topilmadi"}


def delete_render(render_id: str) -> bool:
    with _lock:
        items = _load_index()
        new = [it for it in items if it.get("id") != render_id]
        if len(new) == len(items):
            found = False
        else:
            _save_index(new)
            found = True
    f = render_file(render_id)
    try:
        if f.exists():
            f.unlink()
            found = True
    except OSError:
        pass
    _JOBS.pop(render_id, None)
    return found


def _synth_segments(segments: list, voice: str, base_wav: str) -> bool:
    """Har segmentni alohida sintez qilib, pause_after_ms bilan ulaydi → base_wav.

    Tabiiy nafas/ritm beradi (avatar pauza bilan gapiradi). Xato bo'lsa False
    (chaqiruvchi to'liq matnga qaytadi)."""
    parts = []
    seg_files = []
    try:
        for i, seg in enumerate(segments):
            t = (seg.get("text") or "").strip()
            if not t:
                continue
            sw = base_wav.replace(".wav", f"_seg{i}.wav")
            seg_files.append(sw)
            tts(t, sw, voice=voice)
            if not (os.path.exists(sw) and os.path.getsize(sw) > 0):
                continue
            pad = max(0, int(seg.get("pause_after_ms", 250))) / 1000.0
            if pad > 0.02:
                psw = base_wav.replace(".wav", f"_seg{i}p.wav")
                seg_files.append(psw)
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", sw, "-af",
                                f"apad=pad_dur={pad:.3f}", "-ar", "16000", "-ac", "1", psw],
                               capture_output=True, timeout=60)
                parts.append(psw if (os.path.exists(psw) and os.path.getsize(psw) > 0) else sw)
            else:
                parts.append(sw)
        if not parts:
            return False
        if len(parts) == 1:
            shutil.copy(parts[0], base_wav)
            return True
        listf = base_wav.replace(".wav", "_list.txt")
        seg_files.append(listf)
        with open(listf, "w", encoding="utf-8") as f:
            for p in parts:
                f.write(f"file '{p}'\n")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                        "-i", listf, "-ar", "16000", "-ac", "1", base_wav],
                       capture_output=True, timeout=120)
        return os.path.exists(base_wav) and os.path.getsize(base_wav) > 0
    except Exception as e:  # noqa: BLE001
        print(f"[render segments TTS] {e}")
        return False
    finally:
        for p in seg_files:
            try:
                os.remove(p)
            except OSError:
                pass


def _wav_frames(path: str, fps: int) -> int:
    """WAV davomiyligini kadrlarda qaytaradi (segment vaqtini hizalash uchun)."""
    try:
        with wave.open(path, "rb") as w:
            dur = w.getnframes() / float(w.getframerate() or 16000)
        return max(1, round(dur * fps))
    except Exception:  # noqa: BLE001
        return 0


def _synth_segments_timed(segments: list, voice: str, base_wav: str, fps: int):
    """Har segmentni alohida sintez qilib pauza bilan ulaydi → base_wav. Plus HAR
    segmentning kadr sonini (pauza bilan) qaytaradi → bosh-harakat timeline'i uchun.
    (ok, seg_frames) qaytaradi; ok=False bo'lsa chaqiruvchi fallback qiladi."""
    parts, seg_files, seg_frames = [], [], []
    try:
        for i, seg in enumerate(segments):
            t = (seg.get("text") or "").strip()
            if not t:
                seg_frames.append(0)
                continue
            sw = base_wav.replace(".wav", f"_seg{i}.wav")
            seg_files.append(sw)
            sp = _PACE_SPEED.get(seg.get("pace", "medium"), 1.0)   # pace → tezlik
            tts(t, sw, voice=voice, speed=sp)
            if not (os.path.exists(sw) and os.path.getsize(sw) > 0):
                seg_frames.append(0)
                continue
            cur = sw
            pad = max(0, int(seg.get("pause_after_ms", 250))) / 1000.0
            if pad > 0.02:
                psw = base_wav.replace(".wav", f"_seg{i}p.wav")
                seg_files.append(psw)
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", sw, "-af",
                                f"apad=pad_dur={pad:.3f}", "-ar", "16000", "-ac", "1", psw],
                               capture_output=True, timeout=60)
                if os.path.exists(psw) and os.path.getsize(psw) > 0:
                    cur = psw
            parts.append(cur)
            seg_frames.append(_wav_frames(cur, fps))
        if not parts:
            return False, []
        if len(parts) == 1:
            shutil.copy(parts[0], base_wav)
        else:
            listf = base_wav.replace(".wav", "_list.txt")
            seg_files.append(listf)
            with open(listf, "w", encoding="utf-8") as f:
                for p in parts:
                    f.write(f"file '{p}'\n")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                            "-i", listf, "-ar", "16000", "-ac", "1", base_wav],
                           capture_output=True, timeout=120)
        ok = os.path.exists(base_wav) and os.path.getsize(base_wav) > 0
        return ok, seg_frames
    except Exception as e:  # noqa: BLE001
        print(f"[render segments-timed] {e}")
        return False, []
    finally:
        for p in seg_files:
            try:
                os.remove(p)
            except OSError:
                pass


# Bosh harakati primitivi davomiyligi (sekund) — GPT speed bo'yicha (resample bilan).
_MOTION_SPEED_DUR = {"slow": 1.5, "medium": 1.1, "fast": 0.8}
# Segment pace → TTS gapirish tezligi ko'paytuvchisi (tabiiy, kuchli emas).
_PACE_SPEED = {"slow": 0.9, "medium": 1.0, "fast": 1.12}


def _build_motion_units(avatar_id, segments, seg_frames, lead_frames, trail_frames, fps):
    """GPT reja + segment kadrlaridan bosh-harakat unit ketma-ketligini quradi:
    lead-in neytral + har segment uchun (motion primitiv + neytral to'ldirish) +
    lead-out neytral (oxirgi sukunat ham bosh harakati bilan qoplanadi).
    Faqat mavjud primitivlar ishlatiladi. GPT hech qanday harakat bermasa —
    yengil default harakat sepiladi (jonli ko'rinishi kafolatlanadi)."""
    def avail(mt):
        return mt and mt not in ("none", "") and musetalk.has_motion(avatar_id, mt)

    eff = []
    for seg in segments:
        mt = (seg.get("head_motion") or {}).get("type")
        eff.append(mt if avail(mt) else None)

    # Fallback: GPT hech qanday harakat bermasa → har ikkinchi segmentga aylanma harakat.
    if not any(eff):
        cyc = [m for m in ["nod", "tilt_right", "lean_forward", "look_up", "tilt_left",
                            "lean_back", "turn_right", "look_down", "nod"]
               if musetalk.has_motion(avatar_id, m)]
        if cyc:
            j = 0
            for i in range(len(eff)):
                if i % 2 == 1:
                    eff[i] = cyc[j % len(cyc)]
                    j += 1

    units = [("neutral", lead_frames)] if lead_frames > 0 else []
    for i, seg in enumerate(segments):
        sf = seg_frames[i] if i < len(seg_frames) else 0
        if sf <= 0:
            continue
        mt = eff[i]
        if mt:
            dur = _MOTION_SPEED_DUR.get((seg.get("head_motion") or {}).get("speed", "medium"), 1.1)
            mlen = min(sf, max(12, round(dur * fps)))
            units.append((mt, mlen))
            if sf - mlen > 0:
                units.append(("neutral", sf - mlen))
        else:
            units.append(("neutral", sf))
    if trail_frames > 0:
        units.append(("neutral", trail_frames))
    return units


def _script_from_gpt(prompt: str, avatar: dict) -> str:
    """GPT'dan og'zaki SKRIPT yozdiradi (suhbat emas — to'liq matn)."""
    persona = (avatar or {}).get("persona", "")
    language = (avatar or {}).get("language", "uz")
    base, _ = build_system_prompt(persona, "long", language)
    sp = (base + "\n\nVAZIFA: Quyidagi mavzu/ko'rsatma bo'yicha AVATAR aytadigan "
          "og'zaki skript yoz. Faqat aytiladigan matnni ber (sahna ko'rsatmalari, "
          "qavslar, markdown YO'Q). Tabiiy, ravon gaplar.")
    return ask_gpt(prompt, system_prompt=sp, temperature=0.6, max_tokens=700,
                   history_key=None)


def start_render(avatar_id: str, text: str = "", voice: str = None,
                 mode: str = "script", prompt: str = "", hd: bool = False,
                 title: str = "") -> str:
    """Renderni fon thread'ida boshlaydi. render_id qaytaradi."""
    avatar = avatar_store.get_avatar(avatar_id)
    if avatar is None:
        raise ValueError("Avatar topilmadi")
    if not avatar.get("real"):
        raise ValueError("Avatar tayyor emas (idle + artefakt qurilmagan)")
    use_voice = voice or avatar.get("voice") or DEFAULT_VOICE
    if use_voice not in VOICES:
        raise ValueError(f"Noma'lum ovoz: {use_voice}")
    if mode == "script":
        text = (text or "").strip()
        if not text:
            raise ValueError("Skript matni bo'sh")
        if len(text) > MAX_SCRIPT_CHARS:
            raise ValueError(f"Skript juda uzun (maks {MAX_SCRIPT_CHARS} belgi)")
    else:
        if not (prompt or "").strip():
            raise ValueError("GPT uchun mavzu/prompt bo'sh")

    rid = uuid.uuid4().hex[:12]
    fps = int(avatar.get("fps", 25)) or 25
    meta = {
        "id": rid, "title": (title or "").strip() or "Nomsiz video",
        "avatar_id": avatar_id, "avatar_name": avatar.get("name", avatar_id),
        "voice": use_voice, "mode": mode, "hd": bool(hd),
        "text": text if mode == "script" else "", "prompt": prompt,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "state": "processing",
    }
    _JOBS[rid] = {"state": "processing", "error": None, "meta": meta}
    t = threading.Thread(target=_run, args=(rid, avatar, use_voice, mode, text,
                                            prompt, hd, fps, meta), daemon=True)
    t.start()
    return rid


def _run(rid, avatar, voice, mode, text, prompt, hd, fps, meta):
    avatar_id = avatar["id"]
    language = avatar.get("language", "uz")
    wav = str(TEMP_DIR / f"render_{rid}.wav")
    wav_pad = str(TEMP_DIR / f"render_{rid}_pad.wav")
    try:
        # 1. Matn (GPT bo'lsa skript yozdiramiz).
        if mode == "gpt":
            text = _script_from_gpt(prompt, avatar)
        # 2. Avatar skript analizatori: normalizatsiya (raqam/sana→so'z) + his-tuyg'u
        #    + segment/pauza/bosh-harakat rejasi (full_text + segments).
        plan = analyze_script(text, language)
        full_text = plan.get("full_text") or text
        segments = plan.get("segments") or []
        meta["text"] = full_text
        meta["segments"] = segments        # bosh harakati rejasi — 2-faza ishlatadi
        _JOBS[rid]["meta"] = meta
        # 3. TTS. BOSH-HARAKAT rejimi (segments bor + avatar primitivlari bor) bo'lsa:
        #    segmentli + har segment kadr soni (timeline hizalash uchun). Aks holda fallback.
        motion_mode = bool(segments) and musetalk.has_motion(avatar_id, "neutral")
        seg_frames = []
        if motion_mode:
            ok_tts, seg_frames = _synth_segments_timed(segments, voice, wav, fps)
            motion_mode = ok_tts
        if not motion_mode:
            done = False
            if len(segments) >= 2:
                done = _synth_segments(segments, voice, wav)
            if not done:
                tts(full_text, wav, voice=voice)

        # 4. Lead-in + lead-out: boshiga ~0.7s, oxiriga ~0.7s sukunat → avatar
        #    gapirishdan OLDIN va KEYIN jim (og'iz yopiq, bosh tabiiy) turadi,
        #    keyin gapiradi / jimga tinch tushadi (keskin boshlanmaydi/uzulmaydi).
        lead_sec, trail_sec = 0.85, 1.0
        src_wav = wav
        try:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-af",
                            f"adelay={int(lead_sec * 1000)},apad=pad_dur={trail_sec:.3f}",
                            "-ar", "16000", "-ac", "1", wav_pad],
                           capture_output=True, timeout=60)
            if os.path.exists(wav_pad) and os.path.getsize(wav_pad) > 0:
                src_wav = wav_pad
        except Exception:  # noqa: BLE001
            pass

        # 5. MuseTalk — bosh-harakat rejimida ASSEMBLED timeline (GPT reja → primitivlar),
        #    aks holda oddiy idle artefakt.
        out = render_file(rid)
        art = None
        if motion_mode:
            try:
                lead_frames = round(lead_sec * fps)
                trail_frames = round(trail_sec * fps)
                units = _build_motion_units(avatar_id, segments, seg_frames, lead_frames,
                                            trail_frames, fps)
                art = musetalk.assemble_motion_timeline(avatar_id, units)
                meta["motion_units"] = [[u[0], int(u[1])] for u in units]
                _JOBS[rid]["meta"] = meta
            except Exception as e:  # noqa: BLE001
                print(f"[render {rid}] motion assemble xato → oddiy idle: {e}")
                art = None
        ok = musetalk.musetalk_infer(src_wav, str(out), fps=fps, avatar_id=avatar_id,
                                     hd=hd, artifact=art)
        if not ok or not out.exists():
            raise RuntimeError("Video generatsiya qilinmadi")
        meta["state"] = "done"
        meta["size"] = out.stat().st_size
        _index_add(meta)
        _JOBS[rid] = {"state": "done", "error": None, "meta": meta}
        try:
            avatar_store.log_event(avatar_id, f"[render] {meta['title']}", False,
                                   gpt=0, tts=0, video=0, total=0)
        except Exception:
            pass
    except Exception as e:  # noqa: BLE001
        meta["state"] = "error"
        _JOBS[rid] = {"state": "error", "error": str(e), "meta": meta}
        print(f"[render {rid}] XATO: {e}")
    finally:
        for p in (wav, wav_pad):
            try:
                os.remove(p)
            except OSError:
                pass
