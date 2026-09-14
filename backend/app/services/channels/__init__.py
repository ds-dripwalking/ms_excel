"""Каналы доставки - адаптеры облачных хранилищ."""
from app.services.channels.base import (
    BaseStorageAdapter,
    RemoteFileMeta,
    RemoteFolderItem,
    StorageError,
    AuthError,
    PermissionError,
    QuotaExceededError,
    NotFoundError,
)
from app.services.channels.factory import StorageAdapterFactory
from app.services.channels.yandex_disk import YandexDiskAdapter
from app.services.channels.mailru_cloud import MailRuCloudAdapter
from app.services.channels.google_drive import GoogleDriveAdapter
from app.services.channels.s3_compatible import S3CompatibleAdapter

__all__ = [
    # Базовые классы
    "BaseStorageAdapter",
    "RemoteFileMeta",
    "RemoteFolderItem",
    # Исключения
    "StorageError",
    "AuthError",
    "PermissionError",
    "QuotaExceededError",
    "NotFoundError",
    # Фабрика
    "StorageAdapterFactory",
    # Адаптеры
    "YandexDiskAdapter",
    "MailRuCloudAdapter",
    "GoogleDriveAdapter",
    "S3CompatibleAdapter",
]
