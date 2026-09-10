"""Адаптер для Яндекс.Диска (REST API + WebDAV fallback)."""
import asyncio
from typing import Optional, BinaryIO, List, Dict, Any
from datetime import datetime
import httpx
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


class YandexDiskError(StorageError):
    """Базовое исключение для ошибок Яндекс.Диска."""
    pass


class YandexDiskAdapter(BaseStorageAdapter):
    """
    Адаптер для Яндекс.Диска.
    
    Поддерживает:
    - REST API (основной режим): полноценная работа с публикацией ссылок
    - WebDAV (fallback): простой режим для базовых операций
    
    OAuth scope: disk:read, disk:write (или disk:app_folder)
    """
    
    REST_BASE_URL = "https://cloud-api.yandex.net/v1/disk"
    WEBDAV_URL = "https://webdav.yandex.ru"
    
    def __init__(self, credentials: Dict[str, Any], use_webdav: bool = False):
        """
        Инициализация адаптера.
        
        Args:
            credentials: {
                "access_token": str,
                "refresh_token": str,
                "token_expires_at": str (ISO datetime),
                "client_id": str (опционально, для refresh),
                "client_secret": str (опционально, для refresh)
            }
            use_webdav: Если True, использовать WebDAV вместо REST API.
        """
        super().__init__(credentials)
        self.use_webdav = use_webdav
        self._client: Optional[httpx.AsyncClient] = None
        self._access_token = credentials.get("access_token")
        self._refresh_token = credentials.get("refresh_token")
        self._token_expires_at = credentials.get("token_expires_at")
    
    async def connect(self) -> bool:
        """Установка соединения с Яндекс.Диском."""
        if self.use_webdav:
            # WebDAV режим: используем логин + пароль приложения
            login = self.credentials.get("login")
            app_password = self.credentials.get("app_password")
            if not login or not app_password:
                raise AuthError("Для WebDAV требуются login и app_password")
            
            self._client = httpx.AsyncClient(
                base_url=self.WEBDAV_URL,
                auth=(login, app_password),
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
        else:
            # REST API режим: OAuth токен
            if not self._access_token:
                raise AuthError("Требуется access_token для REST API")
            
            # Проверка срока действия токена
            if self._token_expires_at:
                expires_at = datetime.fromisoformat(self._token_expires_at.replace('Z', '+00:00'))
                if datetime.now(expires_at.tzinfo) >= expires_at:
                    # Токен истек, пробуем refresh
                    await self._refresh_access_token()
            
            self._client = httpx.AsyncClient(
                base_url=self.REST_BASE_URL,
                headers={"Authorization": f"OAuth {self._access_token}"},
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
        
        return True
    
    async def _refresh_access_token(self):
        """Обновление OAuth токена."""
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")
        
        if not client_id or not client_secret or not self._refresh_token:
            raise AuthError("Невозможно обновить токен: отсутствуют client_id/client_secret/refresh_token")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth.yandex.ru/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            
            if response.status_code != 200:
                raise AuthError(f"Не удалось обновить токен: {response.text}")
            
            data = response.json()
            self._access_token = data["access_token"]
            self._refresh_token = data.get("refresh_token", self._refresh_token)
            
            # Обновляем credentials в памяти (но не в БД - это делает сервис)
            self._token_expires_at = datetime.now().isoformat()
            
            # Пересоздаем клиент с новым токеном
            if self._client:
                await self._client.aclose()
            
            self._client = httpx.AsyncClient(
                base_url=self.REST_BASE_URL,
                headers={"Authorization": f"OAuth {self._access_token}"},
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
    
    async def test(self) -> bool:
        """Проверка подключения к Яндекс.Диску."""
        try:
            if self.use_webdav:
                # WebDAV: OPTIONS запрос
                response = await self._client.options("/")
                return response.status_code in (200, 204)
            else:
                # REST: информация о диске
                response = await self._client.get("/v1/disk/")
                if response.status_code == 401:
                    # Пробуем refresh
                    await self._refresh_access_token()
                    response = await self._client.get("/v1/disk/")
                return response.status_code == 200
        except Exception:
            return False
    
    async def ensure_folder(self, path: str) -> str:
        """Создание папки (идемпотентно)."""
        if self.use_webdav:
            # WebDAV: MKCOL
            response = await self._client.mkcol(path)
            if response.status_code == 409:  # Conflict - папка уже существует
                return path
            elif response.status_code not in (200, 201, 204):
                raise StorageError(f"Не удалось создать папку {path}: {response.status_code}")
            return path
        else:
            # REST API: POST /resources
            response = await self._client.post(
                "/resources",
                params={"path": path},
            )
            if response.status_code == 409:  # Папка уже существует
                return path
            elif response.status_code not in (200, 201, 202):
                # Проверяем, не нужна ли авторизация
                if response.status_code == 401:
                    await self._refresh_access_token()
                    response = await self._client.post("/resources", params={"path": path})
                
                if response.status_code not in (200, 201, 202, 409):
                    raise StorageError(f"Не удалось создать папку {path}: {response.status_code} {response.text}")
            
            return path
    
    async def upload(
        self,
        stream: BinaryIO,
        path: str,
        overwrite: bool = True,
        filename: Optional[str] = None
    ) -> RemoteFileMeta:
        """Загрузка файла в Яндекс.Диск."""
        if self.use_webdav:
            return await self._upload_webdav(stream, path, overwrite, filename)
        else:
            return await self._upload_rest(stream, path, overwrite, filename)
    
    async def _upload_rest(
        self,
        stream: BinaryIO,
        path: str,
        overwrite: bool = True,
        filename: Optional[str] = None
    ) -> RemoteFileMeta:
        """Загрузка через REST API (двухэтапная: получение ссылки -> PUT)."""
        # Шаг 1: Получаем ссылку для загрузки
        response = await self._client.get(
            "/resources/upload",
            params={"path": path, "overwrite": str(overwrite).lower()},
        )
        
        if response.status_code == 401:
            await self._refresh_access_token()
            response = await self._client.get(
                "/resources/upload",
                params={"path": path, "overwrite": str(overwrite).lower()},
            )
        
        if response.status_code != 200:
            if response.status_code == 507:
                raise QuotaExceededError("Диск переполнен")
            raise StorageError(f"Не удалось получить ссылку для загрузки: {response.status_code} {response.text}")
        
        upload_data = response.json()
        upload_url = upload_data.get("href")
        method = upload_data.get("method", "PUT").upper()
        
        # Шаг 2: Загружаем файл по полученной ссылке
        file_content = stream.read()
        
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            upload_response = await self._client.request(
                method=method,
                url=upload_url,
                content=file_content,
                timeout=httpx.Timeout(300.0),
            )
            
            if upload_response.status_code in (200, 201, 204):
                break
            elif upload_response.status_code == 429:  # Rate limit
                retry_count += 1
                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                continue
            elif upload_response.status_code == 507:
                raise QuotaExceededError("Диск переполнен")
            else:
                retry_count += 1
                if retry_count >= max_retries:
                    raise StorageError(f"Не удалось загрузить файл: {upload_response.status_code} {upload_response.text}")
                await asyncio.sleep(2 ** retry_count)
        
        # Получаем метаданные загруженного файла
        return await self._get_file_meta(path)
    
    async def _upload_webdav(
        self,
        stream: BinaryIO,
        path: str,
        overwrite: bool = True,
        filename: Optional[str] = None
    ) -> RemoteFileMeta:
        """Загрузка через WebDAV (PUT)."""
        file_content = stream.read()
        
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
        if self.use_webdav:
            # WebDAV: PROPFIND
            response = await self._client.propfind(path)
            if response.status_code != 207:
                raise NotFoundError(f"Файл не найден: {path}")
            # Парсинг XML ответа (упрощенно)
            # В продакшене нужен полноценный XML парсер
            return RemoteFileMeta(
                path=path,
                name=path.split("/")[-1],
                size=0,  # Нужно парсить из XML
                created_at=datetime.now(),
                modified_at=datetime.now(),
            )
        else:
            # REST API: GET /resources
            response = await self._client.get("/resources", params={"path": path})
            
            if response.status_code == 404:
                raise NotFoundError(f"Файл не найден: {path}")
            elif response.status_code == 401:
                await self._refresh_access_token()
                response = await self._client.get("/resources", params={"path": path})
            elif response.status_code != 200:
                raise StorageError(f"Не удалось получить метаданные: {response.status_code}")
            
            data = response.json()
            
            public_url = None
            if data.get("public"):
                public_url = data.get("public_url")
            
            return RemoteFileMeta(
                path=path,
                name=data.get("name", path.split("/")[-1]),
                size=data.get("size", 0),
                created_at=datetime.fromisoformat(data["created"].replace("Z", "+00:00")) if data.get("created") else datetime.now(),
                modified_at=datetime.fromisoformat(data["modified"].replace("Z", "+00:00")) if data.get("modified") else datetime.now(),
                public_url=public_url,
                mime_type=data.get("mime_type"),
            )
    
    async def publish(self, path: str) -> Optional[str]:
        """Публикация файла (создание публичной ссылки)."""
        if self.use_webdav:
            # WebDAV не поддерживает публикацию
            return None
        
        # REST API: PATCH /resources
        response = await self._client.patch(
            "/resources",
            params={"path": path},
            json={"public": True},
        )
        
        if response.status_code == 401:
            await self._refresh_access_token()
            response = await self._client.patch(
                "/resources",
                params={"path": path},
                json={"public": True},
            )
        
        if response.status_code != 200:
            raise StorageError(f"Не удалось опубликовать файл: {response.status_code} {response.text}")
        
        data = response.json()
        return data.get("public_url")
    
    async def list(self, path: str) -> List[RemoteFolderItem]:
        """Список содержимого папки."""
        if self.use_webdav:
            # WebDAV: PROPFIND
            response = await self._client.propfind(path)
            if response.status_code != 207:
                raise NotFoundError(f"Папка не найдена: {path}")
            # Упрощенно - в продакшене нужен парсинг XML
            return []
        else:
            # REST API: GET /resources
            response = await self._client.get(
                "/resources",
                params={"path": path, "limit": 1000},
            )
            
            if response.status_code == 404:
                raise NotFoundError(f"Папка не найдена: {path}")
            elif response.status_code == 401:
                await self._refresh_access_token()
                response = await self._client.get(
                    "/resources",
                    params={"path": path, "limit": 1000},
                )
            elif response.status_code != 200:
                raise StorageError(f"Не удалось получить список: {response.status_code}")
            
            data = response.json()
            items = []
            
            for item in data.get("_embedded", {}).get("items", []):
                items.append(RemoteFolderItem(
                    name=item.get("name", ""),
                    path=item.get("path", ""),
                    is_folder=item.get("type") == "dir",
                    size=item.get("size"),
                    modified_at=datetime.fromisoformat(item["modified"].replace("Z", "+00:00")) if item.get("modified") else None,
                ))
            
            return items
    
    async def delete(self, path: str) -> bool:
        """Удаление файла или папки."""
        if self.use_webdav:
            response = await self._client.delete(path)
            return response.status_code in (200, 204, 404)  # 404 = уже удалено
        else:
            response = await self._client.delete(
                "/resources",
                params={"path": path, "permanently": "false"},
            )
            
            if response.status_code == 401:
                await self._refresh_access_token()
                response = await self._client.delete(
                    "/resources",
                    params={"path": path, "permanently": "false"},
                )
            
            return response.status_code in (200, 204, 404)
    
    async def disconnect(self) -> None:
        """Закрытие соединения."""
        if self._client:
            await self._client.aclose()
            self._client = None
