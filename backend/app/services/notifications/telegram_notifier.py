"""Telegram-уведомления через Bot API."""
import aiohttp
from typing import Dict, Any, Optional
from datetime import datetime

from .base import NotificationAdapter, NotificationResult


class TelegramNotifier(NotificationAdapter):
    """
    Адаптер для отправки уведомлений в Telegram.
    
    P0-объём:
    - sendMessage (текстовые уведомления об успехе/ошибке)
    - sendDocument (файлы до 50 МБ)
    - Проверка подключения
    """
    
    provider_name = "telegram"
    API_URL = "https://api.telegram.org/bot{token}/{method}"
    
    # Лимиты Telegram
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ
    RATE_LIMIT_PER_BOT = 30  # msg/s
    RATE_LIMIT_PER_CHAT = 1  # msg/s в один чат
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Инициализация Telegram-нотификатора.
        
        Args:
            credentials: {
                "bot_token": str,
                "chat_id": str (опционально, можно указывать при отправке)
            }
        """
        super().__init__(credentials)
        self.bot_token = credentials.get("bot_token", "")
        self.default_chat_id = credentials.get("chat_id", "")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получение HTTP-сессии."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Закрытие сессии."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _get_api_url(self, method: str) -> str:
        """Формирование URL API."""
        return self.API_URL.format(token=self.bot_token, method=method)
    
    async def send_message(self, recipient: str, text: str, 
                          parse_mode: str = "HTML") -> NotificationResult:
        """
        Отправка текстового сообщения.
        
        Args:
            recipient: Chat ID получателя.
            text: Текст сообщения (поддерживает HTML).
            parse_mode: Режим парсинга (HTML/Markdown).
            
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
            url = self._get_api_url("sendMessage")
            
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                
                if resp.status == 200 and data.get("ok"):
                    return NotificationResult(
                        success=True,
                        message="Сообщение отправлено",
                        recipient=chat_id,
                        sent_at=datetime.utcnow()
                    )
                else:
                    error_desc = data.get("description", "Неизвестная ошибка")
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
        Отправка файла (документа).
        
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
            # Проверка размера файла
            file_size = os.path.getsize(file_path)
            if file_size > self.MAX_FILE_SIZE:
                return NotificationResult(
                    success=False,
                    message=f"Файл слишком большой ({file_size} байт). Максимум {self.MAX_FILE_SIZE} байт",
                    recipient=chat_id,
                    error_code="FILE_TOO_LARGE"
                )
            
            session = await self._get_session()
            url = self._get_api_url("sendDocument")
            
            filename = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                document = aiohttp.FormData()
                document.add_field("chat_id", chat_id)
                document.add_field("document", f, filename=filename)
                if caption:
                    document.add_field("caption", caption)
                    document.add_field("parse_mode", "HTML")
                
                async with session.post(url, data=document) as resp:
                    data = await resp.json()
                    
                    if resp.status == 200 and data.get("ok"):
                        return NotificationResult(
                            success=True,
                            message=f"Файл {filename} отправлен",
                            recipient=chat_id,
                            sent_at=datetime.utcnow()
                        )
                    else:
                        error_desc = data.get("description", "Неизвестная ошибка")
                        return self._handle_error(error_desc, chat_id)
                        
        except FileNotFoundError:
            return NotificationResult(
                success=False,
                message="Файл не найден",
                recipient=chat_id,
                error_code="FILE_NOT_FOUND"
            )
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
    
    def _handle_error(self, error_desc: str, chat_id: str) -> NotificationResult:
        """Обработка ошибок Telegram API."""
        error_map = {
            "Unauthorized": ("Неверный токен бота", "BOT_AUTH_ERROR"),
            "Forbidden": ("Бот заблокирован пользователем", "BOT_BLOCKED"),
            "Chat not found": ("Чат не найден", "CHAT_NOT_FOUND"),
            "Rate limit exceeded": ("Превышен лимит сообщений", "RATE_LIMIT"),
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
            message=f"Ошибка Telegram: {error_desc}",
            recipient=chat_id,
            error_code="TELEGRAM_API_ERROR"
        )
    
    async def test(self) -> NotificationResult:
        """
        Проверка подключения к Telegram Bot API.
        
        Returns:
            NotificationResult: Результат тестирования.
        """
        try:
            session = await self._get_session()
            url = self._get_api_url("getMe")
            
            async with session.get(url) as resp:
                data = await resp.json()
                
                if resp.status == 200 and data.get("ok"):
                    bot_info = data.get("result", {})
                    bot_name = bot_info.get("username", "бот")
                    return NotificationResult(
                        success=True,
                        message=f"Telegram-бот @{bot_name} подключен",
                        recipient=self.default_chat_id or "test",
                        sent_at=datetime.utcnow()
                    )
                else:
                    error_desc = data.get("description", "Неизвестная ошибка")
                    return self._handle_error(error_desc, "test")
                    
        except Exception as e:
            return NotificationResult(
                success=False,
                message=f"Ошибка подключения: {str(e)}",
                recipient="test",
                error_code="TELEGRAM_TEST_ERROR"
            )
