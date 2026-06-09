"""normalize_for_tts keshlash xulqi — bir xil matn GPT'ni qayta chaqirmaydi."""
from app.services import gpt


def _reset_cache():
    with gpt._norm_lock:
        gpt._NORM_CACHE.clear()


def test_normalize_caches_success(monkeypatch):
    _reset_cache()
    calls = {"n": 0}

    def fake_ask_gpt(text, **kw):
        calls["n"] += 1
        return "o'n besh kilometr"

    monkeypatch.setattr(gpt, "ask_gpt", fake_ask_gpt)

    out1 = gpt.normalize_for_tts("15 km", language="uz")
    out2 = gpt.normalize_for_tts("15 km", language="uz")
    assert out1 == out2 == "o'n besh kilometr"
    assert calls["n"] == 1                      # ikkinchi safar keshdan — qayta chaqirilmadi


def test_normalize_failure_not_cached(monkeypatch):
    _reset_cache()
    calls = {"n": 0}

    def boom(text, **kw):
        calls["n"] += 1
        raise RuntimeError("API down")

    monkeypatch.setattr(gpt, "ask_gpt", boom)

    assert gpt.normalize_for_tts("3645", language="uz") == "3645"   # fallback = asl matn
    assert gpt.normalize_for_tts("3645", language="uz") == "3645"
    assert calls["n"] == 2                      # xato keshlanmadi → qayta urindi


def test_normalize_lru_eviction(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(gpt, "ask_gpt", lambda text, **kw: f"norm:{text}")
    monkeypatch.setattr(gpt, "_NORM_CACHE_MAX", 3)

    for i in range(5):
        gpt.normalize_for_tts(f"matn-{i}", language="uz")
    assert len(gpt._NORM_CACHE) <= 3            # kesh chegaradan oshmaydi


def test_normalize_empty_passthrough(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(gpt, "ask_gpt", lambda *a, **k: (_ for _ in ()).throw(AssertionError("chaqirilmasligi kerak")))
    assert gpt.normalize_for_tts("", language="uz") == ""
    assert gpt.normalize_for_tts("   ", language="uz") == ""
