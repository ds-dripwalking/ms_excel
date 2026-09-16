"""
Сервис для генерации исходящих JWT-токенов для запросов к API МойСклад.
Спецификация: integration.md §11.2
Требования:
- alg: HS256
- sub: appUid
- iat: текущее время
- jti: уникальный UUID
- exp: iat + 300 сек (не более 5 минут)
"""

import uuid
import time
import jwt
from typing import Optional
import os


class OutboundJWTService:
    """Сервис генерации JWT для исходящих запросов к МойСклад."""

    ALGORITHM = "HS256"
    TOKEN_LIFETIME_SECONDS = 300  # 5 минут

    def __init__(self, secret_key: Optional[str] = None, app_uid: Optional[str] = None):
        # Берем из env напрямую, чтобы избежать зависимости от config
        self.secret_key = secret_key or os.getenv("SECRET_KEY", "fallback-secret-key")
        self.app_uid = app_uid or os.getenv("MOYSKLAD_APP_UID")

    def generate_token(self, app_uid: Optional[str] = None) -> str:
        """
        Генерирует JWT для запроса к API МойСклад.
        
        :param app_uid: UID приложения (если не передан, берется из настроек)
        :return: JWT токен
        """
        uid = app_uid or self.app_uid
        if not uid:
            raise ValueError("APP_UID не настроен. Невозможно сгенерировать исходящий JWT.")

        now = int(time.time())
        payload = {
            "sub": uid,
            "iat": now,
            "jti": str(uuid.uuid4()),
            "exp": now + self.TOKEN_LIFETIME_SECONDS,
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.ALGORITHM)
        return token

    def verify_token(self, token: str) -> dict:
        """
        Проверяет валидность токена (для тестов или отладки).
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.ALGORITHM],
                options={"require": ["exp", "iat", "jti", "sub"]}
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Токен истек")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Невалидный токен: {e}")


# Глобальный экземпляр
outbound_jwt_service = OutboundJWTService()
