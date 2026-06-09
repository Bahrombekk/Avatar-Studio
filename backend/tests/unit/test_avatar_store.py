"""Avatar do'koni (CRUD) + analitika + event log."""
from app.services import avatar_store


def test_seed_and_list():
    avs = avatar_store.list_avatars()
    ids = {a["id"] for a in avs}
    assert "madina_lp" in ids and "sardor_bank" in ids


def test_create_update_delete():
    a = avatar_store.create_avatar({"name": "Test Bot"})
    aid = a["id"]
    assert aid.startswith("av_")
    assert a["real"] is False                      # yangi avatar → preprocessing kerak
    upd = avatar_store.update_avatar(aid, {"role": "Yordamchi"})
    assert upd["role"] == "Yordamchi"
    assert upd["real"] is False                    # update real'ni saqlaydi
    assert avatar_store.delete_avatar(aid) is True
    assert avatar_store.get_avatar(aid) is None


def test_log_event_and_stats():
    a = avatar_store.create_avatar({"name": "Stat Bot"})
    aid = a["id"]
    avatar_store.log_event(aid, "savol", cached=False, gpt=0.5, tts=0.6, video=1.0,
                           total=2.1, request_id="rid1", session_id="sid1")
    fresh = avatar_store.get_avatar(aid)
    assert fresh["sessions"] == 1
    assert fresh["avgLatency"] == 2.1
    # events.jsonl ga request_id/session_id yozildi
    events = avatar_store._read_events_for(aid)
    assert events and events[-1]["request_id"] == "rid1" and events[-1]["session_id"] == "sid1"
    avatar_store.delete_avatar(aid)


def test_analytics_demo_when_no_events():
    # Yangi (event'siz) avatarlar bo'lsa demo qaytadi yoki hisoblangan — kalitlar bor.
    data = avatar_store.analytics()
    assert "totals" in data and "latencyBreakdown" in data and "daily" in data
