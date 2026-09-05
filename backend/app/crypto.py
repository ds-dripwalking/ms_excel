"""
Модуль шифрования секретов.

Использует AES-256-GCM для authenticated encryption с уникальным nonce.
Мастер-ключ хранится вне базы данных (переменная окружения).
"""

import base64
import json
import logging
import os
import re
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


# Мастер-ключ шифрования (32 байта = 256 бит для AES-256)
# Получается из переменной окружения MASTER_KEY в base64 формате
def _get_master_key() -> bytes:
    """Получает мастер-ключ из переменной окружения."""
    key_b64 = os.environ.get("MASTER_KEY")
    if not key_b64:
        raise ValueError(
            "Мастер-ключ не найден. Установите переменную окружения MASTER_KEY."
        )
    try:
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise ValueError(
                f"Неверная длина ключа: {len(key)} байт. Ожидается 32 байта (256 бит)."
            )
        return key
    except Exception as e:
        raise ValueError(f"Ошибка декодирования мастер-ключа: {e}") from e


def encrypt_secret(payload: dict) -> str:
    """
    Шифрует словарь с секретами.

    Args:
        payload: Словарь с данными для шифрования.

    Returns:
        Base64-строка с зашифрованными данными (nonce + ciphertext + tag).

    Raises:
        ValueError: Если мастер-ключ не найден или некорректен.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload должен быть словарём")

    key = _get_master_key()
    aesgcm = AESGCM(key)

    # Генерируем уникальный nonce (12 байт - рекомендуемый размер для GCM)
    nonce = os.urandom(12)

    # Сериализуем данные в JSON и кодируем в UTF-8
    plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    # Шифруем с аутентификацией (GCM режим)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # Объединяем nonce и ciphertext (tag уже включён в ciphertext)
    encrypted_data = nonce + ciphertext

    # Возвращаем как base64 строку
    return base64.b64encode(encrypted_data).decode("ascii")


def decrypt_secret(payload: str) -> dict:
    """
    Расшифровывает зашифрованные данные.

    Args:
        payload: Base64-строка с зашифрованными данными.

    Returns:
        Словарь с расшифрованными данными.

    Raises:
        ValueError: Если мастер-ключ не найден, некорректен или расшифровка не удалась.
        cryptography.exceptions.InvalidTag: Если данные были изменены или ключ неверен.
    """
    if not isinstance(payload, str):
        raise TypeError("payload должен быть строкой")

    key = _get_master_key()
    aesgcm = AESGCM(key)

    try:
        # Декодируем base64
        encrypted_data = base64.b64decode(payload)

        # Извлекаем nonce (первые 12 байт) и ciphertext
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]

        # Расшифровываем
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        # Десериализуем JSON
        return json.loads(plaintext.decode("utf-8"))

    except InvalidTag as e:
        raise ValueError(
            "Не удалось расшифровать данные: неверный ключ или данные повреждены"
        ) from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Ошибка десериализации данных: {e}") from e
    except Exception as e:
        raise ValueError(f"Ошибка расшифровки: {e}") from e


# === Маскирование чувствительных данных ===


def mask_email(email: str) -> str:
    """
    Маскирует email адрес.

    Пример: user@example.com -> u***@example.com
    """
    if not email or "@" not in email:
        return email

    local, domain = email.rsplit("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = local[0] + "***" + local[-1:]

    return f"{masked_local}@{domain}"


def mask_phone(phone: str) -> str:
    """
    Маскирует телефон.

    Пример: +79991234567 -> +7*** *** ** 67
    """
    if not phone:
        return phone

    # Удаляем все нецифровые символы кроме +
    digits = re.sub(r"[^\d]", "", phone)
    prefix = "+" if phone.startswith("+") else ""

    if len(digits) < 4:
        return prefix + "***"

    # Показываем первые 1 и последние 2 цифры
    masked = f"{digits[0]}*** *** ** {digits[-2:]}"
    return prefix + masked


def mask_token(token: str, visible_chars: int = 4) -> str:
    """
    Маскирует токен/ключ.

    Пример: sk-abc123...xyz -> sk-abc123...****
    """
    if not token:
        return token

    if len(token) <= visible_chars * 2:
        return "*" * len(token)

    return token[:visible_chars] + "..." + "*" * visible_chars


def mask_sensitive_value(value: str, value_type: Optional[str] = None) -> str:
    """
    Автоматически определяет тип чувствительных данных и маскирует их.

    Args:
        value: Значение для маскирования.
        value_type: Подсказка типа ('email', 'phone', 'token').

    Returns:
        Замаскированное значение.
    """
    if not value:
        return value

    if value_type == "email" or ("@" in value and "." in value.split("@")[-1]):
        return mask_email(value)

    if value_type == "phone" or re.match(r"^\+?\d{10,15}$", re.sub(r"[^\d]", "", value)):
        return mask_phone(value)

    # По умолчанию считаем токеном/ключом
    return mask_token(value)


class SecretStr(str):
    """
    Строковый класс для секретных значений с безопасным выводом.
    При печати или логировании автоматически маскируется.
    """

    def __new__(cls, value: str):
        instance = super().__new__(cls, value)
        instance._unmasked_value = value
        return instance

    def __str__(self) -> str:
        return self.masked()

    def __repr__(self) -> str:
        return f"SecretStr({self.masked()!r})"

    def masked(self, visible_chars: int = 4) -> str:
        """Возвращает замаскированное представление."""
        return mask_token(self._unmasked_value, visible_chars)

    def unmasked(self) -> str:
        """Возвращает оригинальное значение (использовать с осторожностью!)."""
        return self._unmasked_value


class SensitiveFilter(logging.Filter):
    """
    Фильтр для логов, который маскирует чувствительные данные.
    """

    # Паттерны для поиска секретов
    PATTERNS = [
        (re.compile(r"(?i)(password|passwd|pwd|secret|token|api_key|apikey|auth)\s*[=:]\s*['\"]?[\w\-]+['\"]?", re.IGNORECASE), r"\1=****"),
        (re.compile(r"Bearer\s+[\w\.\-]+"), "Bearer ****"),
        (re.compile(r"Basic\s+[\w\+/=]+"), "Basic ****"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Маскирует чувствительные данные в сообщении лога."""
        if hasattr(record, "msg") and isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        if hasattr(record, "args") and record.args:
            masked_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    for pattern, replacement in self.PATTERNS:
                        arg = pattern.sub(replacement, arg)
                masked_args.append(arg)
            record.args = tuple(masked_args)
        return True


# Добавляем фильтр к корневому логгеру
logging.getLogger().addFilter(SensitiveFilter())
