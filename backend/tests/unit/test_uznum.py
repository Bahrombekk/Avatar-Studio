"""O'zbekcha TTS normalizatori testlari (son/narx/sana/vaqt/klass → so'z)."""
from app.services.uznum import num_to_uz, normalize_uz_tts as n


def test_num_to_uz():
    assert num_to_uz(0) == "nol"
    assert num_to_uz(5) == "besh"
    assert num_to_uz(311000) == "uch yuz o'n bir ming"
    assert num_to_uz(300560) == "uch yuz ming besh yuz oltmish"
    assert num_to_uz(2026) == "ikki ming yigirma olti"


def test_prices():
    assert "uch yuz o'n bir ming" in n("311000 so'm")
    assert "uch yuz ming besh yuz oltmish" in n("300 560 so'm")


def test_seat_class():
    assert n("1С") == "bir si"          # kiril С
    assert n("2В") == "ikki ve"          # kiril В
    assert n("1C") == "bir si"           # lotin C


def test_dates():
    assert n("10.06.2026") == "o'ninchi iyun"
    assert n("25.06.2026") == "yigirma beshinchi iyun"
    assert n("2026-07-21") == "yigirma birinchi iyul"


def test_time():
    assert n("08:00") == "soat sakkiz"
    assert "soat o'n olti" in n("16:30")


def test_plain_text_unchanged():
    assert n("Salom dunyo") == "Salom dunyo"
    assert n("") == ""
