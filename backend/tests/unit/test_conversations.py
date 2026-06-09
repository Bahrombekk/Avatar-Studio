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
