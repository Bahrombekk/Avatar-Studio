"""Railway natija keshi — brauzerga (Playwright) har savol bormaydi.

`_call` (brauzer worker) mock qilinadi, shuning uchun bu testlar GPU/brauzersiz ishlaydi.
"""
from app.services import railway


def setup_function():
    railway.clear_cache()


def _stations_payload(code="2900000", name="TOSHKENT"):
    return {"data": {"stations": [{"code": code, "name": name}]}}


def _trains_payload(trains):
    return {"data": {"directions": {"forward": {"trains": trains}}}}


def test_resolve_station_caches(monkeypatch):
    calls = {"n": 0}

    def fake_call(kind, *args, **kw):
        calls["n"] += 1
        return _stations_payload()

    monkeypatch.setattr(railway, "_call", fake_call)
    r1 = railway.resolve_station("Toshkent")
    r2 = railway.resolve_station("toshkent")        # katta-kichik harf farqi — bir kalit
    assert r1 == r2 == {"code": "2900000", "name": "TOSHKENT"}
    assert calls["n"] == 1                           # ikkinchisi keshdan


def test_resolve_station_miss_not_cached(monkeypatch):
    calls = {"n": 0}

    def fake_call(kind, *args, **kw):
        calls["n"] += 1
        return {"data": {"stations": []}}            # topilmadi

    monkeypatch.setattr(railway, "_call", fake_call)
    assert railway.resolve_station("yo'q-shahar") is None
    assert railway.resolve_station("yo'q-shahar") is None
    assert calls["n"] == 2                           # topilmagani keshlanmadi → qayta urindi


def test_search_trains_caches(monkeypatch):
    calls = {"n": 0}

    def fake_call(kind, *args, **kw):
        calls["n"] += 1
        return _trains_payload([{"number": "010F", "brand": "Afrosiyob"}])

    monkeypatch.setattr(railway, "_call", fake_call)
    t1 = railway.search_trains("2900000", "2900700", "2026-06-10")
    t2 = railway.search_trains("2900000", "2900700", "2026-06-10")
    assert t1 == t2 and len(t1) == 1
    assert calls["n"] == 1


def test_search_trains_transient_error_not_cached(monkeypatch):
    calls = {"n": 0}

    def fake_call(kind, *args, **kw):
        calls["n"] += 1
        return None                                   # transient (timeout/xato)

    monkeypatch.setattr(railway, "_call", fake_call)
    assert railway.search_trains("a", "b", "d") == []
    assert railway.search_trains("a", "b", "d") == []
    assert calls["n"] == 2                            # keshlanmadi


def test_search_ttl_expiry(monkeypatch):
    monkeypatch.setattr(railway, "_SEARCH_TTL", 0)    # darhol eskiradi
    calls = {"n": 0}

    def fake_call(kind, *args, **kw):
        calls["n"] += 1
        return _trains_payload([{"number": "1"}])

    monkeypatch.setattr(railway, "_call", fake_call)
    railway.search_trains("a", "b", "d")
    railway.search_trains("a", "b", "d")
    assert calls["n"] == 2                            # TTL=0 → har safar yangi


def test_clear_cache(monkeypatch):
    monkeypatch.setattr(railway, "_call", lambda *a, **k: _stations_payload())
    railway.resolve_station("Toshkent")
    assert railway._station_cache
    railway.clear_cache()
    assert not railway._station_cache and not railway._search_cache


def test_looks_like_train_query():
    assert railway.looks_like_train_query("Toshkentdan Samarqandga chipta narxi")
    assert railway.looks_like_train_query("poyezd jadvali")
    assert not railway.looks_like_train_query("bugun ob-havo qanday")
