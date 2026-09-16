"""API для управления каналами доставки."""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import List, Any
from pydantic import BaseModel, Field
import uuid

from app.database import get_db
from app.models.cloud_storage import CloudCredential, StorageType
from app.models.vendor import MoyskladAccount
from app.services.channels.factory import StorageAdapterFactory
from app.services.channels.base import ChannelTestResult
from app.crypto import CryptoService


async def get_account_from_context(
    db: Session = Depends(get_db),
    x_account_id: str = Header(..., description="ID аккаунта из заголовка")
) -> MoyskladAccount:
    """Получение аккаунта из заголовка X-Account-ID."""
    account = db.query(MoyskladAccount).filter(MoyskladAccount.id == x_account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Аккаунт не найден")
    return account


router = APIRouter(prefix="/channels", tags=["Каналы доставки"])


class ChannelTestResponse(BaseModel):
    """Ответ теста подключения канала."""
    success: bool
    message: str
    provider: str
    
    class Config:
        from_attributes = True


class ChannelCreateRequest(BaseModel):
    """Запрос на создание канала."""
    storage_type: StorageType
    name: str = "Новый канал"
    credentials_data: dict = Field(..., description="Данные для шифрования (зависят от типа)")
    default_folder: str = "/kombain_exports"
    overwrite_enabled: bool = True


class ChannelResponse(BaseModel):
    """Ответ с информацией о канале."""
    id: str
    storage_type: StorageType
    name: str
    default_folder: str
    overwrite_enabled: bool
    is_active: bool
    test_status: str | None
    last_tested_at: str | None
    
    class Config:
        from_attributes = True


@router.post("/test", response_model=ChannelTestResponse)
async def test_channel_connection(
    request: ChannelCreateRequest,
    account: MoyskladAccount = Depends(get_account_from_context),
    db: Session = Depends(get_db)
):
    """
    Тестирование подключения к каналу без сохранения.
    Используется для проверки корректности введенных данных.
    """
    try:
        # Создаем временные учетные данные для теста
        crypto = CryptoService()
        encrypted_creds = crypto.encrypt(str(request.credentials_data))
        
        temp_credential = CloudCredential(
            id=str(uuid.uuid4()),
            account_id=account.id,
            storage_type=request.storage_type,
            name=request.name,
            encrypted_credentials=encrypted_creds,
            default_folder=request.default_folder,
            overwrite_enabled=request.overwrite_enabled
        )
        
        # Расшифровываем для адаптера
        decrypted_data = crypto.decrypt(temp_credential.encrypted_credentials)
        import json
        try:
            creds_dict = json.loads(decrypted_data)
        except:
            creds_dict = {"raw_data": decrypted_data}
        
        # Создаем объект-заглушку с нужным интерфейсом
        class MockCredential:
            def __init__(self, data):
                self.decrypted_data = data
        
        mock_cred = MockCredential(creds_dict)
        
        # Создаем адаптер через фабрику
        adapter = StorageAdapterFactory.create(request.storage_type, mock_cred)
        
        # Запускаем тест
        result: ChannelTestResult = await adapter.test()
        
        return ChannelTestResponse(
            success=result.success,
            message=result.message,
            provider=request.storage_type.value
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка тестирования: {str(e)}"
        )


@router.get("/", response_model=List[ChannelResponse])
async def list_channels(
    account: MoyskladAccount = Depends(get_account_from_context),
    db: Session = Depends(get_db)
):
    """Получение списка всех каналов текущего аккаунта."""
    channels = db.query(CloudCredential).filter(
        CloudCredential.account_id == current_account_id,
        CloudCredential.is_active == True
    ).all()
    
    return channels


@router.post("/", response_model=ChannelResponse)
async def create_channel(
    request: ChannelCreateRequest,
    account: MoyskladAccount = Depends(get_account_from_context),
    db: Session = Depends(get_db)
):
    """Создание нового канала доставки."""
    try:
        crypto = CryptoService()
        import json
        encrypted_creds = crypto.encrypt(json.dumps(request.credentials_data))
        
        channel = CloudCredential(
            id=str(uuid.uuid4()),
            account_id=account.id,
            storage_type=request.storage_type,
            name=request.name,
            encrypted_credentials=encrypted_creds,
            default_folder=request.default_folder,
            overwrite_enabled=request.overwrite_enabled,
            test_status="pending"
        )
        
        db.add(channel)
        db.commit()
        db.refresh(channel)
        
        return ChannelResponse.model_validate(channel)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка создания канала: {str(e)}"
        )


@router.get("/{channel_id}/test", response_model=ChannelTestResponse)
async def test_existing_channel(
    channel_id: str,
    account: MoyskladAccount = Depends(get_account_from_context),
    db: Session = Depends(get_db)
):
    """Тестирование существующего канала."""
    channel = db.query(CloudCredential).filter(
        CloudCredential.id == channel_id,
        CloudCredential.account_id == current_account_id
    ).first()
    
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Канал не найден"
        )
    
    try:
        crypto = CryptoService()
        decrypted_data = crypto.decrypt(channel.encrypted_credentials)
        import json
        try:
            creds_dict = json.loads(decrypted_data)
        except:
            creds_dict = {"raw_data": decrypted_data}
        
        class MockCredential:
            def __init__(self, data):
                self.decrypted_data = data
        
        mock_cred = MockCredential(creds_dict)
        adapter = StorageAdapterFactory.create(channel.storage_type, mock_cred)
        
        result: ChannelTestResult = await adapter.test()
        
        # Обновляем статус в БД
        from datetime import datetime, timezone
        channel.last_tested_at = datetime.now(timezone.utc)
        channel.test_status = "success" if result.success else "failed"
        channel.test_error_message = None if result.success else result.message
        db.commit()
        
        return ChannelTestResponse(
            success=result.success,
            message=result.message,
            provider=channel.storage_type.value
        )
        
    except Exception as e:
        from datetime import datetime, timezone
        channel.last_tested_at = datetime.now(timezone.utc)
        channel.test_status = "failed"
        channel.test_error_message = str(e)
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка тестирования: {str(e)}"
        )


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: str,
    account: MoyskladAccount = Depends(get_account_from_context),
    db: Session = Depends(get_db)
):
    """Удаление канала (помечается как неактивный)."""
    channel = db.query(CloudCredential).filter(
        CloudCredential.id == channel_id,
        CloudCredential.account_id == current_account_id
    ).first()
    
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Канал не найден"
        )
    
    channel.is_active = False
    db.commit()
    
    return {"message": "Канал удален"}
