"""Avatar yaratish / yangilash sxemalari + validatsiya.

Server boshqaradigan maydonlar (id, real, sessions, avgLatency, cacheRate,
csat, updated) bu yerda YO'Q — ularni avatar_store o'rnatadi. Klient faqat
konfiguratsiya yuboradi.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.tts import VOICES, DEFAULT_VOICE

_VOICE_IDS = set(VOICES.keys())


class Portrait(BaseModel):
    # "from" — Python kalit so'zi, shuning uchun alias bilan.
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field("#1C3A5E", alias="from", pattern=r"^#[0-9A-Fa-f]{6}$")
    to: str = Field("#0F2540", pattern=r"^#[0-9A-Fa-f]{6}$")
    initials: str = Field("A", min_length=1, max_length=2)


class AvatarCreate(BaseModel):
    """Yangi avatar uchun to'liq, validatsiyalangan konfiguratsiya."""
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=60)
    role: str = Field("Virtual yordamchi", max_length=80)
    brand: str = Field("", max_length=80)
    brandShort: str = Field("", max_length=5)
    status: Literal["live", "draft", "paused"] = "draft"
    accent: str = Field("#B98944", pattern=r"^#[0-9A-Fa-f]{6}$")
    portrait: Portrait = Field(default_factory=Portrait)

    voice: str = DEFAULT_VOICE
    language: Literal["uz", "ru", "en"] = "uz"

    persona: str = Field("", max_length=4000)
    respLen: Literal["short", "medium", "long"] = "short"
    temperature: float = Field(0.4, ge=0.0, le=1.0)
    speechRate: int = Field(0, ge=-30, le=30)

    fps: Literal[20, 25, 30] = 25
    blinkRate: int = Field(4, ge=2, le=8)
    headMotion: float = Field(0.45, ge=0.0, le=1.0)
    extraMargin: int = Field(16, ge=0, le=32)
    # Build rezolyutsiyasi: 1280 = 720p (tez, real-time), 1920 = 1080p (sifat, Studio).
    maxDim: Literal[1280, 1920] = 1280

    hasPhoto: bool = False
    suggestions: List[str] = Field(default_factory=list)

    @field_validator("voice")
    @classmethod
    def _voice_known(cls, v: str) -> str:
        if v not in _VOICE_IDS:
            raise ValueError(f"Noma'lum ovoz '{v}'. Mavjud: {sorted(_VOICE_IDS)}")
        return v

    @field_validator("suggestions")
    @classmethod
    def _clean_suggestions(cls, v: List[str]) -> List[str]:
        # Bo'sh tavsiyalarni tashlab, 6 tagacha cheklash.
        cleaned = [s.strip() for s in v if s and s.strip()]
        return cleaned[:6]


class AvatarUpdate(BaseModel):
    """Qisman yangilash — barcha maydon ixtiyoriy. Faqat berilganlar o'zgaradi."""
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, min_length=1, max_length=60)
    role: Optional[str] = Field(None, max_length=80)
    brand: Optional[str] = Field(None, max_length=80)
    brandShort: Optional[str] = Field(None, max_length=5)
    status: Optional[Literal["live", "draft", "paused"]] = None
    accent: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    portrait: Optional[Portrait] = None

    voice: Optional[str] = None
    language: Optional[Literal["uz", "ru", "en"]] = None

    persona: Optional[str] = Field(None, max_length=4000)
    respLen: Optional[Literal["short", "medium", "long"]] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    speechRate: Optional[int] = Field(None, ge=-30, le=30)

    fps: Optional[Literal[20, 25, 30]] = None
    blinkRate: Optional[int] = Field(None, ge=2, le=8)
    headMotion: Optional[float] = Field(None, ge=0.0, le=1.0)
    extraMargin: Optional[int] = Field(None, ge=0, le=32)
    maxDim: Optional[Literal[1280, 1920]] = None

    hasPhoto: Optional[bool] = None
    suggestions: Optional[List[str]] = None

    @field_validator("voice")
    @classmethod
    def _voice_known(cls, v):
        if v is not None and v not in _VOICE_IDS:
            raise ValueError(f"Noma'lum ovoz '{v}'. Mavjud: {sorted(_VOICE_IDS)}")
        return v

    @field_validator("suggestions")
    @classmethod
    def _clean_suggestions(cls, v):
        if v is None:
            return v
        cleaned = [s.strip() for s in v if s and s.strip()]
        return cleaned[:6]
