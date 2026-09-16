"""
Адаптер для генерации секретных ссылок на файлы.
Файл хранится локально или в облаке, доступ предоставляется по временной подписанной ссылке.
"""
import os
import uuid
import time
import hashlib
import hmac
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from app.services.channels.base import BaseStorageAdapter, ChannelTestResult
from app.models.cloud_storage import CloudCredential


class FileLinkAdapter(BaseStorageAdapter):
    """Адаптер 'Файл + Секретная ссылка'."""

    provider_name = "file_link"
    
    def __init__(self, credentials: CloudCredential):
        # Базовый URL сервиса (где будет эндпоинт скачивания)
        self.base_url = credentials.decrypted_data.get("base_url", "http://localhost:8000")
        # Секретный ключ для подписи ссылок
        self.secret_key = credentials.decrypted_data.get("secret_key", "default-secret-key-change-in-production")
        # Время жизни ссылки по умолчанию (секунды)
        self.default_ttl = int(credentials.decrypted_data.get("default_ttl_seconds", 86400)) # 24 часа
        # Путь к директории хранения файлов (если локально)
        self.storage_path = credentials.decrypted_data.get("storage_path", "/tmp/kombain_exports")

    def _generate_token(self, file_id: str, expires_at: int) -> str:
        """Генерация подписанного токена."""
        message = f"{file_id}:{expires_at}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"{file_id}:{expires_at}:{signature}"

    def _verify_token(self, token: str) -> Optional[str]:
        """Проверка токена и возврат file_id если токен валиден."""
        try:
            parts = token.split(':')
            if len(parts) != 3:
                return None
            
            file_id, expires_at_str, signature = parts
            expires_at = int(expires_at_str)
            
            # Проверка времени
            if time.time() > expires_at:
                return None
            
            # Проверка подписи
            expected_message = f"{file_id}:{expires_at}"
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                expected_message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                return None
                
            return file_id
        except Exception:
            return None

    async def connect(self) -> bool:
        """Проверка доступности хранилища."""
        # Проверяем существование директории хранения
        if not os.path.exists(self.storage_path):
            try:
                os.makedirs(self.storage_path, exist_ok=True)
            except Exception:
                return False
        return True

    async def test(self) -> ChannelTestResult:
        """Тестирование подключения."""
        is_connected = await self.connect()
        if is_connected:
            return ChannelTestResult(success=True, message="Хранилище доступно")
        return ChannelTestResult(success=False, message="Не удалось получить доступ к хранилищу")

    async def ensure_folder(self, folder_path: str) -> bool:
        """Создание папки если не существует."""
        full_path = os.path.join(self.storage_path, folder_path)
        if not os.path.exists(full_path):
            try:
                os.makedirs(full_path, exist_ok=True)
            except Exception:
                return False
        return True

    async def upload(self, file_path: str, file_name: str, ttl_seconds: Optional[int] = None) -> Dict[str, Any]:
        """
        'Загрузка' файла - сохранение метаданных и генерация ссылки.
        Физически файл может остаться там, куда его записал генератор.
        Возвращает ссылку для скачивания.
        """
        if ttl_seconds is None:
            ttl_seconds = self.default_ttl
            
        file_id = str(uuid.uuid4())
        expires_at = int(time.time()) + ttl_seconds
        token = self._generate_token(file_id, expires_at)
        
        download_url = f"{self.base_url}/api/v1/channels/file_link/download?token={token}"
        
        # Сохраняем маппинг file_id -> реальный путь (в реальном приложении лучше в Redis/DB)
        # Для простоты создаем файл-метаданные
        meta_path = os.path.join(self.storage_path, f"{file_id}.meta")
        with open(meta_path, 'w') as f:
            f.write(f"{file_path}\n{file_name}\n{expires_at}")
            
        return {
            "success": True,
            "file_id": file_id,
            "download_url": download_url,
            "expires_at": datetime.fromtimestamp(expires_at).isoformat()
        }

    async def publish(self, file_id: str, public: bool = True) -> Optional[str]:
        """Публикация не нужна, ссылка уже является механизмом доступа."""
        return None

    async def list_files(self, folder_path: str = "") -> list:
        """Список файлов не поддерживается в этом адаптере."""
        return []

    async def delete(self, file_id: str) -> bool:
        """Удаление файла и метаданных."""
        meta_path = os.path.join(self.storage_path, f"{file_id}.meta")
        try:
            if os.path.exists(meta_path):
                # Читаем путь к реальному файлу
                with open(meta_path, 'r') as f:
                    real_path = f.readline().strip()
                if os.path.exists(real_path):
                    os.remove(real_path)
                os.remove(meta_path)
            return True
        except Exception:
            return False

    async def get_download_url(self, file_id: str, expires_in: int = 3600) -> str:
        """Генерация новой ссылки."""
        expires_at = int(time.time()) + expires_in
        token = self._generate_token(file_id, expires_at)
        return f"{self.base_url}/api/v1/channels/file_link/download?token={token}"
        
    async def get_file_path_by_token(self, token: str) -> Optional[str]:
        """Получение пути к файлу по токену (для использования в эндпоинте скачивания)."""
        file_id = self._verify_token(token)
        if not file_id:
            return None
            
        meta_path = os.path.join(self.storage_path, f"{file_id}.meta")
        if not os.path.exists(meta_path):
            return None
            
        try:
            with open(meta_path, 'r') as f:
                lines = f.readlines()
                if len(lines) >= 1:
                    return lines[0].strip()
        except Exception:
            return None
        return None
