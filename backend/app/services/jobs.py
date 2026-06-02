"""Oddiy in-process fon job menejeri — uzoq generatsiya bosqichlari uchun.

Avatar yaratishda idle generatsiya (LivePortrait) va MuseTalk preprocessing uzoq
davom etadi. Ularni so'rov ichida kutib turmasdan, fon thread'ida ishga tushiramiz
va holatni avatar config'idagi `build` maydoniga yozamiz (avatar_store.set_build).
Frontend `GET /api/avatars/{id}` orqali shu holatni polling qiladi.

Bir avatar uchun bir vaqtda faqat BITTA job — dublikat ishga tushirish bloklanadi.
Bu modul step 3 (idle) va step 4 (musetalk) tomonidan birgalikda ishlatiladi.
"""
import threading

from app.services import avatar_store

_jobs = {}            # avatar_id -> threading.Thread
_lock = threading.Lock()


def is_running(avatar_id: str) -> bool:
    with _lock:
        th = _jobs.get(avatar_id)
        return bool(th and th.is_alive())


def start(avatar_id: str, stage: str, fn) -> bool:
    """fn() ni fon thread'ida ishga tushiradi.

    Holat o'tishlari avatar config'iga yoziladi:
        boshlanishda → build.state = "processing"
        muvaffaqiyat → "done"
        istisno      → "error" (error matni bilan)

    Allaqachon shu avatar uchun job ishlayotgan bo'lsa → False (boshlanmaydi).
    """
    with _lock:
        if avatar_id in _jobs and _jobs[avatar_id].is_alive():
            return False

        avatar_store.set_build(avatar_id, "processing", stage=stage)

        def worker():
            try:
                fn()
                avatar_store.set_build(avatar_id, "done", stage=stage)
            except Exception as e:  # noqa: BLE001 — har qanday xato build.error ga
                avatar_store.set_build(avatar_id, "error", stage=stage, error=str(e))
            finally:
                with _lock:
                    _jobs.pop(avatar_id, None)

        th = threading.Thread(target=worker, daemon=True, name=f"job-{avatar_id}-{stage}")
        _jobs[avatar_id] = th
        th.start()
        return True
