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
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import analytics, auth, avatars, chat, studio, system
from app.core.paths import FRONTEND_DIST, STATIC_DIR
from app.realtime.ws import router as realtime_router
from app.services.musetalk import preload_artifact, warmup


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
    def _bg():
        try:
            warmup()
            # Real avatarlar artefaktini (200 kadr/mask) keshга oldindan yuklaymiz —
            # foydalanuvchining BIRINCHI savoli sekin bo'lmasligi uchun.
            try:
                from app.services import avatar_store
                for av in avatar_store.list_avatars():
                    if av.get("real"):
                        preload_artifact(av["id"])
            except Exception as e:
                print(f"[server] artefakt preload xato: {e}")
        except Exception as e:
            print(f"[server] warmup xato: {e}")
    threading.Thread(target=_bg, daemon=True).start()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Madina Avatar (LP-MuseTalk)", lifespan=lifespan)

    app.include_router(auth.router)        # /api/auth/login, /check
    app.include_router(chat.router)
    app.include_router(avatars.router)
    app.include_router(analytics.router)
    app.include_router(system.router)
    app.include_router(studio.router)      # /api/studio (Video Studiya — offline render)
    app.include_router(realtime_router)    # /api/realtime/ws (alohida modul)

    # SPA — endi ROOT '/' da: '/' = public real-time (user), '/admin/*' = panel (login).
    # API routerlari yuqorida ro'yxatdan o'tgani uchun mount ulardan keyin tekshiriladi.
    # SPAStaticFiles → react-router chuqur havolalari index.html'ga tushadi.
    if FRONTEND_DIST.exists():
        app.mount("/", SPAStaticFiles(directory=str(FRONTEND_DIST), html=True),
                  name="spa")
    else:
        print(f"[server] OGOHLANTIRISH: frontend build yo'q ({FRONTEND_DIST}). "
              f"`cd frontend && npm install && npm run build` ishga tushiring.")

    return app


app = create_app()
