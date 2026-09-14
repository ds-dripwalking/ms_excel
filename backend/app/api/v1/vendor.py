"""
Vendor API эндпоинты для интеграции с МойСклад.

Реализует жизненный цикл приложения в маркетплейсе МойСклад:
- Установка (Install)
- Возобновление (Resume)
- Смена тарифа (TariffChanged)
- Автопродление (Autoprolongation)
- Приостановка (Suspend)
- Удаление (Uninstall)
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.orm import Session
import jwt

from app.database import get_db
from app.models.vendor import (
    MoyskladAccount,
    AccountStatus,
    TariffType,
    CauseType,
)
from app.services.jwt_auth import (
    validate_mysklad_jwt,
    mark_jti_as_used,
    get_existing_jti,
    JWTValidationError,
)
from app.services.account_service import AccountService
from app.config import settings
from app.logging_config import logger


router = APIRouter(prefix="/api/moysklad/vendor/1.0", tags=["moysklad-vendor"])


def get_mysklad_secret_key() -> str:
    """Получает секретный ключ для проверки JWT от МойСклад."""
    # В production это должно быть из настроек
    secret = getattr(settings, 'MOYSKLAD_VENDOR_SECRET', None)
    if not secret:
        # Для разработки можно использовать дефолтное значение
        # В production обязательно настройте MOYSKLAD_VENDOR_SECRET
        secret = "dev-secret-key-change-in-production"
    return secret


async def verify_vendor_jwt(
    request: Request,
    db: Session = Depends(get_db),
    secret_key: str = Depends(get_mysklad_secret_key)
) -> Dict[str, Any]:
    """
    Зависимость для проверки JWT токена от МойСклад.
    
    Извлекает токен из заголовка Authorization и валидирует его.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Отсутствует или некорректный заголовок Authorization"
        )
    
    token = auth_header.split(" ", 1)[1]
    
    try:
        payload = validate_mysklad_jwt(token, secret_key, db)
        return payload
    except JWTValidationError as e:
        logger.warning(f"Ошибка валидации JWT: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Невалидный JWT токен: {str(e)}"
        )


@router.put("/apps/{app_id}/{account_id}")
async def activate_app(
    app_id: str,
    account_id: str,
    request: Request,
    db: Session = Depends(get_db),
    jwt_payload: Dict[str, Any] = Depends(verify_vendor_jwt),
    x_lognex_request_id: Optional[str] = Header(None, alias="X-Lognex-RequestId")
) -> Dict[str, str]:
    """
    Активация приложения.
    
    Обрабатывает следующие события:
    - Install: первая установка
    - Resume: возобновление после приостановки
    - TariffChanged: смена тарифа
    - Autoprolongation: автопродление
    
    Возвращает статус активации.
    """
    jti = jwt_payload.get("jti")
    
    # Проверяем, не был ли уже обработан этот jti (идемпотентность)
    existing_jti = get_existing_jti(db, jti)
    if existing_jti:
        logger.info(
            f"Повторный запрос с тем же jti",
            jti=jti,
            request_id=x_lognex_request_id,
            original_request_id=existing_jti.request_id
        )
        
        # Возвращаем предыдущий результат
        # Для простоты возвращаем Activated, в реальности нужно хранить результат
        return {"status": "Activated"}
    
    # Получаем тело запроса
    body = await request.json()
    cause = body.get("cause")
    
    logger.info(
        f"Активация приложения",
        app_id=app_id,
        account_id=account_id,
        cause=cause,
        jti=jti,
        request_id=x_lognex_request_id
    )
    
    account_service = AccountService(db)
    account = account_service.get_account(account_id, app_id)
    
    # Обрабатываем разные типы событий
    if cause == "Install":
        # Первая установка
        return await handle_install(
            db=db,
            account_service=account_service,
            app_id=app_id,
            account_id=account_id,
            body=body,
            jti=jti,
            request_id=x_lognex_request_id
        )
    elif cause == "Resume":
        # Возобновление после приостановки
        return await handle_resume(
            db=db,
            account_service=account_service,
            account=account,
            body=body,
            jti=jti,
            request_id=x_lognex_request_id
        )
    elif cause == "TariffChanged":
        # Смена тарифа
        return await handle_tariff_changed(
            db=db,
            account_service=account_service,
            account=account,
            body=body,
            jti=jti,
            request_id=x_lognex_request_id
        )
    elif cause == "Autoprolongation":
        # Автопродление
        return await handle_autoprolongation(
            db=db,
            account_service=account_service,
            account=account,
            body=body,
            jti=jti,
            request_id=x_lognex_request_id
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неизвестный тип события: {cause}"
        )


async def handle_install(
    db: Session,
    account_service: AccountService,
    app_id: str,
    account_id: str,
    body: Dict[str, Any],
    jti: str,
    request_id: Optional[str]
) -> Dict[str, str]:
    """
    Обработка первой установки приложения.
    
    Действия:
    1. Создать аккаунт.
    2. Сохранить зашифрованный токен JSON API.
    3. Сохранить подписку.
    4. Остановить задачи, если были.
    5. Вернуть status: SettingsRequired.
    """
    # Получаем токен из тела запроса
    token = body.get("token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Отсутствует токен в запросе"
        )
    
    # Создаём новый аккаунт
    account = account_service.create_account(
        account_id=account_id,
        app_id=app_id,
        tariff=TariffType.LITE  # По умолчанию Lite
    )
    
    # Сохраняем токен
    account_service.update_token(account, token)
    
    # Обновляем информацию о подписке
    subscription = body.get("subscription", {})
    if subscription:
        tariff_name = subscription.get("tariffPlanName", "").lower()
        if "professional" in tariff_name:
            account_service.update_tariff(account, TariffType.PROFESSIONAL)
        
        # Обновляем дату окончания оплаченного периода
        paid_end_str = subscription.get("paidEndDate")
        if paid_end_str:
            try:
                paid_end_date = datetime.fromisoformat(paid_end_str.replace('Z', '+00:00'))
                account_service.update_paid_end_date(account, paid_end_date)
            except ValueError:
                logger.warning(f"Некорректная дата paidEndDate: {paid_end_str}")
    
    # Отмечаем jti как использованный
    mark_jti_as_used(
        db=db,
        jti=jti,
        request_id=request_id,
        operation_type="Install",
        account_id=account_id
    )
    
    logger.info(
        f"Приложение установлено, требуется настройка",
        account_id=account_id,
        app_id=app_id
    )
    
    # Пользователь должен настроить первый профиль
    return {"status": "SettingsRequired"}


async def handle_resume(
    db: Session,
    account_service: AccountService,
    account: Optional[MoyskladAccount],
    body: Dict[str, Any],
    jti: str,
    request_id: Optional[str]
) -> Dict[str, str]:
    """
    Обработка возобновления после приостановки.
    
    Действия:
    1. Обновить токен.
    2. Восстановить настройки.
    3. Проверить подписку.
    4. Запустить планировщик.
    5. Вернуть status: Activated.
    """
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Аккаунт не найден"
        )
    
    # Обновляем токен
    token = body.get("token")
    if token:
        account_service.update_token(account, token)
    
    # Активируем аккаунт
    account_service.activate_account(account)
    
    # Обновляем информацию о подписке
    subscription = body.get("subscription", {})
    if subscription:
        tariff_name = subscription.get("tariffPlanName", "").lower()
        if "professional" in tariff_name:
            account_service.update_tariff(account, TariffType.PROFESSIONAL)
        else:
            account_service.update_tariff(account, TariffType.LITE)
        
        paid_end_str = subscription.get("paidEndDate")
        if paid_end_str:
            try:
                paid_end_date = datetime.fromisoformat(paid_end_str.replace('Z', '+00:00'))
                account_service.update_paid_end_date(account, paid_end_date)
            except ValueError:
                logger.warning(f"Некорректная дата paidEndDate: {paid_end_str}")
    
    # TODO: Запустить планировщик задач
    # scheduler.resume(account.id)
    
    # Отмечаем jti как использованный
    mark_jti_as_used(
        db=db,
        jti=jti,
        request_id=request_id,
        operation_type="Resume",
        account_id=account.account_id
    )
    
    logger.info(
        f"Приложение возобновлено",
        account_id=account.account_id
    )
    
    return {"status": "Activated"}


async def handle_tariff_changed(
    db: Session,
    account_service: AccountService,
    account: Optional[MoyskladAccount],
    body: Dict[str, Any],
    jti: str,
    request_id: Optional[str]
) -> Dict[str, str]:
    """
    Обработка смены тарифа.
    
    Действия:
    1. Обновить тариф.
    2. Применить ограничения:
       - Lite — один модуль, до 3 профилей;
       - Professional — без ограничений.
    3. Вернуть status: Activated.
    """
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Аккаунт не найден"
        )
    
    # Определяем новый тариф
    subscription = body.get("subscription", {})
    tariff_name = subscription.get("tariffPlanName", "").lower()
    
    if "professional" in tariff_name:
        new_tariff = TariffType.PROFESSIONAL
    else:
        new_tariff = TariffType.LITE
    
    # Обновляем тариф
    account_service.update_tariff(account, new_tariff)
    
    # Проверяем лимит профилей для Lite тарифа
    if new_tariff == TariffType.LITE:
        profile_count = account_service.count_active_profiles(account)
        if not account_service.check_profile_limit(account, profile_count):
            logger.warning(
                f"Превышен лимит профилей для Lite тарифа",
                account_id=account.account_id,
                profile_count=profile_count
            )
            # Можно добавить логику отключения лишних профилей
    
    # Отмечаем jti как использованный
    mark_jti_as_used(
        db=db,
        jti=jti,
        request_id=request_id,
        operation_type="TariffChanged",
        account_id=account.account_id
    )
    
    logger.info(
        f"Тариф изменён",
        account_id=account.account_id,
        new_tariff=new_tariff.value
    )
    
    return {"status": "Activated"}


async def handle_autoprolongation(
    db: Session,
    account_service: AccountService,
    account: Optional[MoyskladAccount],
    body: Dict[str, Any],
    jti: str,
    request_id: Optional[str]
) -> Dict[str, str]:
    """
    Обработка автопродления.
    
    Действия:
    1. Обновить paid_end_date.
    2. Разблокировать задачи, если были заблокированы.
    3. Вернуть status: Activated.
    """
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Аккаунт не найден"
        )
    
    # Обновляем дату окончания оплаченного периода
    subscription = body.get("subscription", {})
    paid_end_str = subscription.get("paidEndDate")
    
    if paid_end_str:
        try:
            paid_end_date = datetime.fromisoformat(paid_end_str.replace('Z', '+00:00'))
            account_service.update_paid_end_date(account, paid_end_date)
        except ValueError:
            logger.warning(f"Некорректная дата paidEndDate: {paid_end_str}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Некорректная дата paidEndDate: {paid_end_str}"
            )
    
    # Если аккаунт был приостановлен, активируем его
    if account.status == AccountStatus.SUSPENDED:
        account_service.activate_account(account)
    
    # TODO: Разблокировать задачи
    # scheduler.unblock_tasks(account.id)
    
    # Отмечаем jti как использованный
    mark_jti_as_used(
        db=db,
        jti=jti,
        request_id=request_id,
        operation_type="Autoprolongation",
        account_id=account.account_id
    )
    
    logger.info(
        f"Автопродление выполнено",
        account_id=account.account_id,
        paid_end_date=paid_end_str
    )
    
    return {"status": "Activated"}


@router.delete("/apps/{app_id}/{account_id}")
async def deactivate_app(
    app_id: str,
    account_id: str,
    request: Request,
    db: Session = Depends(get_db),
    jwt_payload: Dict[str, Any] = Depends(verify_vendor_jwt),
    x_lognex_request_id: Optional[str] = Header(None, alias="X-Lognex-RequestId")
) -> Dict[str, str]:
    """
    Деактивация приложения.
    
    Обрабатывает следующие события:
    - Suspend: приостановка из-за неоплаты
    - Uninstall: удаление приложения
    
    Возвращает статус деактивации.
    """
    jti = jwt_payload.get("jti")
    
    # Проверяем, не был ли уже обработан этот jti (идемпотентность)
    existing_jti = get_existing_jti(db, jti)
    if existing_jti:
        logger.info(
            f"Повторный запрос с тем же jti",
            jti=jti,
            request_id=x_lognex_request_id,
            original_request_id=existing_jti.request_id
        )
        
        # Возвращаем предыдущий результат
        return {"status": "Deactivated"}
    
    # Получаем тело запроса
    body = await request.json()
    cause = body.get("cause")
    
    logger.info(
        f"Деактивация приложения",
        app_id=app_id,
        account_id=account_id,
        cause=cause,
        jti=jti,
        request_id=x_lognex_request_id
    )
    
    account_service = AccountService(db)
    account = account_service.get_account(account_id, app_id)
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Аккаунт не найден"
        )
    
    # Обрабатываем разные типы событий
    if cause == "Suspend":
        return await handle_suspend(
            db=db,
            account_service=account_service,
            account=account,
            jti=jti,
            request_id=x_lognex_request_id
        )
    elif cause == "Uninstall":
        return await handle_uninstall(
            db=db,
            account_service=account_service,
            account=account,
            jti=jti,
            request_id=x_lognex_request_id
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неизвестный тип события: {cause}"
        )


async def handle_suspend(
    db: Session,
    account_service: AccountService,
    account: MoyskladAccount,
    jti: str,
    request_id: Optional[str]
) -> Dict[str, str]:
    """
    Обработка приостановки из-за неоплаты.
    
    Действия:
    1. Остановить планировщик.
    2. Запретить ручной запуск.
    3. Сохранить профили.
    4. Сохранить журнал.
    5. Не удалять токены облаков сразу.
    6. Поставить статус suspended.
    """
    # Приостанавливаем аккаунт
    account_service.suspend_account(account)
    
    # TODO: Остановить планировщик задач
    # scheduler.pause(account.id)
    
    # TODO: Запретить ручной запуск
    # tasks.disable_manual_start(account.id)
    
    # Профили и токены сохраняются
    
    # Отмечаем jti как использованный
    mark_jti_as_used(
        db=db,
        jti=jti,
        request_id=request_id,
        operation_type="Suspend",
        account_id=account.account_id
    )
    
    logger.warning(
        f"Приложение приостановлено",
        account_id=account.account_id
    )
    
    return {"status": "Deactivated"}


async def handle_uninstall(
    db: Session,
    account_service: AccountService,
    account: MoyskladAccount,
    jti: str,
    request_id: Optional[str]
) -> Dict[str, str]:
    """
    Обработка удаления приложения.
    
    Действия:
    1. Остановить задачи.
    2. Пометить аккаунт как deleted_pending.
    3. Запустить очистку через grace-период (30 дней).
    4. После grace-периода удалить:
       - токены;
       - секреты;
       - настройки;
       - файлы временных выгрузок.
    """
    # TODO: Остановить все задачи
    # scheduler.stop_all_tasks(account.id)
    
    # Помечаем аккаунт на удаление через 30 дней
    account_service.mark_for_deletion(account, grace_period_days=30)
    
    # Отмечаем jti как использованный
    mark_jti_as_used(
        db=db,
        jti=jti,
        request_id=request_id,
        operation_type="Uninstall",
        account_id=account.account_id
    )
    
    logger.warning(
        f"Приложение помечено на удаление",
        account_id=account.account_id,
        deletion_date=account.deleted_at.isoformat() if account.deleted_at else "N/A"
    )
    
    return {"status": "Deactivated"}
