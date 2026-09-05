"""
Модели данных для Vendor API МойСклад.
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class AccountStatus(str, enum.Enum):
    """Статус аккаунта."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED_PENDING = "deleted_pending"
    DELETED = "deleted"


class TariffType(str, enum.Enum):
    """Тип тарифа."""
    LITE = "lite"
    PROFESSIONAL = "professional"


class CauseType(str, enum.Enum):
    """Тип события от МойСклад."""
    INSTALL = "Install"
    RESUME = "Resume"
    TARIFF_CHANGED = "TariffChanged"
    AUTOPROLONGATION = "Autoprolongation"
    SUSPEND = "Suspend"
    UNINSTALL = "Uninstall"


class MoyskladAccount(Base):
    """Аккаунт пользователя МойСклад."""
    __tablename__ = "moysklad_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(255), nullable=False, index=True)  # accountId из МойСклад
    app_id = Column(String(255), nullable=False)  # appId из МойСклад
    
    # Статус аккаунта
    status = Column(Enum(AccountStatus), default=AccountStatus.ACTIVE, nullable=False)
    
    # Тариф
    tariff = Column(Enum(TariffType), default=TariffType.LITE, nullable=False)
    
    # Дата окончания оплаченного периода
    paid_end_date = Column(DateTime, nullable=True)
    
    # Дата установки
    installed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Дата последнего обновления
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Дата удаления (для grace-периода)
    deleted_at = Column(DateTime, nullable=True)
    
    # Связи
    tokens = relationship("MoyskladToken", back_populates="account", cascade="all, delete-orphan")
    profiles = relationship("IntegrationProfile", back_populates="account", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('account_id', 'app_id', name='uq_account_app'),
    )


class MoyskladToken(Base):
    """Хранение зашифрованных токенов JSON API МойСклад."""
    __tablename__ = "moysklad_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("moysklad_accounts.id"), nullable=False)
    
    # Зашифрованный токен (JSON API token)
    encrypted_token = Column(Text, nullable=False)
    
    # Тип токена
    token_type = Column(String(50), default="json_api", nullable=False)
    
    # Дата создания
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Дата обновления
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Связь
    account = relationship("MoyskladAccount", back_populates="tokens")


class IntegrationProfile(Base):
    """Профили интеграции (настройки синхронизации)."""
    __tablename__ = "integration_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("moysklad_accounts.id"), nullable=False)
    
    # Название профиля
    name = Column(String(255), nullable=False)
    
    # Настройки профиля (JSON)
    settings = Column(Text, nullable=True)  # JSON строка с настройками
    
    # Активность профиля
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Дата создания
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Дата обновления
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Связь
    account = relationship("MoyskladAccount", back_populates="profiles")


class ProcessedJTI(Base):
    """Хранение обработанных jti для защиты от повторных запросов."""
    __tablename__ = "processed_jtis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jti = Column(String(255), nullable=False, unique=True, index=True)
    
    # Время обработки
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # X_Lognex_RequestId для логирования
    request_id = Column(String(255), nullable=True)
    
    # Тип операции
    operation_type = Column(String(50), nullable=True)
    
    # accountId для быстрого поиска
    account_id = Column(String(255), nullable=True, index=True)
