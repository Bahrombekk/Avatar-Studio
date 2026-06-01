"""TTS — matn → ovoz. Provayderlar: edge-TTS, Yandex SpeechKit v1 va v3."""
import asyncio
import os
import subprocess
import time

import edge_tts

from app.core.config import load_env_var

# ── Ovozlar reestri ──
#   edge      → edge-TTS (uz-UZ-*Neural)
#   yandex    → Yandex SpeechKit v1 REST (uz-UZ nigora)
#   yandex_v3 → Yandex SpeechKit v3 REST (uz-UZ yulduz — faqat v3 da bor)
_YX_SMOOTH = "dynaudnorm=f=250:g=7,treble=g=-2:f=7000"
VOICES = {
    "madina": {"provider": "edge",   "voice": "uz-UZ-MadinaNeural", "label": "Madina (edge)"},
    "sardor": {"provider": "edge",   "voice": "uz-UZ-SardorNeural", "label": "Sardor (edge)"},
    "nigora": {"provider": "yandex", "voice": "nigora", "lang": "uz-UZ",
               "label": "Nigora (Yandex)", "speed": 0.95, "smooth_af": _YX_SMOOTH},
    "yulduz": {"provider": "yandex_v3", "voice": "yulduz",
               "label": "Yulduz (Yandex)", "speed": 0.97, "smooth_af": _YX_SMOOTH},
}
DEFAULT_VOICE = "madina"

# Ikki chetdagi sukunatni kesish filtri (nutq tugagach og'iz g'imirlamasin).
_TRIM_AF = (
    "silenceremove=start_periods=1:start_threshold=-45dB:detection=peak,"
    "areverse,"
    "silenceremove=start_periods=1:start_threshold=-45dB:detection=peak,"
    "areverse"
)

YANDEX_TTS_URL    = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
YANDEX_TTS_V3_URL = "https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis"


def _trim_to_wav(tmp_audio: str, wav_path: str, extra_af: str = ""):
    """Istalgan audio → sukunat kesilgan 16k mono WAV (MuseTalk uchun)."""
    af = _TRIM_AF + ("," + extra_af if extra_af else "")
    subprocess.run([
        "ffmpeg", "-y", "-i", tmp_audio, "-af", af,
        "-ar", "16000", "-ac", "1", wav_path,
    ], capture_output=True)


async def _tts_edge(text: str, tmp_path: str, voice_id: str):
    await edge_tts.Communicate(text=text, voice=voice_id).save(tmp_path)


def _yx_auth_folder():
    api_key = load_env_var("YX_API_KEY")
    iam_token = load_env_var("YX_IAM_TOKEN")
    folder = load_env_var("YX_FOLDER_ID")
    if api_key:
        auth = f"Api-Key {api_key}"
    elif iam_token:
        auth = f"Bearer {iam_token}"
    else:
        raise RuntimeError("Yandex TTS uchun YX_API_KEY yoki YX_IAM_TOKEN (.env) kerak")
    if not folder:
        raise RuntimeError("Yandex TTS uchun YX_FOLDER_ID (.env) kerak")
    return auth, folder


def _tts_yandex(text: str, tmp_path: str, voice_id: str, lang: str = "uz-UZ", speed: float = 1.0):
    import urllib.request
    import urllib.parse
    import urllib.error
    auth, folder = _yx_auth_folder()
    data = urllib.parse.urlencode({
        "text": text, "lang": lang, "voice": voice_id,
        "speed": f"{speed:.2f}", "folderId": folder,
        "format": "oggopus",
    }).encode("utf-8")
    req = urllib.request.Request(YANDEX_TTS_URL, data=data, headers={"Authorization": auth})
    audio = None
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio = resp.read()
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Yandex TTS {e.code}: {body}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    if audio is None:
        raise RuntimeError(f"Yandex TTS tarmoq xatosi (3 urinish): {last_err}")
    with open(tmp_path, "wb") as f:
        f.write(audio)


def _tts_yandex_v3(text: str, tmp_path: str, voice_id: str, speed: float = 1.0):
    """Yandex SpeechKit v3 (yulduz kabi yangi ovozlar shu yerda)."""
    import json as _json
    import base64
    import urllib.request
    import urllib.error
    auth, folder = _yx_auth_folder()
    body = _json.dumps({
        "text": text,
        "outputAudioSpec": {"containerAudio": {"containerAudioType": "OGG_OPUS"}},
        "hints": [{"voice": voice_id}, {"speed": speed}],
        "loudnessNormalizationType": "LUFS",
    }).encode("utf-8")
    req = urllib.request.Request(YANDEX_TTS_V3_URL, data=body, headers={
        "Authorization": auth, "x-folder-id": folder,
        "Content-Type": "application/json",
    })
    raw = None
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Yandex TTS v3 {e.code}: {body_txt}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    if raw is None:
        raise RuntimeError(f"Yandex TTS v3 tarmoq xatosi (3 urinish): {last_err}")
    audio = bytearray()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = _json.loads(line)
        except Exception:
            continue
        chunk = obj.get("result", {}).get("audioChunk", {}).get("data")
        if chunk:
            audio.extend(base64.b64decode(chunk))
    if not audio:
        raise RuntimeError("Yandex TTS v3: audio bo'sh qaytdi")
    with open(tmp_path, "wb") as f:
        f.write(bytes(audio))


def tts(text: str, wav_path: str, voice: str = DEFAULT_VOICE):
    spec = VOICES.get(voice) or VOICES[DEFAULT_VOICE]
    if spec["provider"] == "edge":
        tmp = wav_path.replace(".wav", ".mp3")
        asyncio.run(_tts_edge(text, tmp, spec["voice"]))
    elif spec["provider"] == "yandex":
        tmp = wav_path.replace(".wav", ".ogg")
        _tts_yandex(text, tmp, spec["voice"], spec.get("lang", "uz-UZ"),
                    speed=spec.get("speed", 1.0))
    elif spec["provider"] == "yandex_v3":
        tmp = wav_path.replace(".wav", ".ogg")
        _tts_yandex_v3(text, tmp, spec["voice"], speed=spec.get("speed", 1.0))
    else:
        raise RuntimeError(f"Noma'lum provayder: {spec['provider']}")
    _trim_to_wav(tmp, wav_path, extra_af=spec.get("smooth_af", ""))
    try:
        os.remove(tmp)
    except OSError:
        pass
