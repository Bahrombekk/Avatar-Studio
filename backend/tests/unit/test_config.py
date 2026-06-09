"""Settings (pydantic-settings) validatsiya va yuklash."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings, load_env_var


def test_defaults(monkeypatch):
    # .env va conftest env ta'sirini kamaytirish — standartlarni tekshiramiz.
    monkeypatch.delenv("CANNED_MATCH_RATIO", raising=False)
    monkeypatch.delenv("CANNED_SEM_THRESHOLD", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    s = Settings(_env_file=None)
    assert s.CANNED_MATCH_RATIO == 0.82
    assert s.CANNED_SEM_THRESHOLD == 0.58
    assert s.LOG_FORMAT == "json"


def test_canned_ratio_out_of_range(monkeypatch):
    monkeypatch.setenv("CANNED_MATCH_RATIO", "2.0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_log_format_normalized(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "PLAIN")     # noma'lum → json'ga tushadi
    assert Settings(_env_file=None).LOG_FORMAT == "json"


def test_yandex_configured(monkeypatch):
    monkeypatch.setenv("YX_API_KEY", "k")
    monkeypatch.setenv("YX_FOLDER_ID", "f")
    assert Settings(_env_file=None).yandex_configured is True
    monkeypatch.delenv("YX_FOLDER_ID", raising=False)
    assert Settings(_env_file=None).yandex_configured is False


def test_load_env_var_precedence(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "shell-value")
    assert load_env_var("OPENAI_API_KEY") == "shell-value"


def test_local_default_no_security_issues(monkeypatch):
    # Local (standart) muhitda standart parol — faqat yumshoq holat, blok yo'q.
    monkeypatch.delenv("APP_ENV", raising=False)
    s = Settings(_env_file=None, ADMIN_PASSWORD="admin")
    assert s.is_production is False
    assert s.security_issues() == []


def test_production_default_password_blocked(monkeypatch):
    s = Settings(_env_file=None, APP_ENV="production", ADMIN_PASSWORD="admin")
    assert s.is_production is True
    issues = s.security_issues()
    assert any("ADMIN_PASSWORD" in m for m in issues)


def test_production_auth_disabled_blocked(monkeypatch):
    s = Settings(_env_file=None, APP_ENV="production",
                 ADMIN_PASSWORD="strong-pw", AUTH_DISABLED=True)
    issues = s.security_issues()
    assert any("AUTH_DISABLED" in m for m in issues)


def test_production_strong_password_ok(monkeypatch):
    s = Settings(_env_file=None, APP_ENV="prod", ADMIN_PASSWORD="strong-pw")
    assert s.security_issues() == []


def test_get_settings_raises_in_insecure_production(monkeypatch):
    import app.core.config as cfg
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin")
    cfg.get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        cfg.get_settings()
    cfg.get_settings.cache_clear()      # boshqa testlarga sof holat qoldiramiz
