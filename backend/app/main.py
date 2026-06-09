"""FastAPI ilova fabrikasi — LP-MuseTalk avatar serveri (port 8100).

Public (loginsiz):
  /                     -> SPA: foydalanuvchi real-time ovozli suhbat
  /api/realtime/ws      -> real-time WebSocket (streaming STT → video)
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
            try:
                from app.services import avatar_store, musetalk
                for av in avatar_store.list_avatars():
                    if av.get("real"):
                        # Native + ishlatiladigan (kichraytirilgan) variantni isitamiz.
                        preload_artifact(av["id"], musetalk.use_max_dim(av))
            except Exception as e:
                log.warning("artefakt preload xato: %s", e)
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
    configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

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
    app.include_router(realtime_router)    # /api/realtime/ws (alohida modul)

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
