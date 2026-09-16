"""Базовый интерфейс для облачных хранилищ."""
from abc import ABC, abstractmethod
from typing import Optional, BinaryIO, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ChannelTestResult:
    """Результат тестирования канала."""
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class RemoteFileMeta:
    """Метаданные удаленного файла."""
    path: str
    name: str
    size: int
    created_at: datetime
    modified_at: datetime
    public_url: Optional[str] = None
    mime_type: Optional[str] = None


@dataclass
class RemoteFolderItem:
    """Элемент списка папки."""
    name: str
    path: str
    is_folder: bool
    size: Optional[int] = None
    modified_at: Optional[datetime] = None


class StorageError(Exception):
    """Базовое исключение для ошибок хранилища."""
    pass


class AuthError(StorageError):
    """Ошибка аутентификации."""
    pass


class PermissionError(StorageError):
    """Ошибка прав доступа."""
    pass


class QuotaExceededError(StorageError):
    """Превышена квота хранилища."""
    
    def __init__(self, message: str = "Превышена квота хранилища"):
        super().__init__(message)


class NotFoundError(StorageError):
    """Ресурс не найден."""
    pass


class BaseStorageAdapter(ABC):
    """
    Базовый абстрактный класс для всех адаптеров облачных хранилищ.
    
    Контракт интерфейса:
    - connect() -> bool / raise AuthError
    - test() -> ChannelTestResult (кнопка "Проверить подключение")
    - ensure_folder(path) -> создать папку (идемпотентно)
    - upload(file_path, filename, ...) -> dict с результатом
    - publish(path) -> public_url | None
    - list(path) -> [items]
    - delete(path)
    """
    
    provider_name: str = "base"
    
    def __init__(self, credentials: Any):
        """
        Инициализация адаптера.
        
        Args:
            credentials: Учетные данные (расшифрованные).
                        Структура зависит от типа хранилища.
        """
        self.credentials = credentials
        self._session = None
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Установка соединения с хранилищем.
        
        Returns:
            bool: True если соединение успешно установлено.
            
        Raises:
            AuthError: Если учетные данные неверны.
        """
        pass
    
    @abstractmethod
    async def test(self) -> ChannelTestResult:
        """
        Проверка подключения к хранилищу.
        
        Returns:
            ChannelTestResult: Результат тестирования.
        """
        pass
    
    @abstractmethod
    async def ensure_folder(self, folder_path: str) -> bool:
        """
        Создание папки (идемпотентно).
        
        Args:
            folder_path: Путь к папке.
            
        Returns:
            bool: True если папка существует или создана.
        """
        pass
    
    @abstractmethod
    async def upload(self, file_path: str, file_name: str, **kwargs) -> Dict[str, Any]:
        """
        Загрузка файла в хранилище.
        
        Поддерживает streaming для больших файлов (>100 МБ).
        
        Args:
            file_path: Путь к файлу на диске.
            file_name: Имя файла для сохранения.
            **kwargs: Дополнительные параметры (например, recipient_email для Email).
            
        Returns:
            Dict[str, Any]: Результат загрузки (зависит от адаптера).
            
        Raises:
            StorageError: Ошибка загрузки.
            QuotaExceededError: Превышена квота хранилища.
        """
        pass
    
    @abstractmethod
    async def publish(self, file_id: str, public: bool = True) -> Optional[str]:
        """
        Публикация файла (создание публичной ссылки).
        
        Args:
            file_id: Идентификатор файла.
            public: Сделать публичным или приватным.
            
        Returns:
            Optional[str]: Публичная ссылка или None.
        """
        pass
    
    @abstractmethod
    async def list_files(self, folder_path: str = "") -> list:
        """
        Список содержимого папки.
        
        Args:
            folder_path: Путь к папке.
            
        Returns:
            list: Список элементов.
        """
        pass
    
    @abstractmethod
    async def delete(self, file_id: str) -> bool:
        """
        Удаление файла или папки.
        
        Args:
            file_id: Идентификатор ресурса.
            
        Returns:
            bool: True если удаление успешно.
        """
        pass
    
    @abstractmethod
    async def get_download_url(self, file_id: str, expires_in: int = 3600) -> str:
        """
        Генерация временной ссылки для скачивания.
        
        Args:
            file_id: Идентификатор файла.
            expires_in: Время жизни ссылки в секундах.
            
        Returns:
            str: Ссылка для скачивания.
        """
        pass
