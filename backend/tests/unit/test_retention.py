"""RAM/disk cheksiz o'sishining oldini olish: gpt sessiya tarixi LRU + events rotatsiya."""
from app.services import gpt, avatar_store


def test_history_session_lru_eviction(monkeypatch):
    gpt._histories.clear()
    monkeypatch.setattr(gpt, "_HIST_MAX_SESSIONS", 3)
    for i in range(5):
        h = gpt._history_for(f"sess_{i}")
        h.append({"role": "user", "content": f"x{i}"})
    assert len(gpt._histories) <= 3
    # Eng yangilari qoladi, eng eskilari (sess_0, sess_1) chiqib ketadi.
    assert "sess_4" in gpt._histories
    assert "sess_0" not in gpt._histories


def test_history_access_refreshes_lru(monkeypatch):
    gpt._histories.clear()
    monkeypatch.setattr(gpt, "_HIST_MAX_SESSIONS", 3)
    for i in range(3):
        gpt._history_for(f"s{i}")
    gpt._history_for("s0")            # s0'ga qayta murojaat → eng yangi bo'ladi
    gpt._history_for("s3")           # yangi kalit → eng eski (s1) chiqadi
    assert "s0" in gpt._histories
    assert "s1" not in gpt._histories


def test_clear_history_removes_key():
    gpt._histories.clear()
    gpt._history_for("to_clear").append({"role": "user", "content": "x"})
    gpt.clear_history("to_clear")
    assert "to_clear" not in gpt._histories


def test_events_rotation_trims_file(monkeypatch):
    # Chegaralarni juda past qilib rotatsiyani majburlaymiz.
    monkeypatch.setattr(avatar_store, "_EVENTS_ROTATE_BYTES", 200)
    monkeypatch.setattr(avatar_store, "_EVENTS_KEEP_LINES", 5)
    aid = "rot_avatar"
    for i in range(40):
        avatar_store.log_event(aid, f"savol {i}", cached=False, total=0.5)
    events = avatar_store._read_events_for(aid)
    assert len(events) <= 5                 # rotatsiya oxirgi qatorlarni saqladi
    # Saqlangan qatorlar — eng yangilari (oxirgisi savol 39).
    assert events[-1]["query"] == "savol 39"
