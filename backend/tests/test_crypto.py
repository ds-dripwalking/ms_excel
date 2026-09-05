"""
Тесты для модуля шифрования секретов.
"""

import base64
import os
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Устанавливаем тестовый мастер-ключ перед импортом crypto
TEST_MASTER_KEY = os.urandom(32)  # 32 байта = 256 бит
os.environ["MASTER_KEY"] = base64.b64encode(TEST_MASTER_KEY).decode("ascii")

from app.crypto import (
    encrypt_secret,
    decrypt_secret,
    mask_email,
    mask_phone,
    mask_token,
    mask_sensitive_value,
    SecretStr,
)


class TestEncryptDecrypt:
    """Тесты шифрования/расшифровки."""

    def test_encrypt_decrypt_basic(self):
        """Базовый тест: шифрование и расшифровка."""
        payload = {"token": "secret123", "user_id": 42}
        encrypted = encrypt_secret(payload)
        decrypted = decrypt_secret(encrypted)
        assert decrypted == payload

    def test_encrypt_returns_base64(self):
        """Шифрование возвращает base64 строку."""
        payload = {"key": "value"}
        encrypted = encrypt_secret(payload)
        # Должна быть валидной base64 строкой
        try:
            base64.b64decode(encrypted)
        except Exception:
            pytest.fail("encrypt_secret не вернул валидную base64 строку")

    def test_decrypt_with_wrong_key_fails(self):
        """Расшифровка с неверным ключом должна падать."""
        payload = {"secret": "data"}
        encrypted = encrypt_secret(payload)

        # Сохраняем оригинальный ключ
        original_key = os.environ.get("MASTER_KEY")

        # Устанавливаем другой ключ
        wrong_key = os.urandom(32)
        os.environ["MASTER_KEY"] = base64.b64encode(wrong_key).decode("ascii")

        # Должно выбросить исключение
        with pytest.raises(ValueError, match="неверный ключ|данные повреждены"):
            decrypt_secret(encrypted)

        # Восстанавливаем оригинальный ключ
        if original_key:
            os.environ["MASTER_KEY"] = original_key

    def test_decrypt_corrupted_data_fails(self):
        """Расшифровка повреждённых данных должна падать."""
        payload = {"secret": "data"}
        encrypted = encrypt_secret(payload)

        # Повреждаем данные (изменяем последний байт)
        corrupted = encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B")

        with pytest.raises(ValueError):
            decrypt_secret(corrupted)

    def test_encrypt_empty_dict(self):
        """Шифрование пустого словаря."""
        payload = {}
        encrypted = encrypt_secret(payload)
        decrypted = decrypt_secret(encrypted)
        assert decrypted == {}

    def test_encrypt_nested_dict(self):
        """Шифрование вложенного словаря."""
        payload = {
            "oauth": {
                "access_token": "abc123",
                "refresh_token": "xyz789",
            },
            "nested": {"deep": {"value": "secret"}}
        }
        encrypted = encrypt_secret(payload)
        decrypted = decrypt_secret(encrypted)
        assert decrypted == payload

    def test_encrypt_unicode_data(self):
        """Шифрование данных с Unicode."""
        payload = {"text": "Привет мир 🌍", "emoji": "🔐"}
        encrypted = encrypt_secret(payload)
        decrypted = decrypt_secret(encrypted)
        assert decrypted == payload

    def test_no_master_key_raises_error(self):
        """Отсутствие мастер-ключа должно вызывать ошибку."""
        original_key = os.environ.pop("MASTER_KEY", None)

        try:
            with pytest.raises(ValueError, match="Мастер-ключ не найден"):
                encrypt_secret({"test": "data"})
        finally:
            # Восстанавливаем ключ
            if original_key:
                os.environ["MASTER_KEY"] = original_key

    def test_unique_nonce(self):
        """Каждое шифрование должно использовать уникальный nonce."""
        payload = {"same": "data"}
        encrypted1 = encrypt_secret(payload)
        encrypted2 = encrypt_secret(payload)
        # Даже при одинаковых данных результат должен отличаться из-за nonce
        assert encrypted1 != encrypted2

    def test_invalid_payload_type(self):
        """Неверный тип payload должен вызывать TypeError."""
        with pytest.raises(TypeError):
            encrypt_secret("not a dict")

        with pytest.raises(TypeError):
            encrypt_secret(["list"])

    def test_decrypt_invalid_type(self):
        """Неверный тип payload для расшифровки должен вызывать TypeError."""
        with pytest.raises(TypeError):
            decrypt_secret({"not": "string"})  # type: ignore


class TestMasking:
    """Тесты маскирования чувствительных данных."""

    def test_mask_email_normal(self):
        """Маскирование обычного email."""
        assert mask_email("user@example.com") == "u***r@example.com"

    def test_mask_email_short(self):
        """Маскирование короткого email."""
        result = mask_email("ab@test.com")
        assert "***" in result
        assert "@test.com" in result

    def test_mask_email_single_char(self):
        """Маскирование email с одним символом локальной части."""
        result = mask_email("a@test.com")
        assert "***" in result

    def test_mask_phone_russian(self):
        """Маскирование российского телефона."""
        result = mask_phone("+79991234567")
        assert "+7*** *** ** 67" in result or "***" in result

    def test_mask_phone_international(self):
        """Маскирование международного телефона."""
        result = mask_phone("+12345678901")
        assert "***" in result

    def test_mask_phone_short(self):
        """Маскирование короткого номера."""
        result = mask_phone("123")
        assert "***" in result

    def test_mask_token_long(self):
        """Маскирование длинного токена."""
        token = "sk-abc123def456ghi789jkl012mno345pqr"
        result = mask_token(token)
        assert result.startswith("sk-a")
        assert result.endswith("****")
        assert "..." in result

    def test_mask_token_short(self):
        """Маскирование короткого токена."""
        token = "abc"
        result = mask_token(token)
        assert result == "***"

    def test_mask_token_empty(self):
        """Маскирование пустого токена."""
        assert mask_token("") == ""
        assert mask_token(None) is None

    def test_mask_sensitive_value_email(self):
        """Автоматическое определение email."""
        result = mask_sensitive_value("user@example.com")
        assert "@" in result
        assert "***" in result

    def test_mask_sensitive_value_phone(self):
        """Автоматическое определение телефона."""
        result = mask_sensitive_value("+79991234567", value_type="phone")
        assert "***" in result

    def test_mask_sensitive_value_token(self):
        """Автоматическое определение токена."""
        result = mask_sensitive_value("api_key_12345")
        assert "***" in result or "..." in result


class TestSecretStr:
    """Тесты класса SecretStr."""

    def test_secretstr_str_masks(self):
        """str() должен возвращать замаскированное значение."""
        secret = SecretStr("my_super_secret_password")
        assert str(secret) != "my_super_secret_password"
        assert "***" in str(secret) or "..." in str(secret)

    def test_secretstr_repr_masks(self):
        """repr() должен возвращать замаскированное значение."""
        secret = SecretStr("secret_value")
        repr_str = repr(secret)
        assert "secret_value" not in repr_str
        assert "SecretStr" in repr_str

    def test_secretstr_unmasked(self):
        """unmasked() должен возвращать оригинальное значение."""
        original = "my_secret_token"
        secret = SecretStr(original)
        assert secret.unmasked() == original

    def test_secretstr_print_masks(self):
        """print() должен выводить замаскированное значение."""
        secret = SecretStr("password123")
        # Проверяем, что str возвращает маскированное значение
        masked = str(secret)
        assert "password123" not in masked


class TestEncryptionFields:
    """
    Тесты для проверки типов полей, которые должны шифроваться:
    - токен МойСклад
    - OAuth-токены Яндекс
    - OAuth-токены Google
    - пароль приложения Mail.ru
    - SMTP-пароль
    - токены ботов
    """

    def test_mysklad_token_encryption(self):
        """Шифрование токена МойСклад."""
        payload = {"mysklad_token": "iAmASecretToken12345"}
        encrypted = encrypt_secret(payload)
        decrypted = decrypt_secret(encrypted)
        assert decrypted["mysklad_token"] == "iAmASecretToken12345"

    def test_yandex_oauth_tokens(self):
        """Шифрование OAuth-токенов Яндекс."""
        payload = {
            "yandex_access_token": "ya29.secret_access_token",
            "yandex_refresh_token": "1-secret-refresh-token",
        }
        encrypted = encrypt_secret(payload)
        decrypted = decrypt_secret(encrypted)
        assert decrypted == payload

    def test_google_oauth_tokens(self):
        """Шифрование OAuth-токенов Google."""
        payload = {
            "google_access_token": "ya29.a0AfH6SMBx...",
            "google_refresh_token": "1//0gSecretRefreshToken",
        }
        encrypted = encrypt_secret(payload)
        decrypted = decrypt_secret(encrypted)
        assert decrypted == payload

    def test_mailru_app_password(self):
        """Шифрование пароля приложения Mail.ru."""
        payload = {"mailru_app_password": "VerySecretPassword123!"}
        encrypted = encrypt_secret(payload)
        decrypted = decrypt_secret(encrypted)
        assert decrypted["mailru_app_password"] == "VerySecretPassword123!"

    def test_smtp_password(self):
        """Шифрование SMTP-пароля."""
        payload = {"smtp_password": "SmtpSecretPass!@#"}
        encrypted = encrypt_secret(payload)
        decrypted = decrypt_secret(encrypted)
        assert decrypted["smtp_password"] == "SmtpSecretPass!@#"

    def test_bot_tokens(self):
        """Шифрование токенов ботов."""
        payload = {
            "telegram_bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "slack_bot_token": "TEST_SLACK_TOKEN_PLACEHOLDER",
        }
        encrypted = encrypt_secret(payload)
        decrypted = decrypt_secret(encrypted)
        assert decrypted == payload
