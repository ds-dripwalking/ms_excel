"""Модели для облачных хранилищ (каналы доставки)."""
from sqlalchemy import Column, String, Text, ForeignKey, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class StorageType(str, enum.Enum):
    """Типы поддерживаемых облачных хранилищ."""
    YANDEX_DISK = "yandex_disk"
    MAILRU_CLOUD = "mailru_cloud"
    GOOGLE_DRIVE = "google_drive"
    S3_COMPATIBLE = "s3_compatible"  # VK Cloud, MTS Cloud, Yandex Object Storage


class CloudCredential(Base):
    """Учетные данные для доступа к облачным хранилищам."""
    __tablename__ = "cloud_credentials"

    id = Column(String(36), primary_key=True)  # UUID
    account_id = Column(String(36), ForeignKey("moysklad_accounts.id"), nullable=False, index=True)
    
    # Тип хранилища
    storage_type = Column(SQLEnum(StorageType), nullable=False)
    
    # Название профиля (для удобства пользователя)
    name = Column(String(255), nullable=False, default="Основное хранилище")
    
    # Зашифрованные учетные данные (JSON как текст)
    # Структура зависит от типа хранилища:
    # - YANDEX_DISK: {"access_token": "...", "refresh_token": "...", "token_expires_at": "..."}
    # - MAILRU_CLOUD: {"login": "...", "app_password": "..."}
    # - GOOGLE_DRIVE: {"access_token": "...", "refresh_token": "...", "token_expires_at": "..."}
    # - S3_COMPATIBLE: {"endpoint": "...", "bucket": "...", "access_key": "...", "secret_key": "...", "region": "..."}
    encrypted_credentials = Column(Text, nullable=False)
    
    # Настройки по умолчанию
    default_folder = Column(String(500), default="/kombain_exports")  # Папка для выгрузок
    overwrite_enabled = Column(Boolean, default=True)  # Перезаписывать файлы с одинаковым именем
    
    # Статус подключения
    is_active = Column(Boolean, default=True)
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    test_status = Column(String(50), nullable=True)  # "success", "failed", "pending"
    test_error_message = Column(Text, nullable=True)
    
    # Метаданные
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Связи
    account = relationship("MoyskladAccount", back_populates="cloud_credentials")
    export_profiles = relationship("ExportProfile", back_populates="cloud_credential")

    def __repr__(self):
        return f"<CloudCredential(id={self.id}, type={self.storage_type}, name={self.name})>"
