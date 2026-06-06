"""Nutqni matnga (STT) — Yandex SpeechKit v1 recognize.

Mikrofon audiosi (brauzer MediaRecorder → webm/opus) ffmpeg bilan OggOpus'ga
o'giriladi va Yandex'ga yuboriladi. Kalit: YX_SPEECH_TO_SPEECH_KEY (.env).
"""
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from app.core.config import load_env_var

STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"

# Avatar tili → Yandex STT til kodi.
_LANG = {"uz": "uz-UZ", "ru": "ru-RU", "en": "en-US", "kk": "kk-KZ"}


def _to_oggopus(raw: bytes) -> bytes:
    """Mikrofon XOM PCM oqimini (s16le, 16kHz, mono — RealtimePage WS orqali yuboradi)
    mono OggOpus'ga o'giradi. Frontend ScriptProcessor'dan Int16 PCM yuboradi, shuning
    uchun ffmpeg'ga kirish formatini ANIQ aytamiz (aks holda 'Invalid data' xatosi)."""
    p = subprocess.run(
        ["ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1", "-i", "pipe:0",
         "-ac", "1", "-c:a", "libopus", "-f", "ogg", "pipe:1"],
        input=raw, capture_output=True,
    )
    if p.returncode != 0 or not p.stdout:
        err = (p.stderr or b"").decode("utf-8", "replace")[-300:]
        raise RuntimeError(f"Audio konvertatsiya xato (ffmpeg): {err}")
    return p.stdout


def recognize(audio: bytes, language: str = "uz") -> str:
    """Audio baytlarini matnga aylantiradi. Xato → RuntimeError."""
    key = load_env_var("YX_SPEECH_TO_SPEECH_KEY") or load_env_var("YX_API_KEY")
    folder = load_env_var("YX_FOLDER_ID")
    if not key:
        raise RuntimeError("STT uchun YX_SPEECH_TO_SPEECH_KEY (.env) kerak")
    if not folder:
        raise RuntimeError("STT uchun YX_FOLDER_ID (.env) kerak")
    if not audio:
        return ""

    ogg = _to_oggopus(audio)
    lang = _LANG.get((language or "uz").lower(), "ru-RU")
    qs = urllib.parse.urlencode({
        "topic": "general", "folderId": folder, "lang": lang, "format": "oggopus",
    })
    req = urllib.request.Request(
        f"{STT_URL}?{qs}", data=ogg,
        headers={"Authorization": f"Api-Key {key}",
                 "Content-Type": "application/octet-stream"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            obj = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Yandex STT {e.code}: {body}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"Yandex STT tarmoq xatosi: {e}") from None
    return (obj.get("result") or "").strip()
