"""MAX-уведомления через VK WorkSpace API."""
import aiohttp
from typing import Dict, Any, Optional
from datetime import datetime

from .base import NotificationAdapter, NotificationResult


class MaxNotifier(NotificationAdapter):
    """
    Адаптер для отправки уведомлений в MAX (VK WorkSpace).
    
    P0-объём:
    - Отправка текстовых сообщений об успехе/ошибке
    - Проверка подключения
    
    Лимиты:
    - 2 msg/s в чат
    - 30 rps общий
    """
    
    provider_name = "max"
    API_URL = "https://botapi.mcs.mail.ru/bot/v1"
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Инициализация MAX-нотификатора.
        
        Args:
            credentials: {
                "bot_token": str,
                "chat_id": str (опционально),
                "api_secret": str (для webhook validation)
            }
        """
        super().__init__(credentials)
        self.bot_token = credentials.get("bot_token", "")
        self.default_chat_id = credentials.get("chat_id", "")
        self.api_secret = credentials.get("api_secret", "")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получение HTTP-сессии."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-Max-Bot-Api-Secret": self.api_secret} if self.api_secret else {}
            )
        return self._session
    
    async def close(self):
        """Закрытие сессии."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _get_api_url(self, method: str) -> str:
        """Формирование URL API."""
        return f"{self.API_URL}/{method}"
    
    async def send_message(self, recipient: str, text: str) -> NotificationResult:
        """
        Отправка текстового сообщения.
        
        Args:
            recipient: Chat ID получателя.
            text: Текст сообщения.
            
        Returns:
            NotificationResult: Результат отправки.
        """
        chat_id = recipient or self.default_chat_id
        if not chat_id:
            return NotificationResult(
                success=False,
                message="Не указан chat_id",
                recipient=recipient,
                error_code="MISSING_CHAT_ID"
            )
        
        try:
            session = await self._get_session()
            url = self._get_api_url("messages")
            
            payload = {
                "chatId": chat_id,
                "text": {"body": text}
            }
            
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                
                if resp.status in (200, 202) and data.get("ok"):
                    return NotificationResult(
                        success=True,
                        message="Сообщение отправлено",
                        recipient=chat_id,
                        sent_at=datetime.utcnow()
                    )
                else:
                    error_desc = data.get("description", str(data))
                    return self._handle_error(error_desc, chat_id)
                    
        except aiohttp.ClientError as e:
            return NotificationResult(
                success=False,
                message=f"Сетевая ошибка: {str(e)}",
                recipient=chat_id,
                error_code="NETWORK_ERROR"
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                message=f"Неизвестная ошибка: {str(e)}",
                recipient=chat_id,
                error_code="UNKNOWN_ERROR"
            )
    
    async def send_file(self, recipient: str, file_path: str, 
                       caption: str = "") -> NotificationResult:
        """
        Отправка файла.
        
        Для MAX требуется двухэтапная загрузка:
        1. POST /uploads?type=file → токен
        2. Multipart upload
        3. POST /messages с attachments
        
        Args:
            recipient: Chat ID получателя.
            file_path: Путь к файлу.
            caption: Подпись к файлу.
            
        Returns:
            NotificationResult: Результат отправки.
        """
        import os
        chat_id = recipient or self.default_chat_id
        if not chat_id:
            return NotificationResult(
                success=False,
                message="Не указан chat_id",
                recipient=recipient,
                error_code="MISSING_CHAT_ID"
            )
        
        try:
            # Проверка размера файла (лимит MAX ~50 МБ)
            file_size = os.path.getsize(file_path)
            max_size = 50 * 1024 * 1024
            if file_size > max_size:
                return NotificationResult(
                    success=False,
                    message=f"Файл слишком большой ({file_size} байт). Максимум {max_size} байт",
                    recipient=chat_id,
                    error_code="FILE_TOO_LARGE"
                )
            
            session = await self._get_session()
            filename = os.path.basename(file_path)
            
            # Этап 1: Получение токена для загрузки
            uploads_url = self._get_api_url("uploads?type=file")
            async with session.post(uploads_url, json={"filename": filename}) as resp:
                upload_data = await resp.json()
                if resp.status != 200:
                    return self._handle_error("Не удалось получить токен загрузки", chat_id)
                
                upload_url = upload_data.get("url")
                attachment_token = upload_data.get("token")
            
            # Этап 2: Загрузка файла
            with open(file_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("file", f, filename=filename)
                
                async with session.put(upload_url, data=form) as resp:
                    if resp.status not in (200, 201, 204):
                        return self._handle_error("Ошибка загрузки файла", chat_id)
            
            # Этап 3: Отправка сообщения с вложением
            msg_url = self._get_api_url("messages")
            payload = {
                "chatId": chat_id,
                "text": {"body": caption} if caption else {"body": "Файл"},
                "attachments": [
                    {"type": "file", "payload": {"token": attachment_token}}
                ]
            }
            
            async with session.post(msg_url, json=payload) as resp:
                data = await resp.json()
                if resp.status in (200, 202) and data.get("ok"):
                    return NotificationResult(
                        success=True,
                        message=f"Файл {filename} отправлен",
                        recipient=chat_id,
                        sent_at=datetime.utcnow()
                    )
                else:
                    error_desc = data.get("description", str(data))
                    return self._handle_error(error_desc, chat_id)
                    
        except FileNotFoundError:
            return NotificationResult(
                success=False,
                message="Файл не найден",
                recipient=chat_id,
                error_code="FILE_NOT_FOUND"
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                message=f"Ошибка отправки файла: {str(e)}",
                recipient=chat_id,
                error_code="FILE_SEND_ERROR"
            )
    
    def _handle_error(self, error_desc: str, chat_id: str) -> NotificationResult:
        """Обработка ошибок MAX API."""
        error_map = {
            "Unauthorized": ("Неверный токен бота", "BOT_AUTH_ERROR"),
            "Forbidden": ("Доступ запрещён", "ACCESS_FORBIDDEN"),
            "Chat not found": ("Чат не найден", "CHAT_NOT_FOUND"),
            "Rate limit": ("Превышен лимит сообщений", "RATE_LIMIT"),
        }
        
        for key, (msg, code) in error_map.items():
            if key in error_desc:
                return NotificationResult(
                    success=False,
                    message=msg,
                    recipient=chat_id,
                    error_code=code
                )
        
        return NotificationResult(
            success=False,
            message=f"Ошибка MAX: {error_desc}",
            recipient=chat_id,
            error_code="MAX_API_ERROR"
        )
    
    async def test(self) -> NotificationResult:
        """
        Проверка подключения к MAX Bot API.
        
        Returns:
            NotificationResult: Результат тестирования.
        """
        try:
            session = await self._get_session()
            url = self._get_api_url("me")
            
            async with session.get(url) as resp:
                data = await resp.json()
                
                if resp.status == 200 and data.get("ok"):
                    bot_info = data.get("result", {})
                    bot_name = bot_info.get("name", "бот")
                    return NotificationResult(
                        success=True,
                        message=f"MAX-бот {bot_name} подключен",
                        recipient=self.default_chat_id or "test",
                        sent_at=datetime.utcnow()
                    )
                else:
                    error_desc = data.get("description", str(data))
                    return self._handle_error(error_desc, "test")
                    
        except Exception as e:
            return NotificationResult(
                success=False,
                message=f"Ошибка подключения: {str(e)}",
                recipient="test",
                error_code="MAX_TEST_ERROR"
            )
