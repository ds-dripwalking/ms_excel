"""Сервис отправки уведомлений."""
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from .factory import NotificationFactory
from .base import NotificationResult

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Сервис для отправки уведомлений пользователям.
    
    Поддерживает множественные каналы (email, Telegram, MAX).
    """
    
    def __init__(self):
        self._notifiers: Dict[str, Any] = {}
    
    def register_notifier(self, channel_type: str, credentials: Dict[str, Any]):
        """
        Регистрация нотификатора.
        
        Args:
            channel_type: Тип канала (email, telegram, max).
            credentials: Учетные данные.
        """
        try:
            notifier = NotificationFactory.create(channel_type, credentials)
            self._notifiers[channel_type] = notifier
            logger.info(f"Зарегистрирован нотификатор {channel_type}")
        except ValueError as e:
            logger.error(f"Ошибка регистрации нотификатора {channel_type}: {e}")
    
    async def send_success_notification(
        self,
        channels: List[str],
        recipients: Dict[str, str],
        profile_name: str,
        rows_count: int,
        file_size: int,
        download_url: Optional[str] = None
    ) -> Dict[str, NotificationResult]:
        """
        Отправка уведомления об успешном экспорте.
        
        Args:
            channels: Список каналов для отправки.
            recipients: Получатели по каналам {channel_type: recipient}.
            profile_name: Имя профиля экспорта.
            rows_count: Количество строк в файле.
            file_size: Размер файла в байтах.
            download_url: Ссылка на скачивание (опционально).
            
        Returns:
            Dict[str, NotificationResult]: Результаты отправки по каналам.
        """
        results = {}
        
        message = (
            f"✅ <b>Экспорт выполнен успешно</b>\n\n"
            f"Профиль: {profile_name}\n"
            f"Строк: {rows_count:,}\n"
            f"Размер: {self._format_size(file_size)}\n"
        )
        
        if download_url:
            message += f"\n📥 <a href='{download_url}'>Скачать файл</a>"
        
        for channel in channels:
            if channel not in self._notifiers:
                logger.warning(f"Канал {channel} не зарегистрирован")
                continue
            
            recipient = recipients.get(channel)
            if not recipient:
                logger.warning(f"Не указан получатель для канала {channel}")
                continue
            
            notifier = self._notifiers[channel]
            result = await notifier.send_message(recipient, message)
            results[channel] = result
            
            if result.success:
                logger.info(f"Уведомление об успехе отправлено через {channel} → {recipient}")
            else:
                logger.error(f"Ошибка отправки уведомления через {channel}: {result.message}")
        
        return results
    
    async def send_error_notification(
        self,
        channels: List[str],
        recipients: Dict[str, str],
        profile_name: str,
        error_message: str
    ) -> Dict[str, NotificationResult]:
        """
        Отправка уведомления об ошибке экспорта.
        
        Args:
            channels: Список каналов для отправки.
            recipients: Получатели по каналам {channel_type: recipient}.
            profile_name: Имя профиля экспорта.
            error_message: Текст ошибки.
            
        Returns:
            Dict[str, NotificationResult]: Результаты отправки по каналам.
        """
        results = {}
        
        message = (
            f"❌ <b>Ошибка экспорта</b>\n\n"
            f"Профиль: {profile_name}\n"
            f"Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Ошибка: {error_message}\n\n"
            f"Проверьте настройки профиля и повторите попытку."
        )
        
        # Email-уведомления об ошибках (E5)
        for channel in channels:
            if channel not in self._notifiers:
                logger.warning(f"Канал {channel} не зарегистрирован")
                continue
            
            recipient = recipients.get(channel)
            if not recipient:
                logger.warning(f"Не указан получатель для канала {channel}")
                continue
            
            notifier = self._notifiers[channel]
            result = await notifier.send_message(recipient, message)
            results[channel] = result
            
            if result.success:
                logger.info(f"Уведомление об ошибке отправлено через {channel} → {recipient}")
            else:
                logger.error(f"Ошибка отправки уведомления через {channel}: {result.message}")
        
        return results
    
    async def test_channel(self, channel_type: str) -> NotificationResult:
        """
        Тестирование канала уведомлений.
        
        Args:
            channel_type: Тип канала для тестирования.
            
        Returns:
            NotificationResult: Результат теста.
        """
        if channel_type not in self._notifiers:
            return NotificationResult(
                success=False,
                message=f"Канал {channel_type} не зарегистрирован",
                recipient="test",
                error_code="CHANNEL_NOT_FOUND"
            )
        
        notifier = self._notifiers[channel_type]
        return await notifier.test()
    
    def _format_size(self, size_bytes: int) -> str:
        """Форматирование размера файла."""
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} ТБ"


# Глобальный экземпляр сервиса
notification_service = NotificationService()
