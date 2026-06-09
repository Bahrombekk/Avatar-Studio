"""Strukturali logging — stdlib `logging` ustida JSON formatter + ko'p-kontekstli ID.

`print()` o'rniga butun loyiha `logging.getLogger(__name__)` ishlatadi. Har log
qatori joriy so'rovning kontekstini avtomatik oladi:
  - `request_id`  — middleware har HTTP so'rovga beradi
  - `avatar_id`   — chat/realtime oqimi o'rnatadi (qaysi avatar)
  - `session_id`  — chat sessiyasi (suhbat ipini ajratish)
Bu ID'lar `log_context(...)` orqali o'rnatiladi va shu blok ichidagi HAR QANDAY
log qatoriga (hatto chuqur servis funksiyalarida ham) qo'lda uzatmasdan tushadi.

JSON format prod uchun (structured, agregatorga qulay), text format lokal uchun.
Ixtiyoriy: LOG_FILE berilsa, JSON loglar aylanuvchi (rotating) faylga ham yoziladi.
"""
import contextvars
import json
import logging
import logging.handlers
import os
import sys
import time
from contextlib import contextmanager

# ── So'rov konteksti (contextvar — asyncio + thread xavfsiz) ──
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
avatar_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("avatar_id", default="-")
session_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="-")

# nom → contextvar (filter va log_context shu ro'yxat bo'yicha ishlaydi).
_CTX_VARS = {
    "request_id": request_id_ctx,
    "avatar_id": avatar_id_ctx,
    "session_id": session_id_ctx,
}

_PID = os.getpid()
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}
_CTX_NAMES = set(_CTX_VARS)


@contextmanager
def log_context(**fields):
    """Berilgan kontekst maydonlarini (avatar_id, session_id, request_id) shu blok
    davomida o'rnatadi — ichidagi barcha loglar shu ID'larni oladi. Blokdan chiqilganda
    avvalgi qiymatlar tiklanadi (ichma-ich chaqiruvlar xavfsiz).

        with log_context(avatar_id="madina_lp", session_id=sid):
            ... pipeline ...     # har log avatar_id+session_id bilan chiqadi
    """
    tokens = []
    for key, val in fields.items():
        var = _CTX_VARS.get(key)
        if var is not None and val is not None:
            tokens.append((var, var.set(str(val))))
    try:
        yield
    finally:
        for var, tok in reversed(tokens):
            var.reset(tok)


class _ContextFilter(logging.Filter):
    """Har yozuvga joriy kontekst ID'larini (request_id/avatar_id/session_id) qo'shadi."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name, var in _CTX_VARS.items():
            if not hasattr(record, name):
                setattr(record, name, var.get())
        return True


class JsonFormatter(logging.Formatter):
    """Har yozuvni bitta JSON qatoriga aylantiradi (kontekst + `extra` maydonlar bilan)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "pid": _PID,
        }
        # avatar_id/session_id — faqat o'rnatilgan bo'lsa (shovqin kam bo'lsin).
        for name in ("avatar_id", "session_id"):
            val = getattr(record, name, "-")
            if val and val != "-":
                payload[name] = val
        # `logger.info("...", extra={"foo": 1})` orqali kelgan qo'shimcha maydonlar.
        skip = _RESERVED | _CTX_NAMES
        for k, v in record.__dict__.items():
            if k not in skip and k not in payload and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # default=str — serializatsiya bo'lmaydigan obyektlar (WebSocketProtocol va h.k.)
        # xato tug'dirmasdan str'ga aylanadi (logging hech qachon crash bo'lmaydi).
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Inson o'qishiga qulay lokal format (request_id bilan)."""

    def __init__(self):
        super().__init__("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s",
                         datefmt="%H:%M:%S")


_configured = False


def configure_logging(level: str = "INFO", fmt: str = "json",
                      log_file: str = "", max_mb: int = 10, backups: int = 5) -> None:
    """Root logger'ni bir marta sozlaydi (idempotent).

    log_file berilsa, stdout'ga qo'shimcha JSON loglar aylanuvchi faylga ham yoziladi
    (max_mb hajmga yetganda backups tagacha rotatsiya) — agregatorsiz deploy uchun.
    """
    global _configured
    flt = _ContextFilter()
    json_fmt, text_fmt = JsonFormatter(), TextFormatter()

    root = logging.getLogger()
    root.handlers.clear()

    sh = logging.StreamHandler(sys.stdout)
    sh.addFilter(flt)
    sh.setFormatter(json_fmt if fmt == "json" else text_fmt)
    root.addHandler(sh)

    if log_file:
        try:
            d = os.path.dirname(log_file)
            if d:
                os.makedirs(d, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=max(1, max_mb) * 1024 * 1024,
                backupCount=max(0, backups), encoding="utf-8")
            fh.addFilter(flt)
            fh.setFormatter(json_fmt)        # faylga doim JSON (text bo'lsa ham)
            root.addHandler(fh)
        except Exception as e:  # noqa: BLE001
            root.warning("log fayl handler ochilmadi (%s): %s", log_file, e)

    root.setLevel(getattr(logging, (level or "INFO").upper(), logging.INFO))
    # uvicorn'ning o'z handlerlari bizning formatdan o'tsin.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    _configured = True
