from app.workers.celery_app import celery_app


@celery_app.task
def example_task(x, y):
    return x + y
