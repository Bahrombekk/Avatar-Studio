"""Markaziy sozlamalar va .env yuklash.

`.env` faylni shell export'siz ham o'qiydi (shell orqali kelgan qiymat afzal).
"""
import os
from pathlib import Path

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BACKEND_DIR / ".env"


def load_env_var(name: str) -> str:
    """Muhit o'zgaruvchisini o'qish; bo'lmasa .env faylidan."""
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
