"""Базовый интерфейс для облачных хранилищ."""
from abc import ABC, abstractmethod
from typing import Optional, BinaryIO, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


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
    pass


class NotFoundError(StorageError):
    """Ресурс не найден."""
    pass


class BaseStorageAdapter(ABC):
    """
    Базовый абстрактный класс для всех адаптеров облачных хранилищ.
    
    Контракт интерфейса:
    - connect(credentials) -> session / raise AuthError
    - test() -> bool (кнопка "Проверить подключение")
    - ensure_folder(path) -> создать папку (идемпотентно)
    - upload(stream, path, overwrite=true) -> remote_meta
    - publish(path) -> public_url | None
    - list(path) -> [items]
    - delete(path)
    """
    
    def __init__(self, credentials: Dict[str, Any]):
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
    async def test(self) -> bool:
        """
        Проверка подключения к хранилищу.
        
        Returns:
            bool: True если подключение работает.
        """
        pass
    
    @abstractmethod
    async def ensure_folder(self, path: str) -> str:
        """
        Создание папки (идемпотентно).
        
        Args:
            path: Путь к папке.
            
        Returns:
            str: Полный путь к созданной/существующей папке.
        """
        pass
    
    @abstractmethod
    async def upload(
        self,
        stream: BinaryIO,
        path: str,
        overwrite: bool = True,
        filename: Optional[str] = None
    ) -> RemoteFileMeta:
        """
        Загрузка файла в хранилище.
        
        Args:
            stream: Поток данных файла (streaming для больших файлов).
            path: Путь к файлу в хранилище.
            overwrite: Перезаписывать ли существующий файл.
            filename: Имя файла (если None, берется из path).
            
        Returns:
            RemoteFileMeta: Метаданные загруженного файла.
            
        Raises:
            StorageError: Ошибка загрузки.
            QuotaExceededError: Превышена квота хранилища.
        """
        pass
    
    @abstractmethod
    async def publish(self, path: str) -> Optional[str]:
        """
        Публикация файла (создание публичной ссылки).
        
        Args:
            path: Путь к файлу.
            
        Returns:
            Optional[str]: Публичная ссылка или None если публикация не поддерживается.
        """
        pass
    
    @abstractmethod
    async def list(self, path: str) -> List[RemoteFolderItem]:
        """
        Список содержимого папки.
        
        Args:
            path: Путь к папке.
            
        Returns:
            List[RemoteFolderItem]: Список элементов.
        """
        pass
    
    @abstractmethod
    async def delete(self, path: str) -> bool:
        """
        Удаление файла или папки.
        
        Args:
            path: Путь к ресурсу.
            
        Returns:
            bool: True если удаление успешно.
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Закрытие соединения."""
        pass
    
    async def __aenter__(self):
        """Контекстный менеджер: вход."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер: выход."""
        await self.disconnect()
