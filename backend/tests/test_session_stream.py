"""Jumla-darajali reply_stream orkestratsiyasi (GPT/TTS mock, GPU'siz).

Tekshiradi:
  • stream eventi ERTA (text'dan oldin) ochiladi — 1-jumla tayyor bo'lishi bilan;
  • barcha jumlalar wav sifatida chunk_queue'ga tushadi va None bilan yakunlanadi;
  • barge-in (cancel) TTS worker'ni to'xtatadi (qolgan jumlalar sintez qilinmaydi).
"""
import threading

import pytest

import app.realtime.session as session


@pytest.fixture()
def patched(monkeypatch, tmp_path):
    """GPT token oqimi + TTS'ni mock qilamiz; pauza-pad (ffmpeg) o'chiriladi."""
    tokens = ["Albatta", ", hozir aytaman. ", "Toshkentdan Samarqandgacha ",
              "chipta narxi o'n bir ming so'm. ", "Yana savol bormi?"]

    def fake_gpt(user_message, **kw):
        yield from tokens

    synthesized = []

    def fake_tts(text, wav_path, voice=None, speed=1.0):
        synthesized.append(text)
        with open(wav_path, "wb") as f:
            f.write(b"RIFF0000WAVE")

    monkeypatch.setattr(session, "ask_gpt_stream", fake_gpt)
    monkeypatch.setattr(session, "tts", fake_tts)
    monkeypatch.setattr(session, "_SENT_PAUSE", 0.0)
    monkeypatch.setattr(session, "_SENTENCE_STREAM", True)
    monkeypatch.setattr(session, "TEMP_DIR", tmp_path)
    # Railway augmentatsiyasi tarmoqqa chiqmasin.
    import app.services.railway as railway
    monkeypatch.setattr(railway, "railway_context", lambda *a, **k: "")
    return synthesized


def _drain(chunk_q, timeout=5.0):
    out = []
    while True:
        c = chunk_q.get(timeout=timeout)
        if c is None:
            return out
        out.append(c)


def test_stream_opens_before_text_and_chunks_flow(patched):
    events = list(session.reply_stream("Narx qancha?", avatar_id=None))
    types = [e["type"] for e in events]

    assert types.count("stream") == 1
    assert "done" in types
    # Oqim matn yakunidan OLDIN ochiladi (erta birinchi ovoz).
    assert types.index("stream") < types.index("text")

    stream_ev = next(e for e in events if e["type"] == "stream")
    assert stream_ev.get("sentence_stream") is True
    sid = stream_ev["url"].rsplit("/", 1)[1]
    info = session.take_pending(sid)
    assert info is not None and info["chunk_queue"] is not None

    chunks = _drain(info["chunk_queue"])
    # Kamida 2 bo'lak (1-jumla erta + qolganlari), har biri mavjud fayl.
    assert len(chunks) >= 2
    import os
    assert all(os.path.exists(c) for c in chunks)
    # 1-jumla — qisqa kirish ("Albatta..."), darrov sintez qilingan.
    assert patched[0].startswith("Albatta")
    # To'liq javob matni yo'qolmagan (hamma jumla qamrab olingan).
    full = " ".join(patched)
    assert "o'n bir ming" in full and "Yana savol bormi?" in full


def test_cancel_stops_tts_worker(patched, monkeypatch):
    cancel = threading.Event()

    real_tts = session.tts
    def tts_then_cancel(text, wav_path, voice=None, speed=1.0):
        real_tts(text, wav_path, voice=voice, speed=speed)
        cancel.set()    # 1-jumladan keyin barge-in
    monkeypatch.setattr(session, "tts", tts_then_cancel)

    events = list(session.reply_stream("Narx qancha?", avatar_id=None, cancel=cancel))
    stream_ev = next(e for e in events if e["type"] == "stream")
    sid = stream_ev["url"].rsplit("/", 1)[1]
    info = session.take_pending(sid)
    chunks = _drain(info["chunk_queue"])
    # Bekor qilingandan keyin worker to'xtaydi — hamma jumla sintez QILINMAYDI.
    assert len(chunks) < 4
    assert len(patched) < 4
