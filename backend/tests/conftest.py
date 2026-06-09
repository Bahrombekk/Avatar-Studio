"""Pytest fixtures — yengil muhit (torch'siz) uchun izolyatsiyalangan sozlash.

DIQQAT: env o'zgaruvchilari `app.*` import qilinishidan OLDIN o'rnatilishi shart
(paths.py DATA_DIR/TEMP_DIR ni import paytida o'qiydi). Shuning uchun ular shu
modulning YUQORISIDA (har qanday app importidan oldin) o'rnatiladi.
"""
import os
import tempfile

# ── 1. Test izolyatsiyasi uchun env (har qanday app importidan OLDIN) ──
_TMP_ROOT = tempfile.mkdtemp(prefix="avatar_studio_test_")
os.environ.setdefault("DATA_DIR", os.path.join(_TMP_ROOT, "data"))
os.environ.setdefault("TEMP_DIR", os.path.join(_TMP_ROOT, "tmp"))
os.environ.setdefault("VID_OUT_DIR", os.path.join(_TMP_ROOT, "vid"))
os.environ["AVATAR_STUDIO_SKIP_WARMUP"] = "1"
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ["ADMIN_PASSWORD"] = "test-pw"          # auth testlari determinizmi uchun
os.environ.setdefault("LOG_FORMAT", "text")

import pytest                                       # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402


@pytest.fixture(scope="session")
def app():
    from app.main import create_app
    return create_app()


@pytest.fixture()
def client(app):
    # `with` lifespan'ni ishga tushiradi (warmup flag bilan o'tkazib yuboriladi).
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_headers():
    from app.core.auth import admin_token
    return {"Authorization": f"Bearer {admin_token()}"}
