"""
Модуль для проверки JWT токенов от МойСклад.

Проверка включает:
- Алгоритм HS256
- Подпись с secretKey
- exp (время истечения)
- jti (уникальный ID)
- Одноразовость jti
"""
import jwt
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.vendor import ProcessedJTI
from app.logging_config import logger


class JWTValidationError(Exception):
    """Исключение при ошибке валидации JWT."""
    pass


def validate_mysklad_jwt(
    token: str,
    secret_key: str,
    db: Session
) -> Dict[str, Any]:
    """
    Валидирует JWT токен от МойСклад.
    
    Args:
        token: JWT токен из заголовка Authorization.
        secret_key: Секретный ключ для проверки подписи.
        db: Сессия базы данных для проверки jti.
        
    Returns:
        Payload токена.
        
    Raises:
        JWTValidationError: Если токен невалиден.
    """
    try:
        # Декодируем токен без проверки для получения header
        unverified_header = jwt.get_unverified_header(token)
        
        # Проверяем алгоритм
        if unverified_header.get("alg") != "HS256":
            raise JWTValidationError(f"Неверный алгоритм: {unverified_header.get('alg')}. Ожидается HS256.")
        
        # Проверяем тип
        if unverified_header.get("typ") != "JWT":
            raise JWTValidationError(f"Неверный тип: {unverified_header.get('typ')}. Ожидается JWT.")
        
        # Декодируем и проверяем токен
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            options={
                "require": ["exp", "jti", "iat"],
                "verify_exp": True,
            }
        )
        
        # Проверяем наличие обязательных полей
        if "jti" not in payload:
            raise JWTValidationError("Отсутствует поле jti в токене.")
        
        if "iat" not in payload:
            raise JWTValidationError("Отсутствует поле iat в токене.")
        
        if "exp" not in payload:
            raise JWTValidationError("Отсутствует поле exp в токене.")
        
        jti = payload["jti"]
        
        # Проверяем одноразовость jti
        existing_jti = db.query(ProcessedJTI).filter(ProcessedJTI.jti == jti).first()
        if existing_jti:
            logger.warning(
                f"Повторное использование jti: {jti}",
                request_id=existing_jti.request_id,
                original_processed_at=existing_jti.processed_at.isoformat()
            )
            raise JWTValidationError(f"jti уже был использован: {jti}")
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise JWTValidationError("Токен истёк (exp).")
    except jwt.InvalidAlgorithmError:
        raise JWTValidationError("Неверный алгоритм подписи.")
    except jwt.DecodeError:
        raise JWTValidationError("Не удалось декодировать токен.")
    except jwt.InvalidTokenError as e:
        raise JWTValidationError(f"Невалидный токен: {e}")


def mark_jti_as_used(
    db: Session,
    jti: str,
    request_id: Optional[str] = None,
    operation_type: Optional[str] = None,
    account_id: Optional[str] = None
) -> ProcessedJTI:
    """
    Отмечает jti как использованный.
    
    Args:
        db: Сессия базы данных.
        jti: Уникальный ID токена.
        request_id: X_Lognex_RequestId для логирования.
        operation_type: Тип операции.
        account_id: accountId из МойСклад.
        
    Returns:
        Созданная запись ProcessedJTI.
    """
    processed_jti = ProcessedJTI(
        jti=jti,
        request_id=request_id,
        operation_type=operation_type,
        account_id=account_id,
        processed_at=datetime.now(timezone.utc)
    )
    db.add(processed_jti)
    db.commit()
    
    logger.info(f"jti отмечен как использованный: {jti}", request_id=request_id)
    
    return processed_jti


def get_existing_jti(db: Session, jti: str) -> Optional[ProcessedJTI]:
    """
    Возвращает существующую запись jti, если она есть.
    
    Args:
        db: Сессия базы данных.
        jti: Уникальный ID токена.
        
    Returns:
        Запись ProcessedJTI или None.
    """
    return db.query(ProcessedJTI).filter(ProcessedJTI.jti == jti).first()
