"""Базовый интерфейс для облачных хранилищ."""
from abc import ABC, abstractmethod
from typing import Optional, BinaryIO, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio
import time


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
    
    # Настройки retry
    MAX_RETRIES: int = 5
    BASE_DELAY: float = 1.0  # секунды
    MAX_DELAY: float = 60.0  # секунды
    
    # Streaming порог (100 МБ)
    STREAMING_THRESHOLD: int = 100 * 1024 * 1024
    
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
    
    async def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Выполнение функции с экспоненциальным backoff retry.
        
        Args:
            func: Асинхронная функция для выполнения.
            *args: Позиционные аргументы функции.
            **kwargs: Именованные аргументы функции.
            
        Returns:
            Результат выполнения функции.
            
        Raises:
            Последнее исключение, если все retry исчерпаны.
        """
        last_exception = None
        
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await func(*args, **kwargs)
            except (AuthError, PermissionError, QuotaExceededError, NotFoundError):
                # Эти ошибки не имеют смысла retry
                raise
            except Exception as e:
                last_exception = e
                
                if attempt == self.MAX_RETRIES:
                    raise
                
                # Экспоненциальная задержка с джиттером
                delay = min(self.BASE_DELAY * (2 ** attempt), self.MAX_DELAY)
                jitter = asyncio.get_event_loop().time() % 0.5
                await asyncio.sleep(delay + jitter)
        
        if last_exception:
            raise last_exception
    
    def _needs_streaming(self, file_size: int) -> bool:
        """
        Проверка необходимости streaming загрузки.
        
        Args:
            file_size: Размер файла в байтах.
            
        Returns:
            bool: True если файл больше порога streaming.
        """
        return file_size > self.STREAMING_THRESHOLD
    
    def _map_provider_error(self, status_code: int, error_body: str) -> StorageError:
        """
        Маппинг ошибок провайдера в человекочитаемые исключения.
        
        Args:
            status_code: HTTP статус код.
            error_body: Тело ответа с ошибкой.
            
        Returns:
            StorageError: Соответствующее исключение.
        """
        error_map = {
            401: AuthError("Неверные учетные данные или истекший токен"),
            403: PermissionError("Нет прав доступа к ресурсу"),
            404: NotFoundError("Ресурс не найден"),
            409: StorageError("Конфликт ресурсов"),
            413: StorageError("Файл слишком большой"),
            429: StorageError("Превышен лимит запросов. Повторите позже."),
            507: QuotaExceededError("Диск переполнен"),
        }
        
        if status_code in error_map:
            return error_map[status_code]
        elif 500 <= status_code < 600:
            return StorageError(f"Ошибка сервера провайдера ({status_code})")
        else:
            return StorageError(f"Ошибка провайдера ({status_code}): {error_body}")
