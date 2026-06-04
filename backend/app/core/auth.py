"""Admin autentifikatsiya — bitta parol (env ADMIN_PASSWORD) asosida stateless token.

Token = sha256("avatar-studio-admin:" + parol). Parol o'zgarsa token ham o'zgaradi
(eski sessiyalar bekor bo'ladi). Server-side saqlash shart emas — qayta ishga
tushgach ham amal qiladi. Public (user) qism login talab qilmaydi.
"""
import hashlib
import hmac

from app.core.config import load_env_var

# Parol .env'da bo'lmasa — standart "admin" (foydalanuvchi o'zgartirishi shart).
_DEFAULT = "admin"


def admin_password() -> str:
    return load_env_var("ADMIN_PASSWORD") or _DEFAULT


def admin_token() -> str:
    return hashlib.sha256(f"avatar-studio-admin:{admin_password()}".encode()).hexdigest()


def verify_token(token: str) -> bool:
    return hmac.compare_digest((token or "").strip(), admin_token())
