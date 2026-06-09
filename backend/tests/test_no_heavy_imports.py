"""Regressiya tutqichi: `app.main` import qilish og'ir ML modullarini tortmasligi shart.

Bu test yengil deps muhitida (torch/cv2/insightface o'rnatilmagan) ham, ular
o'rnatilgan muhitda ham ishlaydi — gap import PAYTIDA ular YUKLANMASLIGIDA.
"""
import sys


def test_create_app_does_not_import_heavy():
    # Toza holatdan boshlash uchun, agar test ketma-ketligida kimdir import qilgan bo'lsa
    # ham, bu test create_app() ning O'ZI tortmasligini tekshiradi.
    before = set(sys.modules)
    from app.main import create_app
    create_app()
    heavy = {"torch", "cv2", "insightface", "diffusers", "transformers", "librosa", "grpc"}
    leaked = heavy & set(sys.modules)
    # Faqat create_app() import qilingandan keyin paydo bo'lganlarini tekshiramiz —
    # agar boshqa test allaqachon import qilgan bo'lsa, bu testni o'tkazib yuboramiz.
    newly = leaked - before
    assert not newly, f"create_app() og'ir modullarni import qildi: {newly}"
