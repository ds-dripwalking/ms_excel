"""Базовый интерфейс для адаптеров уведомлений."""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class NotificationResult:
    """Результат отправки уведомления."""
    success: bool
    message: str
    recipient: str
    sent_at: Optional[datetime] = None
    error_code: Optional[str] = None


class NotificationAdapter(ABC):
    """
    Базовый абстрактный класс для всех адаптеров уведомлений.
    
    Контракт интерфейса:
    - send_message(recipient, text) -> NotificationResult
    - send_file(recipient, file_path, caption) -> NotificationResult
    - test() -> NotificationResult (проверка подключения)
    """
    
    provider_name: str = "base"
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Инициализация адаптера.
        
        Args:
            credentials: Учетные данные (расшифрованные).
        """
        self.credentials = credentials
    
    @abstractmethod
    async def send_message(self, recipient: str, text: str) -> NotificationResult:
        """
        Отправка текстового сообщения.
        
        Args:
            recipient: Получатель (email, chat_id, etc.).
            text: Текст сообщения.
            
        Returns:
            NotificationResult: Результат отправки.
        """
        pass
    
    @abstractmethod
    async def send_file(self, recipient: str, file_path: str, caption: str = "") -> NotificationResult:
        """
        Отправка файла.
        
        Args:
            recipient: Получатель.
            file_path: Путь к файлу.
            caption: Подпись к файлу.
            
        Returns:
            NotificationResult: Результат отправки.
        """
        pass
    
    @abstractmethod
    async def test(self) -> NotificationResult:
        """
        Проверка подключения к сервису уведомлений.
        
        Returns:
            NotificationResult: Результат тестирования.
        """
        pass
