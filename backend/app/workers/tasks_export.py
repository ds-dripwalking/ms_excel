"""
Задачи Celery для экспорта данных МойСклад.
Полный цикл: чтение → генерация → доставка → удаление временного файла.
"""
import os
import tempfile
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.database import get_db_session
from app.models.vendor import MoyskladAccount, IntegrationProfile, AccountStatus
from app.models.moysklad_api import ExportJob, JobEvent
from app.services.export.orders_export import OrdersExportService
from app.services.export.price_export import PriceExportService
from app.services.export.file_generators import FileFormat, FileGeneratorFactory
from app.services.channels.base import BaseStorageAdapter
from app.services.channels.yandex_disk import YandexDiskAdapter
from app.services.channels.mailru_cloud import MailRuCloudAdapter
from app.services.channels.google_drive import GoogleDriveAdapter
from app.crypto import encrypt_secret, decrypt_secret


class CryptoService:
    """Сервис шифрования/дешифрования для использования в задачах Celery."""
    
    def __init__(self):
        pass
    
    def encrypt_token(self, token: str) -> str:
        """Зашифровать токен."""
        return encrypt_secret({"data": token})
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """Расшифровать токен."""
        result = decrypt_secret(encrypted_token)
        return result.get("data", "")


logger = logging.getLogger(__name__)


def _get_account_status(session: Session, account_id: int) -> Optional[AccountStatus]:
    """Получить статус аккаунта."""
    account = session.query(MoyskladAccount).filter_by(id=account_id).first()
    if not account:
        return None
    return account.status


def _check_subscription_active(session: Session, account_id: int) -> tuple[bool, str]:
    """
    Проверить статус подписки перед запуском задачи.
    Возвращает (активна, сообщение).
    """
    account = session.query(MoyskladAccount).filter_by(id=account_id).first()
    if not account:
        return False, "Аккаунт не найден"
    
    if account.status == AccountStatus.SUSPENDED:
        return False, "Аккаунт приостановлен (Suspend)"
    
    if account.status == AccountStatus.DELETED_PENDING:
        return False, "Аккаунт помечен на удаление"
    
    if account.status == AccountStatus.DELETED:
        return False, "Аккаунт удалён"
    
    # Проверка даты окончания оплаченного периода
    now = datetime.utcnow()
    if account.paid_end_date and account.paid_end_date < now:
        # Триал или подписка истекли
        return False, f"Подписка истекла {account.paid_end_date.strftime('%Y-%m-%d')}"
    
    return True, "OK"


def _create_job_event(session: Session, job_id: int, event_type: str, message: str, details: Optional[Dict] = None):
    """Создать событие журнала задания."""
    event = JobEvent(
        job_id=job_id,
        event_type=event_type,
        message=message,
        details=details or {}
    )
    session.add(event)
    session.commit()


def _update_job_status(
    session: Session, 
    job_id: int, 
    status: str, 
    error_message: Optional[str] = None,
    result_file_path: Optional[str] = None,
    download_url: Optional[str] = None,
    records_processed: Optional[int] = None
):
    """Обновить статус задания."""
    job = session.query(ExportJob).filter_by(id=job_id).first()
    if not job:
        logger.error(f"Задание {job_id} не найдено")
        return
    
    job.status = status
    if error_message:
        job.error_message = error_message
    if result_file_path:
        job.result_file_path = result_file_path
    if download_url:
        job.download_url = download_url
    if records_processed is not None:
        job.records_processed = records_processed
    
    if status in ("completed", "failed", "cancelled"):
        job.completed_at = datetime.utcnow()
    
    session.commit()


def _get_export_service(module: str, session: Session, account_id: int, crypto_service: CryptoService):
    """Получить сервис экспорта по модулю."""
    if module == "orders":
        return OrdersExportService(session, account_id, crypto_service)
    elif module == "pricelist":
        return PriceExportService(session, account_id, crypto_service)
    else:
        raise ValueError(f"Неизвестный модуль экспорта: {module}")


def _get_storage_adapter(channel_type: str, credential_data: Dict, crypto_service: CryptoService) -> BaseStorageAdapter:
    """Получить адаптер хранилища по типу канала."""
    if channel_type == "yandex_disk":
        return YandexDiskAdapter(credential_data, crypto_service)
    elif channel_type == "mailru_cloud":
        return MailRuCloudAdapter(credential_data, crypto_service)
    elif channel_type == "google_drive":
        return GoogleDriveAdapter(credential_data, crypto_service)
    else:
        raise ValueError(f"Неизвестный тип канала: {channel_type}")


@celery_app.task(bind=True, max_retries=3)
def run_export_task(self, profile_id: int, job_id: int, account_id: int):
    """
    Основная задача экспорта.
    Полный цикл: чтение → генерация → доставка → удаление временного файла.
    """
    session = None
    temp_file_path = None
    
    try:
        session = next(get_db_session())
        
        # Проверка статуса аккаунта (G3, E8)
        is_active, status_message = _check_subscription_active(session, account_id)
        if not is_active:
            logger.warning(f"Задача {job_id} отменена: {status_message}")
            _update_job_status(session, job_id, "cancelled", error_message=status_message)
            _create_job_event(session, job_id, "cancelled", status_message)
            return {"status": "cancelled", "reason": status_message}
        
        # Обновление статуса задания
        _update_job_status(session, job_id, "running")
        _create_job_event(session, job_id, "started", "Запуск экспорта")
        
        # Получение профиля
        profile = session.query(IntegrationProfile).filter_by(id=profile_id).first()
        if not profile:
            raise ValueError(f"Профиль {profile_id} не найден")
        
        if not profile.is_active:
            raise ValueError("Профиль не активен")
        
        # Парсинг конфигураций
        import json
        fields_config = json.loads(profile.fields_config) if profile.fields_config else {}
        filters = json.loads(profile.filters) if profile.filters else {}
        format_config = json.loads(profile.format_config) if profile.format_config else {"format": "xlsx"}
        channel_config = json.loads(profile.channel_config) if profile.channel_config else {}
        
        # Получение сервиса экспорта
        crypto_service = CryptoService()
        export_service = _get_export_service(profile.module, session, account_id, crypto_service)
        
        # Чтение данных из МойСклад (с пагинацией и throttling)
        _create_job_event(session, job_id, "progress", "Чтение данных из МойСклад")
        data_rows, metadata = export_service.fetch_data(filters)
        
        if not data_rows:
            _update_job_status(session, job_id, "completed", records_processed=0)
            _create_job_event(session, job_id, "completed", "Нет данных для выгрузки")
            return {"status": "completed", "records": 0}
        
        # Генерация файла
        _create_job_event(session, job_id, "progress", f"Генерация файла формата {format_config.get('format', 'xlsx')}")
        file_format = FileFormat(format_config.get("format", "xlsx"))
        generator = FileGeneratorFactory.get_generator(file_format, fields_config, format_config)
        
        # Создание временного файла
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_format.extension}") as temp_file:
            temp_file_path = temp_file.name
        
        # Потоковая запись в файл
        record_count = generator.generate_file(data_rows, temp_file_path)
        
        _create_job_event(session, job_id, "progress", f"Сгенерировано {record_count} записей, размер: {os.path.getsize(temp_file_path)} байт")
        
        # Доставка файла в канал
        channel_type = channel_config.get("channel_type", "yandex_disk")
        credential_id = channel_config.get("credential_id")
        
        if credential_id:
            # Получение учётных данных из БД
            from app.models.cloud_storage import CloudCredential
            cred = session.query(CloudCredential).filter_by(id=credential_id, account_id=account_id).first()
            if not cred:
                raise ValueError(f"Учётные данные {credential_id} не найдены")
            
            cred_data = {
                "type": channel_type,
                "credential_id": cred.id,
                "encrypted_token": cred.encrypted_token,
                "folder_id": cred.folder_id,
            }
            
            storage_adapter = _get_storage_adapter(channel_type, cred_data, crypto_service)
            
            _create_job_event(session, job_id, "progress", "Загрузка файла в облачное хранилище")
            
            # Имя файла
            filename_template = channel_config.get("filename_template", "export_{timestamp}.{ext}")
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = filename_template.format(timestamp=timestamp, ext=file_format.extension)
            
            # Загрузка
            public_url = storage_adapter.upload_file(temp_file_path, filename, overwrite=True)
            
            _create_job_event(session, job_id, "progress", f"Файл загружен: {public_url}")
            
            # Обновление задания
            _update_job_status(
                session, job_id, "completed",
                result_file_path=temp_file_path,
                download_url=public_url,
                records_processed=record_count
            )
            _create_job_event(session, job_id, "completed", f"Экспорт завершён успешно", {"url": public_url})
            
            # Удаление временного файла (E7, GAP-09)
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                logger.info(f"Временный файл удалён: {temp_file_path}")
            
            return {"status": "completed", "records": record_count, "url": public_url}
        else:
            # Канал без учётных данных (например, file_link)
            _update_job_status(
                session, job_id, "completed",
                result_file_path=temp_file_path,
                records_processed=record_count
            )
            _create_job_event(session, job_id, "completed", "Экспорт завершён (файл локально)")
            
            # Временный файл не удаляем, если нет канала доставки
            # TODO: реализовать хранение временных файлов с TTL
            
            return {"status": "completed", "records": record_count, "file": temp_file_path}
    
    except Exception as exc:
        logger.exception(f"Ошибка экспорта: {exc}")
        _update_job_status(session, job_id, "failed", error_message=str(exc))
        _create_job_event(session, job_id, "failed", f"Ошибка: {str(exc)}")
        
        # Удаление временного файла при ошибке
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.info(f"Временный файл удалён после ошибки: {temp_file_path}")
        
        # Retry с экспоненциальной задержкой
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    
    finally:
        if session:
            session.close()


@celery_app.task(bind=True)
def test_export_task(self, profile_id: int, account_id: int):
    """
    Тестовый запуск экспорта (E4).
    Прогон на 10 строк без полной отправки.
    """
    session = None
    
    try:
        session = next(get_db_session())
        
        # Проверка статуса
        is_active, status_message = _check_subscription_active(session, account_id)
        if not is_active:
            return {"status": "cancelled", "reason": status_message}
        
        # Получение профиля
        profile = session.query(IntegrationProfile).filter_by(id=profile_id).first()
        if not profile:
            return {"status": "error", "message": f"Профиль {profile_id} не найден"}
        
        import json
        filters = json.loads(profile.filters) if profile.filters else {}
        
        # Ограничение 10 строками для теста
        filters["limit"] = 10
        
        crypto_service = CryptoService()
        export_service = _get_export_service(profile.module, session, account_id, crypto_service)
        
        # Чтение данных
        data_rows, metadata = export_service.fetch_data(filters)
        
        # Получение колонок из полей
        fields_config = json.loads(profile.fields_config) if profile.fields_config else {}
        columns = fields_config.get("order_fields", []) if profile.module == "orders" else fields_config.get("product_fields", [])
        
        return {
            "status": "success",
            "records": len(data_rows),
            "columns": columns,
            "sample": data_rows[:3] if data_rows else []
        }
    
    except Exception as exc:
        logger.exception(f"Ошибка теста: {exc}")
        return {"status": "error", "message": str(exc)}
    
    finally:
        if session:
            session.close()


@celery_app.task
def cleanup_old_jobs(days: int = 30):
    """
    Очистка старых заданий после grace-периода.
    """
    from datetime import timedelta
    session = None
    
    try:
        session = next(get_db_session())
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Удаление старых записей
        deleted_count = session.query(ExportJob).filter(
            ExportJob.created_at < cutoff_date
        ).delete(synchronize_session=False)
        
        session.commit()
        logger.info(f"Удалено {deleted_count} старых заданий")
        
        return {"deleted": deleted_count}
    
    except Exception as exc:
        logger.exception(f"Ошибка очистки: {exc}")
        if session:
            session.rollback()
        raise
    
    finally:
        if session:
            session.close()
