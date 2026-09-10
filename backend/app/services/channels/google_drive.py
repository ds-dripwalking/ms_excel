"""Адаптер для Google Drive (Drive API v3)."""
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
    NotFoundError,
)


class GoogleDriveAdapter(BaseStorageAdapter):
    """
    Адаптер для Google Drive.
    
    Использует Drive API v3.
    OAuth scope: https://www.googleapis.com/auth/drive.file
    
    Поддерживает:
    - Resumable upload для больших файлов
    - Overwrite по имени файла
    - Публикацию ссылок (permissions: anyone with link)
    """
    
    BASE_URL = "https://www.googleapis.com"
    UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
    
    def __init__(self, credentials: Dict[str, Any]):
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
        """
        super().__init__(credentials)
        self._client: Optional[httpx.AsyncClient] = None
        self._access_token = credentials.get("access_token")
        self._refresh_token = credentials.get("refresh_token")
        self._token_expires_at = credentials.get("token_expires_at")
    
    async def connect(self) -> bool:
        """Установка соединения с Google Drive."""
        if not self._access_token:
            raise AuthError("Требуется access_token для подключения к Google Drive")
        
        # Проверка срока действия токена
        if self._token_expires_at:
            expires_at = datetime.fromisoformat(self._token_expires_at.replace('Z', '+00:00'))
            if datetime.now(expires_at.tzinfo) >= expires_at:
                await self._refresh_access_token()
        
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self._access_token}"},
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
                "https://oauth2.googleapis.com/token",
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
            
            # Обновляем credentials в памяти
            self._token_expires_at = datetime.now().isoformat()
            
            # Пересоздаем клиент с новым токеном
            if self._client:
                await self._client.aclose()
            
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
    
    async def test(self) -> bool:
        """Проверка подключения к Google Drive."""
        try:
            # Получаем информацию о диске
            response = await self._client.get("/drive/v3/about", params={"fields": "user"})
            if response.status_code == 401:
                await self._refresh_access_token()
                response = await self._client.get("/drive/v3/about", params={"fields": "user"})
            return response.status_code == 200
        except Exception:
            return False
    
    async def ensure_folder(self, path: str) -> str:
        """Создание папки (идемпотентно)."""
        parts = [p for p in path.split("/") if p]
        current_path = ""
        parent_id = None
        
        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else f"/{part}"
            
            # Проверяем, существует ли папка
            folder_id = await self._find_folder_by_name(part, parent_id)
            
            if folder_id:
                # Папка существует
                parent_id = folder_id
            else:
                # Создаем папку
                metadata = {
                    "name": part,
                    "mimeType": "application/vnd.google-apps.folder",
                }
                if parent_id:
                    metadata["parents"] = [parent_id]
                
                response = await self._client.post(
                    "/drive/v3/files",
                    json=metadata,
                    params={"fields": "id,name"},
                )
                
                if response.status_code != 200:
                    raise StorageError(f"Не удалось создать папку {current_path}: {response.status_code} {response.text}")
                
                data = response.json()
                parent_id = data["id"]
        
        return path
    
    async def _find_folder_by_name(self, name: str, parent_id: Optional[str]) -> Optional[str]:
        """Поиск папки по имени."""
        query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        
        response = await self._client.get(
            "/drive/v3/files",
            params={"q": query, "fields": "files(id,name)"},
        )
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        files = data.get("files", [])
        
        if files:
            return files[0]["id"]
        
        return None
    
    async def upload(
        self,
        stream: BinaryIO,
        path: str,
        overwrite: bool = True,
        filename: Optional[str] = None
    ) -> RemoteFileMeta:
        """Загрузка файла в Google Drive."""
        if not filename:
            filename = path.split("/")[-1]
        
        # Определяем parent folder
        folder_path = "/".join(path.split("/")[:-1])
        parent_id = None
        
        if folder_path:
            parent_id = await self._get_or_create_folder(folder_path)
        
        # Проверяем, существует ли файл (для overwrite)
        file_id = None
        if overwrite:
            file_id = await self._find_file_by_name(filename, parent_id)
        
        if file_id:
            # Обновляем существующий файл
            return await self._update_file(file_id, stream, filename)
        else:
            # Создаем новый файл
            return await self._create_file(stream, filename, parent_id)
    
    async def _get_or_create_folder(self, path: str) -> str:
        """Получение или создание папки по пути."""
        parts = [p for p in path.split("/") if p]
        parent_id = None
        
        for part in parts:
            folder_id = await self._find_folder_by_name(part, parent_id)
            
            if folder_id:
                parent_id = folder_id
            else:
                metadata = {
                    "name": part,
                    "mimeType": "application/vnd.google-apps.folder",
                }
                if parent_id:
                    metadata["parents"] = [parent_id]
                
                response = await self._client.post(
                    "/drive/v3/files",
                    json=metadata,
                    params={"fields": "id,name"},
                )
                
                if response.status_code != 200:
                    raise StorageError(f"Не удалось создать папку {part}: {response.status_code}")
                
                parent_id = response.json()["id"]
        
        return parent_id
    
    async def _find_file_by_name(self, name: str, parent_id: Optional[str]) -> Optional[str]:
        """Поиск файла по имени."""
        query = f"name='{name}' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        
        response = await self._client.get(
            "/drive/v3/files",
            params={"q": query, "fields": "files(id,name)"},
        )
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        files = data.get("files", [])
        
        if files:
            return files[0]["id"]
        
        return None
    
    async def _create_file(self, stream: BinaryIO, filename: str, parent_id: Optional[str]) -> RemoteFileMeta:
        """Создание нового файла (resumable upload)."""
        # Шаг 1: Инициируем resumable upload
        metadata = {"name": filename}
        if parent_id:
            metadata["parents"] = [parent_id]
        
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "application/octet-stream",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.UPLOAD_URL,
                params={"uploadType": "resumable"},
                headers=headers,
                json=metadata,
            )
            
            if response.status_code != 200:
                raise StorageError(f"Не удалось инициировать загрузку: {response.status_code}")
            
            upload_url = response.headers.get("Location")
            
            # Шаг 2: Загружаем файл
            file_content = stream.read()
            
            upload_response = await client.put(
                upload_url,
                content=file_content,
                headers={"Content-Length": str(len(file_content))},
            )
            
            if upload_response.status_code not in (200, 201):
                raise StorageError(f"Не удалось загрузить файл: {upload_response.status_code}")
            
            data = upload_response.json()
            
            return RemoteFileMeta(
                path=f"/{filename}",
                name=filename,
                size=data.get("size", len(file_content)),
                created_at=datetime.fromisoformat(data["createdTime"].replace("Z", "+00:00")) if data.get("createdTime") else datetime.now(),
                modified_at=datetime.fromisoformat(data["modifiedTime"].replace("Z", "+00:00")) if data.get("modifiedTime") else datetime.now(),
                public_url=None,
                mime_type=data.get("mimeType"),
            )
    
    async def _update_file(self, file_id: str, stream: BinaryIO, filename: str) -> RemoteFileMeta:
        """Обновление существующего файла."""
        file_content = stream.read()
        
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.UPLOAD_URL}/{file_id}",
                params={"uploadType": "media"},
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/octet-stream",
                },
                content=file_content,
            )
            
            if response.status_code not in (200, 201):
                raise StorageError(f"Не удалось обновить файл: {response.status_code}")
            
            data = response.json()
            
            return RemoteFileMeta(
                path=f"/{filename}",
                name=filename,
                size=data.get("size", len(file_content)),
                created_at=datetime.fromisoformat(data["createdTime"].replace("Z", "+00:00")) if data.get("createdTime") else datetime.now(),
                modified_at=datetime.fromisoformat(data["modifiedTime"].replace("Z", "+00:00")) if data.get("modifiedTime") else datetime.now(),
                public_url=None,
                mime_type=data.get("mimeType"),
            )
    
    async def publish(self, path: str) -> Optional[str]:
        """Публикация файла (создание публичной ссылки)."""
        # Находим файл по пути (упрощенно - ищем по имени в корне)
        filename = path.split("/")[-1]
        file_id = await self._find_file_by_name(filename, None)
        
        if not file_id:
            raise NotFoundError(f"Файл не найден: {path}")
        
        # Создаем permission: anyone with link can view
        response = await self._client.post(
            f"/drive/v3/files/{file_id}/permissions",
            json={"role": "reader", "type": "anyone"},
            params={"fields": "id"},
        )
        
        if response.status_code != 200:
            raise StorageError(f"Не удалось опубликовать файл: {response.status_code}")
        
        # Формируем публичную ссылку
        return f"https://drive.google.com/file/d/{file_id}/view"
    
    async def list(self, path: str) -> List[RemoteFolderItem]:
        """Список содержимого папки."""
        # Находим папку по пути
        folder_id = None
        if path != "/":
            folder_id = await self._get_or_create_folder(path)
        
        query = "trashed=false"
        if folder_id:
            query += f" and '{folder_id}' in parents"
        
        response = await self._client.get(
            "/drive/v3/files",
            params={
                "q": query,
                "fields": "files(id,name,mimeType,size,modifiedTime)",
                "pageSize": 1000,
            },
        )
        
        if response.status_code != 200:
            raise StorageError(f"Не удалось получить список: {response.status_code}")
        
        data = response.json()
        items = []
        
        for file in data.get("files", []):
            is_folder = file["mimeType"] == "application/vnd.google-apps.folder"
            
            items.append(RemoteFolderItem(
                name=file["name"],
                path=f"{path}/{file['name']}" if path != "/" else f"/{file['name']}",
                is_folder=is_folder,
                size=int(file["size"]) if file.get("size") else None,
                modified_at=datetime.fromisoformat(file["modifiedTime"].replace("Z", "+00:00")) if file.get("modifiedTime") else None,
            ))
        
        return items
    
    async def delete(self, path: str) -> bool:
        """Удаление файла или папки."""
        filename = path.split("/")[-1]
        file_id = await self._find_file_by_name(filename, None)
        
        if not file_id:
            return True  # Уже удалено
        
        response = await self._client.delete(f"/drive/v3/files/{file_id}")
        return response.status_code in (200, 204, 404)
    
    async def disconnect(self) -> None:
        """Закрытие соединения."""
        if self._client:
            await self._client.aclose()
            self._client = None
