# Модуль шифрования секретов
Использует AES-256-GCM для authenticated encryption.

## Генерация мастер-ключа

```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

Сохраните полученный ключ в переменную окружения `MASTER_KEY`.

## Использование

### Шифрование/расшифровка

```python
from app.crypto import encrypt_secret, decrypt_secret

# Шифрование
payload = {
    "token": "secret_token_123",
    "password": "super_secret_password"
}
encrypted = encrypt_secret(payload)
# encrypted: base64 строка

# Расшифровка
decrypted = decrypt_secret(encrypted)
# decrypted: {"token": "secret_token_123", "password": "super_secret_password"}
```

### Маскирование чувствительных данных

```python
from app.crypto import mask_email, mask_phone, mask_token, SecretStr

# Email
mask_email("user@example.com")  # u***r@example.com

# Телефон
mask_phone("+79991234567")  # +7*** *** ** 67

# Токен
mask_token("sk-abc123def456")  # sk-a...****

# SecretStr - класс для безопасного хранения секретов
secret = SecretStr("my_password")
print(secret)  # my_p...**** (маскируется автоматически)
secret.unmasked()  # "my_password" (оригинальное значение)
```

## Хранение мастер-ключа

### 1. Переменная окружения (рекомендуется для разработки)

```bash
export MASTER_KEY="your-base64-encoded-key"
```

### 2. Secrets Manager (для production)

Интеграция с AWS Secrets Manager, HashiCorp Vault и т.д.

### 3. KMS (Key Management Service)

Использование облачных KMS для управления ключами на этапе роста.

## Поля для шифрования

Все следующие типы данных должны храниться зашифрованными:
- токен МойСклад
- OAuth-токены Яндекс
- OAuth-токены Google
- пароль приложения Mail.ru
- SMTP-пароль
- токены ботов (Telegram, Slack, etc.)

## Безопасность логов

Модуль автоматически добавляет фильтр `SensitiveFilter` к корневому логгеру,
который маскирует чувствительные данные в логах:
- password=****
- token=****
- Bearer ****
- Basic ****
