"""FastAPI ilova fabrikasi — LP-MuseTalk avatar serveri (port 8100).

  GET  /            -> chat UI (static/index.html)
  GET  /idle.jpg    -> idle rasm
  GET  /voices      -> ovozlar reestri
  POST /chat        -> {text, video, timing}
  POST /chat-stream -> SSE: text -> tts_done -> video -> done
  /api/avatars      -> avatar CRUD
  /api/analytics    -> analitika
  /studio           -> Avatar Studio admin (Vite build)
  /health           -> holat

Ishga tushirish: bash run.sh
"""
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import analytics, avatars, chat, system
from app.core.paths import FRONTEND_DIST, STATIC_DIR
from app.services.musetalk import warmup


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startupda model yuklash + warmup (birinchi so'rov tez bo'lsin).
    def _bg():
        try:
            warmup()
        except Exception as e:
            print(f"[server] warmup xato: {e}")
    threading.Thread(target=_bg, daemon=True).start()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Madina Avatar (LP-MuseTalk)", lifespan=lifespan)

    app.include_router(chat.router)
    app.include_router(avatars.router)
    app.include_router(analytics.router)
    app.include_router(system.router)

    @app.get("/", response_class=HTMLResponse)
    def index():
        f = STATIC_DIR / "index.html"
        if not f.exists():
            raise HTTPException(404, "index.html topilmadi")
        return HTMLResponse(f.read_text(encoding="utf-8"))

    # Kesh videolari /videos/{scope}/{voice}/{file} route orqali beriladi (system.py).

    # Avatar Studio admin UI (Vite build natijasi). html=True → SPA fallback.
    if FRONTEND_DIST.exists():
        app.mount("/studio", StaticFiles(directory=str(FRONTEND_DIST), html=True),
                  name="studio")
    else:
        print(f"[server] OGOHLANTIRISH: frontend build yo'q ({FRONTEND_DIST}). "
              f"`cd frontend && npm install && npm run build` ishga tushiring.")

    return app


app = create_app()
