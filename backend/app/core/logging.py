"""Strukturali logging — stdlib `logging` ustida JSON formatter + request_id.

`print()` o'rniga butun loyiha `logging.getLogger(__name__)` ishlatadi. Har log
qatori joriy so'rov `request_id`'sini oladi (middleware o'rnatadi) — loglar so'rov
bo'yicha bog'lanadi. JSON format prod uchun (structured), text format lokal uchun.
"""
import contextvars
import json
import logging
import sys
import time

# Joriy so'rov ID'si (middleware o'rnatadi; fon thread'larda bo'sh bo'lishi mumkin).
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    """Har yozuvni bitta JSON qatoriga aylantiradi (qo'shimcha `extra` maydonlar bilan)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        # `logger.info("...", extra={"foo": 1})` orqali kelgan qo'shimcha maydonlar.
        for k, v in record.__dict__.items():
            if k not in _RESERVED and k not in payload and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # default=str — serializatsiya bo'lmaydigan obyektlar (masalan uvicorn'ning
        # WebSocketProtocol'i) xato tug'dirmasdan str'ga aylanadi (logging crash bo'lmaydi).
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Inson o'qishiga qulay lokal format (request_id bilan)."""

    def __init__(self):
        super().__init__("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s",
                         datefmt="%H:%M:%S")


_configured = False


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Root logger'ni bir marta sozlaydi (idempotent)."""
    global _configured
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, (level or "INFO").upper(), logging.INFO))
    # uvicorn'ning o'z handlerlari bizning formatdan o'tsin.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    _configured = True
