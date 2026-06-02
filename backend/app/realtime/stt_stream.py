"""Yandex SpeechKit v3 STREAMING STT (gRPC) — gapirayotganda real-time tanish.

Mikrofon PCM (16k mono int16) bo'laklari kelishi bilan Yandex'ga uzatiladi va
tanish GAPIRISH PAYTIDA boradi. Foydalanuvchi to'xtaganda yakuniy matn deyarli
tayyor → STT kechikishi keskin kamayadi (REST recognize'dan farqli).

Kalit: YX_SPEECH_TO_SPEECH_KEY (yoki YX_API_KEY) + YX_FOLDER_ID (.env).
"""
import queue
import threading

import grpc
from yandex.cloud.ai.stt.v3 import stt_pb2, stt_service_pb2_grpc

from app.core.config import load_env_var

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
        self._lang = _LANG.get((language or "uz").lower(), "ru-RU")
        self._key = load_env_var("YX_SPEECH_TO_SPEECH_KEY") or load_env_var("YX_API_KEY")
        self._folder = load_env_var("YX_FOLDER_ID")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def feed(self, pcm: bytes):
        if pcm:
            self._q.put(pcm)

    def finish(self):
        self._q.put(_SENTINEL)

    def result(self, timeout: float = 10.0) -> str:
        self._done.wait(timeout)
        if self._err:
            raise RuntimeError(self._err)
        return " ".join(self._finals).strip() or self.partial.strip()

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
