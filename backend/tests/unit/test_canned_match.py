"""Tayyor javoblar matching mantiqi (musetalk/render import qilmasdan)."""
from app.services import canned


def _seed(items):
    canned._save(items)


def test_norm_and_clean_questions():
    assert canned._norm("Chipta NARXI??") == "chipta narxi"
    qs = canned._clean_questions(["Salom", "salom", "  ", "Narx?"])
    assert qs == ["Salom", "Narx?"]             # dublikat (normada) tashlandi


def test_match_exact_and_fuzzy():
    _seed([{
        "id": "c1", "avatar_id": "av_x", "state": "done",
        "questions": ["Chipta narxi qancha?", "Narx qancha"],
        "text": "150 ming so'm", "q_emb": [],
    }])
    # Aniq moslik
    assert canned.match("av_x", "Chipta narxi qancha?")["id"] == "c1"
    # Fuzzy/qism moslik (normallashtirilgan)
    assert canned.match("av_x", "chipta narxi qancha") is not None
    # Boshqa avatar → mos emas
    assert canned.match("av_y", "Chipta narxi qancha?") is None


def test_match_unrelated_returns_none():
    _seed([{
        "id": "c2", "avatar_id": "av_x", "state": "done",
        "questions": ["Bagaj qoidalari"], "text": "20 kg", "q_emb": [],
    }])
    # Umuman boshqa savol; semantik yo'l embed_texts'siz (test kalit) → None.
    assert canned.match("av_x", "Bugun ob-havo qanaqa bo'ladi ekan") is None


def test_match_ignores_non_done():
    _seed([{
        "id": "c3", "avatar_id": "av_x", "state": "processing",
        "questions": ["Tayyor emas savol"], "text": "...", "q_emb": [],
    }])
    assert canned.match("av_x", "Tayyor emas savol") is None
