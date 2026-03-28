"""
Шифрование/дешифрование чувствительных данных (API ключи Binance).
Используется Fernet (симметричное шифрование AES-128-CBC + HMAC-SHA256).

Как сгенерировать ENCRYPTION_KEY:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os

from cryptography.fernet import Fernet
from loguru import logger


def _get_fernet() -> Fernet | None:
    key = os.getenv("ENCRYPTION_KEY", "")
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        logger.warning("Некорректный ENCRYPTION_KEY — ключи хранятся без шифрования!")
        return None


def encrypt(text: str) -> str:
    """Зашифровать строку. Если ENCRYPTION_KEY не задан — вернуть как есть."""
    f = _get_fernet()
    if f is None:
        return text
    return f.encrypt(text.encode()).decode()


def _looks_like_fernet_token(s: str) -> bool:
    """Fernet в base64url всегда начинается с gAAAA (версия + timestamp)."""
    return bool(s) and s.startswith("gAAAA")


def decrypt(text: str) -> str:
    """Дешифровать строку. Если ENCRYPTION_KEY не задан — вернуть как есть."""
    if not text:
        return text
    f = _get_fernet()
    if f is None:
        return text
    try:
        return f.decrypt(text.encode()).decode()
    except Exception:
        # Раньше при невалидном ключе encrypt() писал plaintext — читаем как есть
        if not _looks_like_fernet_token(text):
            logger.warning(
                "Ключи в БД в открытом виде (legacy) — пересохраните через бота для шифрования"
            )
            return text
        logger.error(
            "Ошибка дешифрования — сменили ENCRYPTION_KEY? "
            "Введите API ключи заново в боте (/start)."
        )
        return ""
