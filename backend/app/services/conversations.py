"""Suhbat tarixini saqlash — SQLite (stdlib). RAM tarixi tezlik uchun qoladi,
DB esa doimiy manba (server o'chsa ham yo'qolmaydi; ConversationsPage ko'rsatadi).

Saqlash: data/conversations.db
  conversations(id, session_key UNIQUE, avatar_id, started, updated, msg_count, last_text)
  messages(id, conv_id, role, text, ts, request_id)

session_key — gpt.py history_key (realtime: session_id; admin chat: avatar_id).
Yozish xatolari hech qachon suhbatni buzmaydi (yutiladi).
"""
import logging
import sqlite3
import threading
from datetime import datetime, timezone

log = logging.getLogger(__name__)
_lock = threading.Lock()
_initialized = False


def _db_file():
    from app.core.paths import DATA_DIR
    return DATA_DIR / "conversations.db"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _conn():
    DATA_DIR_FILE = _db_file()
    DATA_DIR_FILE.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DATA_DIR_FILE), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _ensure_init():
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        with _conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_key TEXT UNIQUE,
                    avatar_id TEXT,
                    started TEXT,
                    updated TEXT,
                    msg_count INTEGER DEFAULT 0,
                    last_text TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conv_id INTEGER,
                    role TEXT,
                    text TEXT,
                    ts TEXT,
                    request_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conv_id);
                """
            )
        _initialized = True


def record_message(session_key, role: str, text: str, avatar_id=None, request_id=None) -> None:
    """Bitta xabarni saqlaydi (suhbat yo'q bo'lsa yaratadi). Xato → yutiladi."""
    if not session_key or not (text or "").strip():
        return
    try:
        _ensure_init()
        now = _now()
        with _lock, _conn() as c:
            row = c.execute("SELECT id FROM conversations WHERE session_key = ?",
                            (session_key,)).fetchone()
            if row is None:
                cur = c.execute(
                    "INSERT INTO conversations (session_key, avatar_id, started, updated, msg_count) "
                    "VALUES (?, ?, ?, ?, 0)",
                    (session_key, avatar_id, now, now),
                )
                conv_id = cur.lastrowid
                _prune(c)                  # yangi suhbat → eskilarini chegaraga moslaymiz
            else:
                conv_id = row["id"]
            c.execute(
                "INSERT INTO messages (conv_id, role, text, ts, request_id) VALUES (?, ?, ?, ?, ?)",
                (conv_id, role, text, now, request_id),
            )
            c.execute(
                "UPDATE conversations SET updated = ?, msg_count = msg_count + 1, last_text = ? "
                "WHERE id = ?",
                (now, text[:200], conv_id),
            )
    except Exception as e:  # noqa: BLE001
        log.warning("[conversations] yozish xato: %s", e)


def _max_conversations() -> int:
    """Saqlanadigan eng ko'p suhbat soni (config'dan; xato bo'lsa 5000)."""
    try:
        from app.core.config import get_settings
        return int(get_settings().CONVERSATIONS_MAX)
    except Exception:  # noqa: BLE001
        return 5000


def _prune(c, max_keep: int = None) -> int:
    """Eng yangi `max_keep` suhbatdan tashqarisini (va ularning xabarlarini) o'chiradi.
    Ochiq ulanish (c) ichida ishlaydi. O'chirilgan suhbat sonini qaytaradi."""
    keep = max_keep if max_keep is not None else _max_conversations()
    total = c.execute("SELECT COUNT(*) AS n FROM conversations").fetchone()["n"]
    if total <= keep:
        return 0
    # `updated` bo'yicha eng yangi `keep` tadan keyingilarini tanlaymiz.
    old_ids = [r["id"] for r in c.execute(
        "SELECT id FROM conversations ORDER BY updated DESC, id DESC LIMIT -1 OFFSET ?",
        (keep,),
    ).fetchall()]
    if not old_ids:
        return 0
    qs = ",".join("?" * len(old_ids))
    c.execute(f"DELETE FROM messages WHERE conv_id IN ({qs})", old_ids)
    c.execute(f"DELETE FROM conversations WHERE id IN ({qs})", old_ids)
    return len(old_ids)


def prune(max_keep: int = None) -> int:
    """Tashqi/qo'lda chaqirish uchun retention (yangi ulanish ochadi)."""
    try:
        _ensure_init()
        with _lock, _conn() as c:
            return _prune(c, max_keep)
    except Exception as e:  # noqa: BLE001
        log.warning("[conversations] prune xato: %s", e)
        return 0


def list_conversations(limit: int = 100) -> list:
    try:
        _ensure_init()
        with _conn() as c:
            rows = c.execute(
                "SELECT id, session_key, avatar_id, started, updated, msg_count, last_text "
                "FROM conversations ORDER BY updated DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001
        log.warning("[conversations] ro'yxat xato: %s", e)
        return []


def get_conversation(conv_id: int) -> dict:
    try:
        _ensure_init()
        with _conn() as c:
            conv = c.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if conv is None:
                return {}
            msgs = c.execute(
                "SELECT role, text, ts, request_id FROM messages WHERE conv_id = ? ORDER BY id",
                (conv_id,),
            ).fetchall()
        return {"conversation": dict(conv), "messages": [dict(m) for m in msgs]}
    except Exception as e:  # noqa: BLE001
        log.warning("[conversations] o'qish xato: %s", e)
        return {}
