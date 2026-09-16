from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "kombain",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Настройка расписания (E2)
    beat_schedule={
        # Ежедневная очистка старых заданий в 3:00 UTC
        'cleanup-old-jobs-daily': {
            'task': 'app.workers.tasks.cleanup_old_jobs',
            'schedule': crontab(hour=3, minute=0),
            'args': (30,),  # grace-период 30 дней
        },
    },
    # Таймауты задач
    task_time_limit=3600,  # 1 час на выполнение
    task_soft_time_limit=3300,  # 55 минут мягкий лимит
)

# Автообнаружение задач
celery_app.autodiscover_tasks(['app.workers'])
