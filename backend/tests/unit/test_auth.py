"""Admin token determinizmi va tekshiruvi."""
from app.core import auth


def test_admin_token_deterministic(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "secret1")
    t1 = auth.admin_token()
    t2 = auth.admin_token()
    assert t1 == t2                          # bir xil parol → bir xil token
    monkeypatch.setenv("ADMIN_PASSWORD", "secret2")
    assert auth.admin_token() != t1          # boshqa parol → boshqa token


def test_verify_token(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-pw")
    good = auth.admin_token()
    assert auth.verify_token(good) is True
    assert auth.verify_token("noto'g'ri") is False
    assert auth.verify_token("") is False
    assert auth.verify_token(None) is False


def test_default_password(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    # config.load_env_var .env'dan o'qishi mumkin; agar yo'q bo'lsa "admin".
    assert auth.admin_password()              # bo'sh emas
