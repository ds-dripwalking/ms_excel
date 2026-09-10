"""Фабрика адаптеров облачных хранилищ."""
from typing import Dict, Any, Type
from app.services.channels.base import BaseStorageAdapter
from app.models.cloud_storage import StorageType


class StorageAdapterFactory:
    """
    Фабрика для создания адаптеров облачных хранилищ.
    
    Используется для выбора правильного адаптера на основе типа хранилища.
    """
    
    _adapters: Dict[StorageType, Type[BaseStorageAdapter]] = {}
    
    @classmethod
    def register_adapter(cls, storage_type: StorageType, adapter_class: Type[BaseStorageAdapter]):
        """Регистрация адаптера для типа хранилища."""
        cls._adapters[storage_type] = adapter_class
    
    @classmethod
    def create(cls, storage_type: StorageType, credentials: Dict[str, Any], **kwargs) -> BaseStorageAdapter:
        """
        Создание адаптера для указанного типа хранилища.
        
        Args:
            storage_type: Тип хранилища.
            credentials: Учетные данные (расшифрованные).
            **kwargs: Дополнительные параметры для конкретных адаптеров.
            
        Returns:
            BaseStorageAdapter: Экземпляр адаптера.
            
        Raises:
            ValueError: Если адаптер для типа не зарегистрирован.
        """
        if storage_type not in cls._adapters:
            raise ValueError(f"Адаптер для типа хранилища {storage_type} не найден")
        
        adapter_class = cls._adapters[storage_type]
        return adapter_class(credentials, **kwargs)
    
    @classmethod
    def get_supported_types(cls) -> list:
        """Получение списка поддерживаемых типов хранилищ."""
        return list(cls._adapters.keys())


# Регистрируем адаптеры
def _register_default_adapters():
    """Регистрация стандартных адаптеров."""
    from app.services.channels.yandex_disk import YandexDiskAdapter
    from app.services.channels.mailru_cloud import MailRuCloudAdapter
    from app.services.channels.google_drive import GoogleDriveAdapter
    from app.services.channels.s3_compatible import S3CompatibleAdapter
    
    StorageAdapterFactory.register_adapter(StorageType.YANDEX_DISK, YandexDiskAdapter)
    StorageAdapterFactory.register_adapter(StorageType.MAILRU_CLOUD, MailRuCloudAdapter)
    StorageAdapterFactory.register_adapter(StorageType.GOOGLE_DRIVE, GoogleDriveAdapter)
    StorageAdapterFactory.register_adapter(StorageType.S3_COMPATIBLE, S3CompatibleAdapter)


# Автоматическая регистрация при импорте
_register_default_adapters()
