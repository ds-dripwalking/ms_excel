"""Модуль уведомлений для пользователей."""
from .base import NotificationAdapter, NotificationResult
from .email_notifier import EmailNotifier
from .telegram_notifier import TelegramNotifier
from .max_notifier import MaxNotifier

__all__ = [
    "NotificationAdapter",
    "NotificationResult",
    "EmailNotifier",
    "TelegramNotifier",
    "MaxNotifier",
]
