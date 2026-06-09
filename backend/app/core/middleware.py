"""Request-ID middleware + process-level metrikalar registri.

Har HTTP so'rovga `X-Request-ID` beriladi (kiruvchi header yoki yangi uuid),
contextvar'ga yoziladi (loglar bog'lanishi uchun) va javob header'iga qaytariladi.
Har so'rov bitta strukturali access-log qatori chiqaradi va metrikalarni yangilaydi.
`/metrics` endpointi shu registr'dan o'qiydi.
"""
import logging
import time
import uuid
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import request_id_ctx

log = logging.getLogger("app.access")


class _Metrics:
    """Yengil in-process metrikalar (stdlib; tashqi bog'liqlik yo'q)."""

    def __init__(self, window: int = 1000):
        self.total = 0
        self.errors = 0           # 5xx javoblar
        self.client_errors = 0    # 4xx javoblar
        self._lat = deque(maxlen=window)   # so'nggi N so'rov latency (ms)
        self._started = time.time()

    def record(self, status: int, dur_ms: float) -> None:
        self.total += 1
        if status >= 500:
            self.errors += 1
        elif status >= 400:
            self.client_errors += 1
        self._lat.append(dur_ms)

    def _pct(self, p: float) -> float:
        if not self._lat:
            return 0.0
        s = sorted(self._lat)
        i = min(len(s) - 1, int(round(p * (len(s) - 1))))
        return round(s[i], 1)

    def snapshot(self) -> dict:
        return {
            "requests_total": self.total,
            "errors_5xx": self.errors,
            "errors_4xx": self.client_errors,
            "latency_ms": {"p50": self._pct(0.5), "p95": self._pct(0.95),
                           "p99": self._pct(0.99), "samples": len(self._lat)},
            "uptime_s": round(time.time() - self._started, 1),
        }


metrics = _Metrics()


def _slow_ms() -> int:
    """Sekin-so'rov chegarasi (ms). 0 → o'chiq. config'dan o'qiladi."""
    try:
        from app.core.config import get_settings
        return int(get_settings().LOG_SLOW_MS)
    except Exception:  # noqa: BLE001
        return 0


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)
        t0 = time.time()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            dur_ms = (time.time() - t0) * 1000.0
            metrics.record(status, dur_ms)
            path = request.url.path
            # /videos, /assets kabi statik/oqim so'rovlari shovqin qilmasin —
            # faqat API yo'llari va xatolarni access-log qilamiz.
            noisy = path.startswith(("/assets", "/videos")) or path in ("/idle.jpg",)
            slow_ms = _slow_ms()
            is_slow = slow_ms > 0 and dur_ms >= slow_ms
            if not noisy or status >= 400 or is_slow:
                extra = {"method": request.method, "path": path,
                         "status": status, "dur_ms": round(dur_ms, 1)}
                if is_slow:
                    # Sekin so'rov → WARNING + slow bayrog'i (agregatorda oson filtrlanadi).
                    extra["slow"] = True
                    log.warning("SEKIN %s %s -> %d (%.0fms ≥ %dms)",
                                request.method, path, status, dur_ms, slow_ms, extra=extra)
                else:
                    log.info("%s %s -> %d", request.method, path, status, extra=extra)
            request_id_ctx.reset(token)
