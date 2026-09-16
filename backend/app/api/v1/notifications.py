"""API для управления уведомлениями."""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.vendor import MoyskladAccount
from app.services.notifications.service import notification_service
from app.services.notifications.base import NotificationResult


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/test/{channel_type}")
async def test_notification_channel(
    channel_type: str,
    db: Session = Depends(get_db),
    current_account: MoyskladAccount = Depends()  # TODO: добавить auth
) -> Dict[str, Any]:
    """
    Тестирование канала уведомлений.
    
    Args:
        channel_type: Тип канала (email, telegram, max).
        
    Returns:
        Результат тестирования.
    """
    # Получение учетных данных из аккаунта
    # TODO: реализовать получение credentials из БД
    
    try:
        result = await notification_service.test_channel(channel_type)
        return {
            "success": result.success,
            "message": result.message,
            "sent_at": result.sent_at.isoformat() if result.sent_at else None
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка тестирования канала: {str(e)}"
        )


# TODO: Добавить endpoint для регистрации нотификаторов
# TODO: Добавить endpoint для настройки получателей уведомлений
