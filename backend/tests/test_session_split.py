"""Jumla-darajali oqim: split_sentences (app/realtime/session.py) testlari.

Oqim paytida bufer to'liq bo'lmaydi — splitter faqat "tinish + bo'shliq"
chegarasini tan oladi, kasr sonlar ("3.5") va bufer oxiridagi chala jumla
hech qachon bo'linmaydi.
"""
from app.realtime.session import split_sentences


def test_basic_split():
    sents, rest = split_sentences("Salom! Bugun ob-havo yaxshi. Davom etyap")
    assert sents == ["Salom!", "Bugun ob-havo yaxshi."]
    assert rest == "Davom etyap"


def test_no_boundary_keeps_buffer():
    sents, rest = split_sentences("Chipta narxi qancha")
    assert sents == []
    assert rest == "Chipta narxi qancha"


def test_decimal_not_a_boundary():
    # "3.5" ichidagi nuqta — jumla oxiri EMAS (keyin bo'shliq yo'q).
    sents, rest = split_sentences("Narxi 3.5 million so'm")
    assert sents == []
    assert rest == "Narxi 3.5 million so'm"


def test_trailing_punct_without_space_stays():
    # Oqim paytida "...keldi." dan keyin hali bo'shliq kelmagan — bo'linmaydi
    # (keyingi token "5" bo'lishi mumkin, masalan "soat 18." + "30").
    sents, rest = split_sentences("Poyezd keldi.")
    assert sents == []
    assert rest == "Poyezd keldi."


def test_question_and_ellipsis():
    sents, rest = split_sentences("Qachon jo'naydi? Bilmadim… Keyin aytaman")
    assert sents == ["Qachon jo'naydi?", "Bilmadim…"]
    assert rest == "Keyin aytaman"


def test_closing_quote_included():
    sents, rest = split_sentences('U "ha." dedi va ketdi. Tamom')
    assert sents[-1].endswith("ketdi.")
    assert rest == "Tamom"
