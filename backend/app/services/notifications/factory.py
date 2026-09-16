"""Фабрика нотификаторов."""
from typing import Dict, Any, Type
from .base import NotificationAdapter
from .email_notifier import EmailNotifier
from .telegram_notifier import TelegramNotifier
from .max_notifier import MaxNotifier


class NotificationFactory:
    """Фабрика для создания адаптеров уведомлений."""
    
    _adapters: Dict[str, Type[NotificationAdapter]] = {
        "email": EmailNotifier,
        "telegram": TelegramNotifier,
        "max": MaxNotifier,
    }
    
    @classmethod
    def create(cls, provider: str, credentials: Dict[str, Any]) -> NotificationAdapter:
        """
        Создание адаптера уведомлений.
        
        Args:
            provider: Тип провайдера (email, telegram, max).
            credentials: Учетные данные.
            
        Returns:
            NotificationAdapter: Экземпляр адаптера.
            
        Raises:
            ValueError: Если провайдер не поддерживается.
        """
        adapter_class = cls._adapters.get(provider)
        if not adapter_class:
            raise ValueError(f"Неподдерживаемый провайдер уведомлений: {provider}")
        return adapter_class(credentials)
    
    @classmethod
    def register(cls, provider: str, adapter_class: Type[NotificationAdapter]):
        """Регистрация кастомного адаптера."""
        cls._adapters[provider] = adapter_class
