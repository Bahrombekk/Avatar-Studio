"""Yandex SpeechKit v3 STREAMING STT (gRPC) — gapirayotganda real-time tanish.

Mikrofon PCM (16k mono int16) bo'laklari kelishi bilan Yandex'ga uzatiladi va
tanish GAPIRISH PAYTIDA boradi. Foydalanuvchi to'xtaganda yakuniy matn deyarli
tayyor → STT kechikishi keskin kamayadi (REST recognize'dan farqli).

Kalit: YX_SPEECH_TO_SPEECH_KEY (yoki YX_API_KEY) + YX_FOLDER_ID (.env).
"""
import audioop
import io
import logging
import queue
import threading
import wave

import grpc
from yandex.cloud.ai.stt.v3 import stt_pb2, stt_service_pb2_grpc

from app.core.config import load_env_var

log = logging.getLogger(__name__)

_ENDPOINT = "stt.api.cloud.yandex.net:443"
_LANG = {"uz": "uz-UZ", "ru": "ru-RU", "en": "en-US", "kk": "kk-KZ"}
_SENTINEL = None


class StreamingSTT:
    """Gapirish paytida PCM bo'laklarini Yandex'ga oqim qiladi; yakuniy matnni beradi.

    feed(pcm) — har bo'lak; finish() — tugadi; result(timeout) — yakuniy matn.
    """

    def __init__(self, language: str = "uz"):
        self._q: queue.Queue = queue.Queue()
        self._finals = []
        self.partial = ""
        self._done = threading.Event()
        self._err = None
        self._language = language or "uz"
        self._pcm = bytearray()          # REST fallback uchun xom PCM zaxirasi
        self._lang = _LANG.get((language or "uz").lower(), "ru-RU")
        self._key = load_env_var("YX_SPEECH_TO_SPEECH_KEY") or load_env_var("YX_API_KEY")
        self._folder = load_env_var("YX_FOLDER_ID")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def feed(self, pcm: bytes):
        if pcm:
            self._q.put(pcm)
            self._pcm += pcm

    def finish(self):
        self._q.put(_SENTINEL)

    def result(self, timeout: float = 10.0) -> str:
        self._done.wait(timeout)
        if self._err:
            raise RuntimeError(self._err)
        text = (" ".join(self._finals).strip() or self.partial.strip())
        if text:
            return text
        # Streaming bo'sh qaytdi — sabab JIMLIK (mikrofon) yoki Yandex streaming
        # vaqtinchalik bo'sh-qaytishi bo'lishi mumkin. Audio amplitudasini tekshiramiz:
        # haqiqiy nutq bo'lsa, REST recognize (boshqa endpoint) bilan QAYTA urinamiz.
        try:
            amp = audioop.max(bytes(self._pcm), 2) if self._pcm else 0
        except Exception:  # noqa: BLE001
            amp = 0
        log.info("[stt] streaming bo'sh — PCM=%d bayt, max_amplituda=%d", len(self._pcm), amp)
        if amp < 800:
            return ""        # jimlik/shovqin — mikrofon haqiqiy nutq yubormadi
        return self._rest_fallback()

    def _rest_fallback(self) -> str:
        """Xom PCM'ni WAV qilib Yandex REST recognize'ga yuboradi (streaming bo'sh bo'lsa)."""
        try:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(bytes(self._pcm))
            from app.realtime import stt as _rest
            text = _rest.recognize(buf.getvalue(), self._language)
            log.info("[stt] REST fallback natija='%s'", text)
            return text or ""
        except Exception as e:  # noqa: BLE001
            log.warning("[stt] REST fallback xato: %s", e)
            return ""

    # ── ichki ──
    def _requests(self):
        # 1) Sessiya sozlamalari (real-time, LINEAR16_PCM 16k mono, til).
        opts = stt_pb2.StreamingOptions(
            recognition_model=stt_pb2.RecognitionModelOptions(
                audio_format=stt_pb2.AudioFormatOptions(
                    raw_audio=stt_pb2.RawAudio(
                        audio_encoding=stt_pb2.RawAudio.LINEAR16_PCM,
                        sample_rate_hertz=16000,
                        audio_channel_count=1,
                    )
                ),
                language_restriction=stt_pb2.LanguageRestrictionOptions(
                    restriction_type=stt_pb2.LanguageRestrictionOptions.WHITELIST,
                    language_code=[self._lang],
                ),
                audio_processing_type=stt_pb2.RecognitionModelOptions.REAL_TIME,
            )
        )
        yield stt_pb2.StreamingRequest(session_options=opts)
        # 2) Audio bo'laklari (navbatdan).
        while True:
            chunk = self._q.get()
            if chunk is _SENTINEL:
                break
            yield stt_pb2.StreamingRequest(chunk=stt_pb2.AudioChunk(data=chunk))

    def _run(self):
        try:
            cred = grpc.ssl_channel_credentials()
            chan = grpc.secure_channel(_ENDPOINT, cred)
            stub = stt_service_pb2_grpc.RecognizerStub(chan)
            meta = [("authorization", f"Api-Key {self._key}"),
                    ("x-folder-id", self._folder)]
            for resp in stub.RecognizeStreaming(self._requests(), metadata=meta):
                etype = resp.WhichOneof("Event")
                if etype == "partial" and resp.partial.alternatives:
                    self.partial = resp.partial.alternatives[0].text
                elif etype == "final" and resp.final.alternatives:
                    self._finals.append(resp.final.alternatives[0].text)
                elif etype == "final_refinement":
                    alts = resp.final_refinement.normalized_text.alternatives
                    if alts:
                        # Oxirgi final'ni tozalangan (normalized) variant bilan almashtiramiz.
                        if self._finals:
                            self._finals[-1] = alts[0].text
                        else:
                            self._finals.append(alts[0].text)
            chan.close()
        except Exception as e:  # noqa: BLE001
            self._err = f"Yandex streaming STT: {e}"
        finally:
            self._done.set()
