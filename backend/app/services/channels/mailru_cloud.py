"""Адаптер для Облака Mail.ru (WebDAV)."""
from typing import Optional, BinaryIO, List, Dict, Any
from datetime import datetime
import httpx
from app.services.channels.base import (
    BaseStorageAdapter,
    RemoteFileMeta,
    RemoteFolderItem,
    StorageError,
    AuthError,
    QuotaExceededError,
    NotFoundError,
)


class MailRuCloudAdapter(BaseStorageAdapter):
    """
    Адаптер для Облака Mail.ru (cloud.mail.ru).
    
    Использует WebDAV протокол.
    Аутентификация: логин + пароль приложения.
    
    Важно: это потребительское облако VK, а не VK Cloud (бизнес, S3).
    Публичные ссылки официально не поддерживаются через WebDAV.
    """
    
    WEBDAV_URL = "https://webdav.cloud.mail.ru"
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Инициализация адаптера.
        
        Args:
            credentials: {
                "login": str,  # e-mail или телефон
                "app_password": str  # пароль приложения (создается в настройках профиля)
            }
        """
        super().__init__(credentials)
        self._client: Optional[httpx.AsyncClient] = None
        self._login = credentials.get("login")
        self._app_password = credentials.get("app_password")
    
    async def connect(self) -> bool:
        """Установка соединения с Облаком Mail.ru."""
        if not self._login or not self._app_password:
            raise AuthError("Требуется login и app_password для подключения к Mail.ru Cloud")
        
        self._client = httpx.AsyncClient(
            base_url=self.WEBDAV_URL,
            auth=(self._login, self._app_password),
            timeout=httpx.Timeout(300.0, connect=10.0),
        )
        
        return True
    
    async def test(self) -> bool:
        """Проверка подключения к Облаку Mail.ru."""
        try:
            # WebDAV: OPTIONS запрос
            response = await self._client.options("/")
            return response.status_code in (200, 204)
        except Exception:
            return False
    
    async def ensure_folder(self, path: str) -> str:
        """Создание папки (идемпотентно)."""
        # WebDAV: MKCOL
        response = await self._client.mkcol(path)
        
        if response.status_code == 409:  # Conflict - папка уже существует
            return path
        elif response.status_code in (200, 201, 204):
            return path
        else:
            raise StorageError(f"Не удалось создать папку {path}: {response.status_code} {response.text}")
    
    async def upload(
        self,
        stream: BinaryIO,
        path: str,
        overwrite: bool = True,
        filename: Optional[str] = None
    ) -> RemoteFileMeta:
        """Загрузка файла в Облако Mail.ru."""
        file_content = stream.read()
        
        # WebDAV: PUT
        response = await self._client.put(path, content=file_content)
        
        if response.status_code == 429:
            raise StorageError("Превышен лимит запросов (Rate Limit)")
        elif response.status_code == 507:
            raise QuotaExceededError("Диск переполнен")
        elif response.status_code not in (200, 201, 204):
            raise StorageError(f"Не удалось загрузить файл: {response.status_code} {response.text}")
        
        return await self._get_file_meta(path)
    
    async def _get_file_meta(self, path: str) -> RemoteFileMeta:
        """Получение метаданных файла."""
        # WebDAV: PROPFIND
        response = await self._client.propfind(path)
        
        if response.status_code != 207:
            raise NotFoundError(f"Файл не найден: {path}")
        
        # Упрощенный парсинг XML ответа
        # В продакшене нужен полноценный XML парсер (xml.etree.ElementTree)
        return RemoteFileMeta(
            path=path,
            name=path.split("/")[-1],
            size=0,  # Нужно парсить из XML
            created_at=datetime.now(),
            modified_at=datetime.now(),
        )
    
    async def publish(self, path: str) -> Optional[str]:
        """
        Публикация файла (создание публичной ссылки).
        
        Облако Mail.ru официально не поддерживает создание публичных ссылок через WebDAV.
        
        Returns:
            None - публикация не поддерживается.
        """
        # Продуктовое решение: клиент может расшарить папку вручную в веб-UI
        # Возвращаем None, чтобы показать что публикация не поддерживается
        return None
    
    async def list(self, path: str) -> List[RemoteFolderItem]:
        """Список содержимого папки."""
        # WebDAV: PROPFIND
        response = await self._client.propfind(path)
        
        if response.status_code != 207:
            raise NotFoundError(f"Папка не найдена: {path}")
        
        # Упрощенный парсинг XML ответа
        # В продакшене нужен полноценный XML парсер
        return []
    
    async def delete(self, path: str) -> bool:
        """Удаление файла или папки."""
        response = await self._client.delete(path)
        return response.status_code in (200, 204, 404)  # 404 = уже удалено
    
    async def disconnect(self) -> None:
        """Закрытие соединения."""
        if self._client:
            await self._client.aclose()
            self._client = None
