"""Универсальный S3-адаптер для совместимых хранилищ."""
import asyncio
from typing import Optional, BinaryIO, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
import hashlib
import hmac
import base64
import urllib.parse
from app.services.channels.base import (
    BaseStorageAdapter,
    RemoteFileMeta,
    RemoteFolderItem,
    StorageError,
    AuthError,
    NotFoundError,
)


@dataclass
class S3Object:
    """S3 объект."""
    key: str
    size: int
    last_modified: datetime
    etag: str


class S3CompatibleAdapter(BaseStorageAdapter):
    """
    Универсальный S3-адаптер.
    
    Поддерживает:
    - VK Cloud (s3.vkcloudstorage.ru)
    - MTS Cloud (s3.mts-cloud.ru)
    - Yandex Object Storage (storage.yandexcloud.net)
    - Любой AWS S3-compatible storage (MinIO, Selectel, etc.)
    
    Auth: AWS Signature V4
    """
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Инициализация адаптера.
        
        Args:
            credentials: {
                "endpoint": str,  # https://s3.vkcloudstorage.ru
                "bucket": str,
                "access_key": str,
                "secret_key": str,
                "region": str (опционально, по умолчанию "ru-central1")
            }
        """
        super().__init__(credentials)
        self._endpoint = credentials.get("endpoint", "").rstrip("/")
        self._bucket = credentials.get("bucket")
        self._access_key = credentials.get("access_key")
        self._secret_key = credentials.get("secret_key")
        self._region = credentials.get("region", "ru-central1")
        
        if not all([self._endpoint, self._bucket, self._access_key, self._secret_key]):
            raise AuthError("Требуется endpoint, bucket, access_key и secret_key для S3")
    
    async def connect(self) -> bool:
        """Проверка подключения к S3."""
        try:
            return await self.test()
        except Exception:
            return False
    
    async def test(self) -> bool:
        """Проверка подключения через list_objects."""
        try:
            import httpx
            url = f"{self._endpoint}/{self._bucket}"
            
            headers = self._get_s3_headers("GET", "/", "")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params={"list-type": "2", "max-keys": "1"})
                return response.status_code in (200, 404)  # 404 = bucket пуст, но подключен
        except Exception:
            return False
    
    def _get_s3_headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """Генерация заголовков AWS Signature V4."""
        import hashlib
        import hmac
        from datetime import datetime
        
        now = datetime.utcnow()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        
        # Хэш тела запроса
        payload_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()
        
        # Канонический запрос
        canonical_uri = f"/{self._bucket}{path}"
        canonical_querystring = ""
        canonical_headers = f"host:{urllib.parse.urlparse(self._endpoint).netloc}\nx-amz-date:{amz_date}\n"
        signed_headers = "host;x-amz-date"
        
        canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        
        # Строка для подписи
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self._region}/s3/aws4_request"
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        
        # Вычисление подписи
        def sign(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
        
        k_date = sign(("AWS4" + self._secret_key).encode('utf-8'), date_stamp)
        k_region = sign(k_date, self._region)
        k_service = sign(k_region, "s3")
        k_signing = sign(k_service, "aws4_request")
        signature = sign(k_signing, string_to_sign).hex()
        
        # Заголовок авторизации
        authorization = f"{algorithm} Credential={self._access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
        
        return {
            "Authorization": authorization,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
    
    async def ensure_folder(self, path: str) -> str:
        """Создание папки (в S3 это ключ с суффиксом /)."""
        # В S3 папки не существуют явно, создаем placeholder
        folder_key = path.rstrip("/") + "/"
        
        import httpx
        url = f"{self._endpoint}/{self._bucket}/{folder_key}"
        headers = self._get_s3_headers("PUT", f"/{self._bucket}/{folder_key}", "")
        
        async with httpx.AsyncClient() as client:
            response = await client.put(url, headers=headers, content=b"")
            
            if response.status_code not in (200, 201):
                raise StorageError(f"Не удалось создать папку {path}: {response.status_code}")
        
        return path
    
    async def upload(
        self,
        stream: BinaryIO,
        path: str,
        overwrite: bool = True,
        filename: Optional[str] = None
    ) -> RemoteFileMeta:
        """Загрузка файла в S3."""
        import httpx
        
        key = path.lstrip("/")
        file_content = stream.read()
        
        url = f"{self._endpoint}/{self._bucket}/{key}"
        headers = self._get_s3_headers("PUT", f"/{self._bucket}/{key}", "")
        headers["Content-Type"] = "application/octet-stream"
        
        async with httpx.AsyncClient() as client:
            response = await client.put(url, headers=headers, content=file_content)
            
            if response.status_code not in (200, 201):
                raise StorageError(f"Не удалось загрузить файл: {response.status_code} {response.text}")
        
        # Получаем метаданные
        return await self._get_object_meta(key)
    
    async def _get_object_meta(self, key: str) -> RemoteFileMeta:
        """Получение метаданных объекта."""
        import httpx
        
        url = f"{self._endpoint}/{self._bucket}/{key}"
        headers = self._get_s3_headers("HEAD", f"/{self._bucket}/{key}", "")
        
        async with httpx.AsyncClient() as client:
            response = await client.head(url, headers=headers)
            
            if response.status_code != 200:
                raise NotFoundError(f"Объект не найден: {key}")
            
            size = int(response.headers.get("content-length", 0))
            last_modified = response.headers.get("last-modified", "")
            etag = response.headers.get("etag", "").strip('"')
            
            # Парсинг даты
            try:
                modified_at = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S GMT")
            except Exception:
                modified_at = datetime.now()
            
            return RemoteFileMeta(
                path=f"/{key}",
                name=key.split("/")[-1],
                size=size,
                created_at=modified_at,
                modified_at=modified_at,
                public_url=f"{url}",
            )
    
    async def publish(self, path: str) -> Optional[str]:
        """
        Публикация файла.
        
        Для S3 требуется настройка bucket policy на стороне провайдера.
        Возвращаем постоянную URL объекта.
        """
        key = path.lstrip("/")
        return f"{self._endpoint}/{self._bucket}/{key}"
    
    async def list(self, path: str) -> List[RemoteFolderItem]:
        """Список объектов в 'папке'."""
        import httpx
        import xml.etree.ElementTree as ET
        
        prefix = path.lstrip("/").rstrip("/") + "/" if path != "/" else ""
        
        url = f"{self._endpoint}/{self._bucket}"
        headers = self._get_s3_headers("GET", f"/{self._bucket}", "")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=headers,
                params={"prefix": prefix, "delimiter": "/", "max-keys": "1000"},
            )
            
            if response.status_code != 200:
                raise StorageError(f"Не удалось получить список: {response.status_code}")
            
            # Парсинг XML ответа
            root = ET.fromstring(response.content)
            ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
            
            items = []
            
            # Common prefixes (subfolders)
            for cp in root.findall(".//s3:CommonPrefixes/s3:Prefix", ns):
                prefix_path = cp.text.rstrip("/")
                items.append(RemoteFolderItem(
                    name=prefix_path.split("/")[-1] if prefix_path else "",
                    path=f"/{prefix_path}",
                    is_folder=True,
                ))
            
            # Objects
            for obj in root.findall(".//s3:Contents", ns):
                key = obj.find("s3:Key", ns).text
                size = int(obj.find("s3:Size", ns).text)
                last_modified = obj.find("s3:LastModified", ns).text
                
                try:
                    modified_at = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                except Exception:
                    modified_at = datetime.now()
                
                # Пропускаем placeholder папок
                if key.endswith("/"):
                    continue
                
                items.append(RemoteFolderItem(
                    name=key.split("/")[-1],
                    path=f"/{key}",
                    is_folder=False,
                    size=size,
                    modified_at=modified_at,
                ))
            
            return items
    
    async def delete(self, path: str) -> bool:
        """Удаление объекта."""
        import httpx
        
        key = path.lstrip("/")
        url = f"{self._endpoint}/{self._bucket}/{key}"
        headers = self._get_s3_headers("DELETE", f"/{self._bucket}/{key}", "")
        
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, headers=headers)
            return response.status_code in (200, 204, 404)
    
    async def disconnect(self) -> None:
        """Закрытие соединения (no-op для S3)."""
        pass
