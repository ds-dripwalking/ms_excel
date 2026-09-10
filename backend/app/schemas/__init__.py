"""
Схемы данных (Pydantic) для API.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


# ==================== АВТОРИЗАЦИЯ ====================

class AuthContextRequest(BaseModel):
    """Запрос на получение контекста авторизации."""
    context_key: str = Field(..., description="contextKey из URL iframe")


class MoyskladUserContext(BaseModel):
    """Контекст пользователя от МойСклад."""
    accountId: str
    accountName: str
    userId: str
    userName: str
    userEmail: Optional[str] = None
    appUid: str
    appId: str
    subscription: Optional[Dict[str, Any]] = None


class AuthTokenResponse(BaseModel):
    """Ответ с токеном авторизации."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    account_id: str
    user_id: str


# ==================== ПРОФИЛИ ====================

class ProfileBase(BaseModel):
    """Базовая схема профиля."""
    name: str = Field(..., min_length=1, max_length=255)
    module: str = Field(..., description="orders | pricelist")


class ProfileCreate(ProfileBase):
    """Схема создания профиля."""
    fields_config: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    format_config: Optional[Dict[str, Any]] = None
    channel_config: Optional[Dict[str, Any]] = None
    schedule_config: Optional[Dict[str, Any]] = None


class ProfileUpdate(BaseModel):
    """Схема обновления профиля."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    fields_config: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    format_config: Optional[Dict[str, Any]] = None
    channel_config: Optional[Dict[str, Any]] = None
    schedule_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ProfileResponse(ProfileBase):
    """Схема ответа профиля."""
    id: int
    account_id: int
    fields_config: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    format_config: Optional[Dict[str, Any]] = None
    channel_config: Optional[Dict[str, Any]] = None
    schedule_config: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ==================== ЗАДАНИЯ ====================

class JobStatus(str, Enum):
    """Статусы заданий."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExportJobResponse(BaseModel):
    """Схема ответа задания."""
    id: int
    profile_id: int
    account_id: int
    status: str
    export_type: str
    parameters: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result_file_path: Optional[str] = None
    download_url: Optional[str] = None
    records_processed: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class JobEventResponse(BaseModel):
    """Схема события задания."""
    id: int
    job_id: int
    event_type: str
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== СПРАВОЧНИКИ ====================

class DictionaryResponse(BaseModel):
    """Схема ответа справочника."""
    type: str
    data: List[Dict[str, Any]]
    cached_at: Optional[datetime] = None


# ==================== БИЛЛИНГ ====================

class BillingSummary(BaseModel):
    """Сводка по биллингу."""
    tariff: str
    is_trial: bool
    trial_end_date: Optional[datetime] = None
    paid_end_date: Optional[datetime] = None
    profiles_count: int
    profiles_limit: Optional[int] = None
    modules_used: List[str]
    can_create_profile: bool
