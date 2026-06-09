"""ResponseCache + matn normalizatsiya + 'qayta ayt' aniqlash testlari."""
from app.services import cache


def test_normalize_basic():
    assert cache._normalize("  Salom!!  Dunyo  ") == "salom dunyo"
    # Backtick/modifier-apostrof → to'g'ri apostrof; punktuatsiya olib tashlanadi.
    assert cache._normalize("O`zbekiston, poyezd?") == "o'zbekiston poyezd"


def test_is_repeat_request():
    assert cache.is_repeat_request("qayta ayting")
    assert cache.is_repeat_request("eshitmadim")
    assert not cache.is_repeat_request(
        "Toshkentdan Samarqandga poyezd chiptasi narxi qancha bo'ladi bugun"
    )
    assert not cache.is_repeat_request("")


def test_cache_add_and_exact_match(tmp_path):
    c = cache.ResponseCache(scope="av_test", voice="madina")
    # Manba video fayli (tmp) — add() uni kesh papkasiga KO'CHIRADI.
    src = tmp_path / "src.mp4"
    src.write_bytes(b"FAKEMP4")
    entry = c.add(query="Salom", response="Assalomu alaykum", video_src_path=str(src))
    assert entry is not None
    assert not src.exists()                      # ko'chirildi (nusxa emas)
    hit = c.exact_match("salom")                 # normalizatsiya bilan mos
    assert hit is not None and hit["id"] == entry["id"]
    assert c.exact_match("boshqa savol") is None


def test_cache_repeat_and_clear(tmp_path):
    c = cache.ResponseCache(scope="av_test2", voice="madina")
    src = tmp_path / "s2.mp4"; src.write_bytes(b"X")
    c.add(query="Narx qancha", response="100 so'm", video_src_path=str(src))
    assert c.get_last_entry()["response"] == "100 so'm"
    st = c.stats()
    assert st["total_entries"] == 1
    assert c.clear() == 1
    assert c.stats()["total_entries"] == 0
