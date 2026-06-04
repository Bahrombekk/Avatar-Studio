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


# ── LLM provayder (gpt javob generatsiyasi) ──
# Standart: lokal Ollama (DGX'da ishlaydi, tarmoq kechikishi yo'q, tekin).
# `LLM_PROVIDER=openai` qilib OpenAI'ga qaytish mumkin (fallback / A-B test).
def llm_provider() -> str:
    return (load_env_var("LLM_PROVIDER") or "ollama").strip().lower()


def ollama_base_url() -> str:
    """Ollama OpenAI-mos endpoint (/v1). Standart: lokal."""
    return load_env_var("OLLAMA_BASE_URL") or "http://127.0.0.1:11434/v1"


def ollama_model() -> str:
    return load_env_var("OLLAMA_MODEL") or "qwen3:8b"


def llm_keep_alive() -> str:
    """Model GPU'da qancha rezident qolsin (sovuq yuklanish ~2.5s'ni oldini oladi)."""
    return load_env_var("LLM_KEEP_ALIVE") or "30m"
