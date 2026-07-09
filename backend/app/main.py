"""FastAPI ilova fabrikasi — LP-MuseTalk avatar serveri (port 8100).

Public (loginsiz):
  /                     -> SPA: foydalanuvchi real-time ovozli suhbat
  /api/ws/avatar/realtime      -> real-time WebSocket (streaming STT → video)
  GET /api/avatars      -> avatar ro'yxati (o'qish)
  /voices, /idle.jpg, /health, /videos/...

Admin (Authorization: Bearer <token>, /api/auth/login orqali):
  POST/PUT/DELETE /api/avatars... -> CRUD, photo, build-idle, build-musetalk
  GET /api/analytics, POST /cache/clear

SPA endi ROOT '/' da: '/' = user, '/admin/*' = panel (login bilan).
Ishga tushirish: bash run.sh
"""
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    analytics, auth, avatars, canned, chat, conversations, knowledge, studio, system,
)
from app.core.paths import FRONTEND_DIST
from app.realtime.ws import router as realtime_router

# DIQQAT: `app.services.musetalk` (torch/cv2/og'ir ML) MODUL YUQORISIDA import
# QILINMAYDI — faqat lifespan ichidagi fon thread'da (warmup paytida). Bu `create_app()`
# ni og'ir bog'liqliklarsiz import qilish imkonini beradi (test/CI yengil muhitda).

log = logging.getLogger("app.main")


class SPAStaticFiles(StaticFiles):
    """SPA fallback: mavjud bo'lmagan yo'l (react-router chuqur havolasi) → index.html.

    Vite build qilingan SPA `createBrowserRouter` ishlatadi, shuning uchun
    /studio/analytics yoki /studio/editor/new kabi yo'llar to'g'ridan-to'g'ri
    ochilganda yoki sahifa yangilanganda server index.html'ni qaytarishi kerak.
    Haqiqiy fayllar (assets/...) odatdagidek beriladi.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startupda model yuklash + warmup (birinchi so'rov tez bo'lsin).
    # AVATAR_STUDIO_SKIP_WARMUP=1 → og'ir model yuklashni o'tkazib yuborish (test/CI).
    def _bg():
        try:
            # Og'ir importlar shu yerda (modul yuqorisida emas) — yengil muhitda import bezovta qilmaydi.
            from app.services.musetalk import preload_artifact, warmup
            warmup()
            # Real avatarlar artefaktini (200 kadr/mask) keshga oldindan yuklaymiz —
            # foydalanuvchining BIRINCHI savoli sekin bo'lmasligi uchun.
            _first_real = None
            try:
                from app.services import avatar_store, musetalk
                for av in avatar_store.list_avatars():
                    if av.get("real"):
                        if _first_real is None:
                            _first_real = av["id"]
                        # Native + studio (use_max_dim) + JONLI (rt_max_dim, past
                        # rezolyutsiya) variantlarni isitamiz — birinchi real-time
                        # so'rov artefakt resize narxini to'lamasin (TTFF past).
                        preload_artifact(av["id"], musetalk.use_max_dim(av))
                        preload_artifact(av["id"], musetalk.rt_max_dim(av))
            except Exception as e:
                log.warning("artefakt preload xato: %s", e)
            # Stream (real-time) yo'lini isitamiz — low-latency nvenc enkoder + oqim
            # birinchi JONLI so'rovda JIT bo'lmasin (sovuq-start TTFF ~9s edi).
            try:
                from app.services import musetalk
                if _first_real:
                    musetalk.warmup_stream(_first_real)
            except Exception as e:
                log.warning("stream warmup xato: %s", e)
            # TARMOQ ulanishlarini isitamiz — birinchi so'rov sovuq TLS/ulanish narxini
            # to'lamasin (kuzatilgan: sovuq 1-so'rov ~9s, ko'p qismi GPT/TTS ulanish
            # setup). Kichik so'rovlar (1 token / qisqa wav), alohida history_key.
            try:
                from app.services.gpt import ask_gpt
                ask_gpt("salom", system_prompt="Bir so'z bilan javob ber.",
                        max_tokens=1, history_key="__warmup__")
                log.info("gpt ulanish isitildi", extra={"event": "gpt_warm"})
            except Exception as e:
                log.warning("gpt warmup xato: %s", e)
            try:
                from app.services.tts import tts, VOICES
                import tempfile as _tf
                _voice = "yulduz" if "yulduz" in VOICES else "madina"
                _wt = _tf.NamedTemporaryFile(suffix=".wav", delete=False)
                _wt.close()
                tts("salom", _wt.name, voice=_voice)
                os.remove(_wt.name)
                log.info("tts ulanish isitildi", extra={"event": "tts_warm"})
            except Exception as e:
                log.warning("tts warmup xato: %s", e)
            # Jonli temir yo'l brauzer sessiyasini oldindan ochamiz (1-savol tez bo'lsin).
            try:
                from app.services import railway
                railway.warmup()
            except Exception as e:
                log.warning("railway warmup xato: %s", e)
        except Exception as e:
            log.warning("warmup xato: %r", e, exc_info=True)

    if os.environ.get("AVATAR_STUDIO_SKIP_WARMUP", "").strip() not in ("1", "true", "True"):
        threading.Thread(target=_bg, daemon=True).start()
    else:
        log.info("warmup o'tkazib yuborildi (AVATAR_STUDIO_SKIP_WARMUP)")
    yield


def create_app() -> FastAPI:
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.core.middleware import RequestIDMiddleware

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT,
                      log_file=settings.LOG_FILE, max_mb=settings.LOG_MAX_MB,
                      backups=settings.LOG_BACKUPS)

    app = FastAPI(title="Madina Avatar (LP-MuseTalk)", lifespan=lifespan)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(auth.router)        # /api/auth/login, /check
    app.include_router(chat.router)
    app.include_router(avatars.router)
    app.include_router(analytics.router)
    app.include_router(system.router)
    app.include_router(studio.router)      # /api/studio (Video Studiya — offline render)
    app.include_router(canned.router)      # /api/canned (tayyor javoblar — pre-rendered Q&A)
    app.include_router(knowledge.router)   # /api/avatars/{id}/knowledge (RAG bilim bazasi)
    app.include_router(conversations.router)  # /api/conversations (suhbat tarixi)
    app.include_router(realtime_router)    # /api/ws/avatar/realtime (alohida modul)

    # SPA — endi ROOT '/' da: '/' = public real-time (user), '/admin/*' = panel (login).
    # API routerlari yuqorida ro'yxatdan o'tgani uchun mount ulardan keyin tekshiriladi.
    # SPAStaticFiles → react-router chuqur havolalari index.html'ga tushadi.
    if FRONTEND_DIST.exists():
        app.mount("/", SPAStaticFiles(directory=str(FRONTEND_DIST), html=True),
                  name="spa")
    else:
        log.warning("frontend build yo'q (%s). `cd frontend && npm install && npm run build` ishga tushiring.",
                    FRONTEND_DIST)

    return app


app = create_app()
