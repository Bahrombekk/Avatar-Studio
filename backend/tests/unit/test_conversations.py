"""Suhbat saqlash (SQLite) — yozish, ro'yxat, o'qish."""
from app.services import conversations


def test_record_and_list_and_get():
    key = "sess_test_1"
    conversations.record_message(key, "user", "Salom", avatar_id="av_x", request_id="r1")
    conversations.record_message(key, "assistant", "Assalomu alaykum", avatar_id="av_x")
    convs = conversations.list_conversations()
    mine = [c for c in convs if c["session_key"] == key]
    assert mine and mine[0]["msg_count"] == 2
    assert mine[0]["last_text"] == "Assalomu alaykum"

    detail = conversations.get_conversation(mine[0]["id"])
    assert detail["conversation"]["session_key"] == key
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]
    assert detail["messages"][0]["request_id"] == "r1"


def test_empty_and_missing():
    # Bo'sh matn / kalit yo'q → yozilmaydi (xato emas).
    conversations.record_message("", "user", "x")
    conversations.record_message("k", "user", "   ")
    assert conversations.get_conversation(999999) == {}


def test_second_message_reuses_conversation():
    key = "sess_test_2"
    conversations.record_message(key, "user", "birinchi")
    conversations.record_message(key, "user", "ikkinchi")
    mine = [c for c in conversations.list_conversations() if c["session_key"] == key]
    assert len(mine) == 1 and mine[0]["msg_count"] == 2


def test_prune_keeps_newest(monkeypatch):
    # 6 ta alohida suhbat yozamiz, keyin eng yangi 3 tasini saqlaymiz.
    for i in range(6):
        conversations.record_message(f"prune_sess_{i}", "user", f"xabar {i}")
    removed = conversations.prune(max_keep=3)
    assert removed >= 3
    remaining = conversations.list_conversations(limit=500)
    keys = {c["session_key"] for c in remaining}
    # Eng yangilari (5,4,3) qoladi; eng eskilari (0,1,2) o'chadi.
    assert "prune_sess_5" in keys
    assert "prune_sess_0" not in keys
    assert len(remaining) <= 3


def test_prune_removes_orphan_messages(monkeypatch):
    conversations.record_message("orphan_a", "user", "salom")
    conv = [c for c in conversations.list_conversations(limit=500)
            if c["session_key"] == "orphan_a"][0]
    conversations.prune(max_keep=0)             # hammasini o'chiramiz
    # O'chirilgan suhbatning xabarlari ham yo'qolgan bo'lishi kerak.
    assert conversations.get_conversation(conv["id"]) == {}


def test_auto_prune_on_new_conversation(monkeypatch):
    monkeypatch.setattr(conversations, "_max_conversations", lambda: 2)
    for i in range(5):
        conversations.record_message(f"auto_{i}", "user", "x")
    # Yangi suhbat har yaratilganda _prune ishlaydi → 2 tadan oshmaydi.
    assert len(conversations.list_conversations(limit=500)) <= 2
