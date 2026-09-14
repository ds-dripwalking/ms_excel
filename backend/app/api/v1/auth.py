"""
API для авторизации через контекст МойСклад.

Этап 4: Авторизация фронтенда через контекст МойСклад.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import jwt

from app.database import get_async_db
from app.models.vendor import MoyskladAccount, MoyskladToken
from app.models.moysklad_api import DictionaryCache
from app.schemas import AuthContextRequest, AuthTokenResponse, MoyskladUserContext
from app.config import settings
from app.crypto import decrypt_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Конфигурация Vendor API
VENDOR_API_URL = "https://apps-api.moysklad.ru/api/vendor/1.0"


def create_mysklad_jwt(context_key: str) -> str:
    """
    Создаёт JWT токен для запроса к Vendor API.
    
    Алгоритм: HS256
    Claims:
      - iss: appId
      - sub: accountId (опционально)
      - aud: moysklad
      - exp: now + 5 min
      - iat: now
      - jti: уникальный ID
    """
    app_id = settings.MOYSKLAD_APP_ID
    secret_key = settings.MOYSKLAD_VENDOR_SECRET
    
    if not app_id or not secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не настроены MOYSKLAD_APP_ID или MOYSKLAD_VENDOR_SECRET"
        )
    
    now = datetime.now(timezone.utc)
    payload = {
        "iss": app_id,
        "aud": "moysklad",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": f"{context_key}_{now.timestamp()}",
    }
    
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return token


async def fetch_user_context(context_key: str, jwt_token: str) -> MoyskladUserContext:
    """
    Запрашивает контекст пользователя у МойСклад.
    
    POST https://apps-api.moysklad.ru/api/vendor/1.0/context/{contextKey}
    Authorization: Bearer {jwt_token}
    """
    url = f"{VENDOR_API_URL}/context/{context_key}"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers)
            
            if response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Неверный JWT токен для МойСклад"
                )
            
            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="contextKey не найден или истёк"
                )
            
            if response.status_code >= 500:
                logger.error(f"Ошибка Vendor API: {response.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Ошибка сервиса МойСклад"
                )
            
            if response.status_code != 200:
                logger.warning(f"Unexpected status: {response.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Ошибка получения контекста: {response.status_code}"
                )
            
            data = response.json()
            
            return MoyskladUserContext(
                accountId=data.get("accountId"),
                accountName=data.get("accountName"),
                userId=data.get("userId"),
                userName=data.get("userName"),
                userEmail=data.get("userEmail"),
                appUid=data.get("appUid"),
                appId=data.get("appId"),
                subscription=data.get("subscription"),
            )
            
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис МойСклад недоступен"
        )


def create_session_token(
    account_id: str,
    user_id: str,
    account_uuid: int
) -> str:
    """
    Создаёт сессионный токен для фронтенда.
    
    Хранит:
      - account_id: accountId из МойСклад
      - user_id: userId из МойСклад
      - account_uuid: внутренний UUID аккаунта в БД
      - exp: 24 часа
    """
    secret_key = settings.JWT_SECRET_KEY or "dev-secret-key-change-in-production"
    
    now = datetime.now(timezone.utc)
    payload = {
        "account_id": account_id,
        "user_id": user_id,
        "account_uuid": account_uuid,
        "iat": now,
        "exp": now + timedelta(hours=24),
    }
    
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return token


@router.post("/context", response_model=AuthTokenResponse)
async def auth_context(
    request: AuthContextRequest,
    db: AsyncSession = Depends(get_async_db)
) -> AuthTokenResponse:
    """
    Авторизация через contextKey из iframe МойСклад.
    
    1. Получает contextKey из запроса.
    2. Формирует JWT для Vendor API.
    3. Запрашивает контекст пользователя.
    4. Находит или создаёт аккаунт в БД.
    5. Выдаёт сессионный токен фронтенду.
    """
    context_key = request.context_key
    
    logger.info(f"Авторизация по contextKey: {context_key[:8]}...")
    
    # Шаг 1: Создаём JWT для Vendor API
    try:
        vendor_jwt = create_mysklad_jwt(context_key)
    except HTTPException as e:
        raise e
    
    # Шаг 2: Запрашиваем контекст у МойСклад
    user_context = await fetch_user_context(context_key, vendor_jwt)
    
    logger.info(
        f"Получен контекст",
        account_id=user_context.accountId,
        user_id=user_context.userId,
        account_name=user_context.accountName
    )
    
    # Шаг 3: Находим аккаунт в БД
    from sqlalchemy import select
    result = await db.execute(
        select(MoyskladAccount).where(
            MoyskladAccount.account_id == user_context.accountId,
            MoyskladAccount.app_id == user_context.appId
        )
    )
    account = result.scalar_one_or_none()
    
    if not account:
        # Аккаунт не найден - возможно пользователь ещё не установил приложение
        # или использует старый contextKey
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Аккаунт не найден. Установите приложение в МойСклад."
        )
    
    # Проверяем статус аккаунта
    if account.status.value == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт приостановлен. Проверьте подписку."
        )
    
    if account.status.value == "deleted_pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт помечен на удаление."
        )
    
    # Шаг 4: Создаём сессионный токен
    session_token = create_session_token(
        account_id=user_context.accountId,
        user_id=user_context.userId,
        account_uuid=account.id
    )
    
    logger.info(
        f"Успешная авторизация",
        account_id=user_context.accountId,
        user_id=user_context.userId
    )
    
    return AuthTokenResponse(
        access_token=session_token,
        token_type="bearer",
        expires_in=86400,  # 24 часа
        account_id=user_context.accountId,
        user_id=user_context.userId
    )


async def get_current_account(
    token: str,
    db: AsyncSession = Depends(get_async_db)
) -> MoyskladAccount:
    """
    Зависимость для получения текущего аккаунта из токена.
    
    Используется в защищённых эндпоинтах.
    """
    secret_key = settings.JWT_SECRET_KEY or "dev-secret-key-change-in-production"
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        account_uuid = payload.get("account_uuid")
        
        if not account_uuid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Невалидный токен"
            )
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен истёк"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен"
        )
    
    from sqlalchemy import select
    result = await db.execute(
        select(MoyskladAccount).where(MoyskladAccount.id == account_uuid)
    )
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Аккаунт не найден"
        )
    
    return account


async def get_current_user_context(
    token: str,
    db: AsyncSession = Depends(get_async_db)
) -> Dict[str, Any]:
    """
    Зависимость для получения контекста текущего пользователя.
    
    Возвращает:
      - account_id: accountId из МойСклад
      - user_id: userId из МойСклад
      - account_uuid: внутренний UUID
    """
    secret_key = settings.JWT_SECRET_KEY or "dev-secret-key-change-in-production"
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        return {
            "account_id": payload.get("account_id"),
            "user_id": payload.get("user_id"),
            "account_uuid": payload.get("account_uuid"),
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен истёк"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен"
        )
