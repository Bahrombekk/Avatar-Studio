"""Markaziy sozlamalar va .env yuklash.

Ikki sath:
  1. `load_env_var(name)` / `openai_api_key()` — eski, oddiy interfeys (shell env afzal,
     bo'lmasa .env faylidan). Mavjud call-site'lar (auth, tts, stt, system) buni ishlatadi.
  2. `Settings` (pydantic-settings) — yangi, TIPLI va VALIDATSIYALI surface. Yangi kod
     (`get_settings()`) buni ishlatadi; validatsiya (masalan CANNED_* chegaralari,
     standart "admin" paroli ogohlantirishi) shu yerda.
"""
import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BACKEND_DIR / ".env"

log = logging.getLogger(__name__)


def load_env_var(name: str) -> str:
    """Muhit o'zgaruvchisini o'qish; bo'lmasa .env faylidan (eski interfeys)."""
    val = os.environ.get(name, "").strip()
    if val:
        return val
    if ENV_FILE.exists():
        prefix = f"{name}="
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(prefix):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ[name] = val
                return val
    return ""


def openai_api_key() -> str:
    return load_env_var("OPENAI_API_KEY")


class Settings(BaseSettings):
    """Tipli, validatsiyali sozlamalar — yangi kod uchun yagona manba.

    Shell env'dan, so'ng `.env` faylidan o'qiydi (shell afzal — pydantic-settings
    standart xatti-harakati). Noma'lum kalitlar e'tiborsiz qoldiriladi (`extra=ignore`),
    chunki .env'da ML knob'lar (RT_*, MT_BATCH, ...) ham bo'lishi mumkin.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8",
        extra="ignore", case_sensitive=True,
    )

    # ── Tashqi xizmat kalitlari ──
    OPENAI_API_KEY: str = ""
    YX_API_KEY: str = ""
    YX_IAM_TOKEN: str = ""
    YX_FOLDER_ID: str = ""
    YX_SPEECH_TO_SPEECH_KEY: str = ""

    # ── Admin ──
    ADMIN_PASSWORD: str = "admin"
    AUTH_DISABLED: bool = False
    # Joylashtirish muhiti: "local" (standart) | "production". Production'da
    # standart parol yoki AUTH_DISABLED bilan ishga tushishga YO'L QO'YILMAYDI
    # (get_settings() fail-fast). Har tashkilot instansiyasi production'da
    # APP_ENV=production qo'yib, o'z ADMIN_PASSWORD'ini belgilashi shart.
    APP_ENV: str = "local"

    # ── Tayyor javoblar matching chegaralari ──
    CANNED_MATCH_RATIO: float = Field(0.82, ge=0.0, le=1.0)
    CANNED_SEM_THRESHOLD: float = Field(0.58, ge=0.0, le=1.0)

    # ── Retention (cheksiz o'sishning oldini olish) ──
    # Saqlanadigan eng ko'p suhbat soni; eskilari (+xabarlari) avtomatik o'chiriladi.
    CONVERSATIONS_MAX: int = Field(5000, ge=100)

    # ── Server / observability ──
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"          # "json" | "text"
    LOG_FILE: str = ""                # bo'sh → faqat stdout; yo'l berilsa rotating fayl ham
    LOG_MAX_MB: int = Field(10, ge=1)    # bitta log fayl maksimal hajmi (MB)
    LOG_BACKUPS: int = Field(5, ge=0)    # saqlanadigan rotatsiya fayllari soni
    LOG_SLOW_MS: int = Field(0, ge=0)    # >0 → shu ms'dan sekin so'rovlar WARNING bo'ladi
    AVATAR_STUDIO_SKIP_WARMUP: bool = False
    DATA_DIR: str = ""                # bo'sh → paths.py standartini ishlatadi

    @field_validator("LOG_FORMAT")
    @classmethod
    def _check_log_format(cls, v: str) -> str:
        v = (v or "json").lower()
        return v if v in ("json", "text") else "json"

    @property
    def yandex_configured(self) -> bool:
        return bool((self.YX_API_KEY or self.YX_IAM_TOKEN) and self.YX_FOLDER_ID)

    @property
    def is_production(self) -> bool:
        return (self.APP_ENV or "local").lower() in ("production", "prod")

    def security_issues(self) -> list:
        """Production'da ruxsat etilmaydigan xavfsiz-mas konfiguratsiyalar ro'yxati.
        Local'da har doim bo'sh (faqat yumshoq warning beriladi)."""
        if not self.is_production:
            return []
        issues = []
        if self.ADMIN_PASSWORD == "admin":
            issues.append(
                "ADMIN_PASSWORD production'da standart 'admin' — .env'da kuchli parol qo'ying."
            )
        if self.AUTH_DISABLED:
            issues.append(
                "AUTH_DISABLED production'da yoqilgan — bu butun admin himoyasini o'chiradi."
            )
        return issues


@lru_cache
def get_settings() -> Settings:
    """Keshlangan Settings (jarayon davomida bir marta o'qiladi).

    Testlarda env o'zgartirilgach `get_settings.cache_clear()` chaqiring.
    """
    s = Settings()
    issues = s.security_issues()
    if issues:
        # Production + xavfsiz-mas config → ishga tushirishni TO'XTATAMIZ.
        for m in issues:
            log.error("XAVFSIZLIK: %s", m)
        raise RuntimeError("Production xavfsizlik konfiguratsiyasi xato: " + "; ".join(issues))
    if s.ADMIN_PASSWORD == "admin" and not s.AUTH_DISABLED:
        log.warning(
            "ADMIN_PASSWORD standart 'admin' qiymatida — .env'da o'zgartiring "
            "(yoki sof lokal uchun AUTH_DISABLED=1). Production'da APP_ENV=production "
            "bo'lsa ishga tushish bloklanadi."
        )
    return s
