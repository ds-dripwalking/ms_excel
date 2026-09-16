"""
Celery tasks for Kombain MVP.
Импортирует все задачи из модулей.
"""
from app.workers.celery_app import celery_app

# Автообнаружение задач
celery_app.autodiscover_tasks(['app.workers'])

# Импортируем задачи экспорта явно после autodiscover
# (чтобы избежать циклических импортов)

__all__ = [
    'run_export_task',
    'test_export_task',
    'cleanup_old_jobs',
]


@celery_app.task
def example_task(x, y):
    """Пример задачи."""
    return x + y
