"""
API для управления профилями выгрузки.
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_async_db
from app.models.vendor import IntegrationProfile, MoyskladAccount
from app.models.moysklad_api import ExportJob
from app.schemas import ProfileCreate, ProfileUpdate, ProfileResponse, ExportJobResponse
from app.api.v1.auth import get_current_user_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


async def get_account_from_context(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
) -> MoyskladAccount:
    """Получает аккаунт из токена авторизации."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Отсутствует токен авторизации"
        )
    
    token = auth_header.split(" ", 1)[1]
    context = await get_current_user_context(token, db)
    
    result = await db.execute(
        select(MoyskladAccount).where(MoyskladAccount.id == context["account_uuid"])
    )
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Аккаунт не найден"
        )
    
    return account


@router.get("", response_model=List[ProfileResponse])
async def list_profiles(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    account: MoyskladAccount = Depends(get_account_from_context),
    is_active: Optional[bool] = None
) -> List[ProfileResponse]:
    """Список всех профилей аккаунта."""
    query = select(IntegrationProfile).where(
        IntegrationProfile.account_id == account.id
    )
    
    if is_active is not None:
        query = query.where(IntegrationProfile.is_active == is_active)
    
    result = await db.execute(query.order_by(IntegrationProfile.created_at.desc()))
    profiles = result.scalars().all()
    
    import json
    
    return [
        ProfileResponse(
            id=p.id,
            account_id=p.account_id,
            name=p.name,
            module=p.module,
            fields_config=json.loads(p.fields_config) if p.fields_config else None,
            filters=json.loads(p.filters) if p.filters else None,
            format_config=json.loads(p.format_config) if p.format_config else None,
            channel_config=json.loads(p.channel_config) if p.channel_config else None,
            schedule_config=json.loads(p.schedule_config) if p.schedule_config else None,
            is_active=p.is_active,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in profiles
    ]


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    request: Request,
    profile_data: ProfileCreate,
    db: AsyncSession = Depends(get_async_db),
    account: MoyskladAccount = Depends(get_account_from_context)
) -> ProfileResponse:
    """Создание нового профиля выгрузки."""
    # Проверяем лимит профилей для Lite тарифа
    if account.tariff.value == "lite":
        result = await db.execute(
            select(IntegrationProfile).where(
                IntegrationProfile.account_id == account.id,
                IntegrationProfile.is_active == True
            )
        )
        active_profiles = result.scalars().all()
        if len(active_profiles) >= 3:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Достигнут лимит профилей для тарифа Lite (макс. 3)"
            )
    
    # Сохраняем конфигурации как JSON строки
    import json
    
    profile = IntegrationProfile(
        account_id=account.id,
        name=profile_data.name,
        module=profile_data.module,
        fields_config=json.dumps(profile_data.fields_config) if profile_data.fields_config else None,
        filters=json.dumps(profile_data.filters) if profile_data.filters else None,
        format_config=json.dumps(profile_data.format_config) if profile_data.format_config else None,
        channel_config=json.dumps(profile_data.channel_config) if profile_data.channel_config else None,
        schedule_config=json.dumps(profile_data.schedule_config) if profile_data.schedule_config else None,
        is_active=True,
    )
    
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    
    logger.info(
        f"Создан профиль",
        profile_id=profile.id,
        account_id=account.id,
        name=profile.name
    )
    
    return ProfileResponse(
        id=profile.id,
        account_id=profile.account_id,
        name=profile.name,
        module=profile.module,
        fields_config=profile_data.fields_config,
        filters=profile_data.filters,
        format_config=profile_data.format_config,
        channel_config=profile_data.channel_config,
        schedule_config=profile_data.schedule_config,
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    account: MoyskladAccount = Depends(get_account_from_context)
) -> ProfileResponse:
    """Получение профиля по ID."""
    result = await db.execute(
        select(IntegrationProfile).where(
            IntegrationProfile.id == profile_id,
            IntegrationProfile.account_id == account.id
        )
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль не найден"
        )
    
    import json
    
    return ProfileResponse(
        id=profile.id,
        account_id=profile.account_id,
        name=profile.name,
        module=profile.module,
        fields_config=json.loads(profile.fields_config) if profile.fields_config else None,
        filters=json.loads(profile.filters) if profile.filters else None,
        format_config=json.loads(profile.format_config) if profile.format_config else None,
        channel_config=json.loads(profile.channel_config) if profile.channel_config else None,
        schedule_config=json.loads(profile.schedule_config) if profile.schedule_config else None,
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: int,
    profile_data: ProfileUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    account: MoyskladAccount = Depends(get_account_from_context)
) -> ProfileResponse:
    """Обновление профиля."""
    result = await db.execute(
        select(IntegrationProfile).where(
            IntegrationProfile.id == profile_id,
            IntegrationProfile.account_id == account.id
        )
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль не найден"
        )
    
    import json
    
    # Обновляем поля
    if profile_data.name is not None:
        profile.name = profile_data.name
    if profile_data.module is not None:
        profile.module = profile_data.module
    if profile_data.fields_config is not None:
        profile.fields_config = json.dumps(profile_data.fields_config)
    if profile_data.filters is not None:
        profile.filters = json.dumps(profile_data.filters)
    if profile_data.format_config is not None:
        profile.format_config = json.dumps(profile_data.format_config)
    if profile_data.channel_config is not None:
        profile.channel_config = json.dumps(profile_data.channel_config)
    if profile_data.schedule_config is not None:
        profile.schedule_config = json.dumps(profile_data.schedule_config)
    if profile_data.is_active is not None:
        profile.is_active = profile_data.is_active
    
    await db.commit()
    await db.refresh(profile)
    
    return ProfileResponse(
        id=profile.id,
        account_id=profile.account_id,
        name=profile.name,
        module=profile.module,
        fields_config=json.loads(profile.fields_config) if profile.fields_config else None,
        filters=json.loads(profile.filters) if profile.filters else None,
        format_config=json.loads(profile.format_config) if profile.format_config else None,
        channel_config=json.loads(profile.channel_config) if profile.channel_config else None,
        schedule_config=json.loads(profile.schedule_config) if profile.schedule_config else None,
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    account: MoyskladAccount = Depends(get_account_from_context)
):
    """Удаление профиля."""
    result = await db.execute(
        select(IntegrationProfile).where(
            IntegrationProfile.id == profile_id,
            IntegrationProfile.account_id == account.id
        )
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль не найден"
        )
    
    await db.delete(profile)
    await db.commit()
    
    logger.info(f"Удалён профиль {profile_id}")


@router.post("/{profile_id}/run", response_model=ExportJobResponse)
async def run_profile(
    profile_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    account: MoyskladAccount = Depends(get_account_from_context)
):
    """Ручной запуск выгрузки по профилю."""
    # Проверка существования профиля
    result = await db.execute(
        select(IntegrationProfile).where(
            IntegrationProfile.id == profile_id,
            IntegrationProfile.account_id == account.id
        )
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль не найден"
        )
    
    if not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Профиль не активен"
        )
    
    # Создаём задание
    import json
    from datetime import datetime, timezone
    settings = json.loads(profile.settings) if profile.settings else {}
    
    job = ExportJob(
        profile_id=profile.id,
        account_id=account.id,
        status="pending",
        export_type=settings.get("module", "orders"),
        parameters=settings.get("filters"),
        created_at=datetime.now(timezone.utc),
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    # TODO: Отправить задачу в Celery
    # from app.workers.tasks import run_export_job
    # run_export_job.delay(job.id)
    
    logger.info(f"Запущена выгрузка job_id={job.id}")
    
    return ExportJobResponse(
        id=job.id,
        profile_id=job.profile_id,
        account_id=job.account_id,
        status=job.status,
        export_type=job.export_type,
        parameters=job.parameters,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        result_file_path=job.result_file_path,
        download_url=job.download_url,
        records_processed=job.records_processed,
        created_at=job.created_at,
    )


@router.post("/{profile_id}/test", response_model=ExportJobResponse)
async def test_profile(
    profile_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    account: MoyskladAccount = Depends(get_account_from_context)
):
    """Тестовый запуск выгрузки (без доставки файла)."""
    # Аналогично run_profile, но с флагом test
    result = await db.execute(
        select(IntegrationProfile).where(
            IntegrationProfile.id == profile_id,
            IntegrationProfile.account_id == account.id
        )
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль не найден"
        )
    
    import json
    from datetime import datetime, timezone
    settings = json.loads(profile.settings) if profile.settings else {}
    
    job = ExportJob(
        profile_id=profile.id,
        account_id=account.id,
        status="pending",
        export_type=settings.get("module", "orders"),
        parameters={**settings.get("filters", {}), "test_mode": True},
        created_at=datetime.now(timezone.utc),
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    logger.info(f"Тестовый запуск job_id={job.id}")
    
    return ExportJobResponse(
        id=job.id,
        profile_id=job.profile_id,
        account_id=job.account_id,
        status=job.status,
        export_type=job.export_type,
        parameters=job.parameters,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        result_file_path=job.result_file_path,
        download_url=job.download_url,
        records_processed=job.records_processed,
        created_at=job.created_at,
    )
