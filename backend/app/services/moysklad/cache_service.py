"""Сервис для управления кэшем справочников МойСклад."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from app.models.moysklad_api import DictionaryCache
from app.services.moysklad.api_client import MoyskladClient

logger = logging.getLogger(__name__)

# TTL по умолчанию для разных типов справочников (в секундах)
DEFAULT_TTL_MAP = {
    "organization": 3600,
    "store": 3600,
    "currency": 3600,
    "productfolder": 3600,
    "pricetype": 3600,
    "customerorder_metadata": 1800,
    "product_metadata": 1800,
}


class DictionaryCacheService:
    """Сервис для кэширования справочников МойСклад."""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def get_cached(
        self,
        account_id: int,
        dictionary_type: str,
        force_refresh: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Получение кэшированного справочника.
        
        :param account_id: ID аккаунта
        :param dictionary_type: Тип справочника
        :param force_refresh: Принудительное обновление
        :return: Данные справочника или None
        """
        # Проверяем кэш в БД
        result = await self.db.execute(
            select(DictionaryCache).where(
                DictionaryCache.account_id == account_id,
                DictionaryCache.dictionary_type == dictionary_type,
            )
        )
        cache_record = result.scalar_one_or_none()
        
        now = datetime.utcnow()
        
        if cache_record and not force_refresh:
            # Проверяем актуальность кэша
            expiry_time = cache_record.cached_at + timedelta(seconds=cache_record.ttl_seconds)
            if now < expiry_time:
                logger.debug(f"Cache hit for {dictionary_type} (account={account_id})")
                return cache_record.data.get("rows", [])
        
        logger.info(f"Cache miss or expired for {dictionary_type} (account={account_id})")
        return None
    
    async def set_cache(
        self,
        account_id: int,
        dictionary_type: str,
        data: Any,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Сохранение данных в кэш.
        
        :param account_id: ID аккаунта
        :param dictionary_type: Тип справочника
        :param data: Данные для кэширования
        :param ttl_seconds: TTL в секундах
        """
        if ttl_seconds is None:
            ttl_seconds = DEFAULT_TTL_MAP.get(dictionary_type, 3600)
        
        # Проверяем существующую запись
        result = await self.db.execute(
            select(DictionaryCache).where(
                DictionaryCache.account_id == account_id,
                DictionaryCache.dictionary_type == dictionary_type,
            )
        )
        cache_record = result.scalar_one_or_none()
        
        cache_data = {
            "rows": data if isinstance(data, list) else data,
            "cached_at": datetime.utcnow().isoformat(),
        }
        
        if cache_record:
            # Обновляем существующую запись
            await self.db.execute(
                update(DictionaryCache)
                .where(
                    DictionaryCache.id == cache_record.id,
                )
                .values(
                    data=cache_data,
                    cached_at=datetime.utcnow(),
                    ttl_seconds=ttl_seconds,
                )
            )
        else:
            # Создаём новую запись
            new_record = DictionaryCache(
                account_id=account_id,
                dictionary_type=dictionary_type,
                data=cache_data,
                ttl_seconds=ttl_seconds,
            )
            self.db.add(new_record)
        
        await self.db.commit()
        logger.info(f"Cached {dictionary_type} for account {account_id} (TTL={ttl_seconds}s)")
    
    async def get_or_fetch(
        self,
        account_id: int,
        dictionary_type: str,
        fetch_func,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Получение из кэша или загрузка через API.
        
        :param account_id: ID аккаунта
        :param dictionary_type: Тип справочника
        :param fetch_func: Асинхронная функция для загрузки из API
        :param force_refresh: Принудительное обновление
        :return: Данные справочника
        """
        # Пытаемся получить из кэша
        cached = await self.get_cached(account_id, dictionary_type, force_refresh)
        if cached is not None:
            return cached
        
        # Загружаем через API
        logger.info(f"Fetching {dictionary_type} from API for account {account_id}")
        data = await fetch_func()
        
        # Сохраняем в кэш
        await self.set_cache(account_id, dictionary_type, data)
        
        return data
    
    async def invalidate(self, account_id: int, dictionary_type: Optional[str] = None) -> None:
        """
        Инвалидация кэша.
        
        :param account_id: ID аккаунта
        :param dictionary_type: Тип справочника (None = все справочники аккаунта)
        """
        if dictionary_type:
            await self.db.execute(
                delete(DictionaryCache).where(
                    DictionaryCache.account_id == account_id,
                    DictionaryCache.dictionary_type == dictionary_type,
                )
            )
        else:
            await self.db.execute(
                delete(DictionaryCache).where(
                    DictionaryCache.account_id == account_id,
                )
            )
        
        await self.db.commit()
        logger.info(f"Invalidated cache for account {account_id}" + 
                   (f", type={dictionary_type}" if dictionary_type else ""))
    
    async def get_all_cached_types(self, account_id: int) -> List[str]:
        """
        Получение списка закэшированных типов справочников для аккаунта.
        
        :param account_id: ID аккаунта
        :return: Список типов
        """
        result = await self.db.execute(
            select(DictionaryCache.dictionary_type).where(
                DictionaryCache.account_id == account_id,
            )
        )
        return [row[0] for row in result.all()]
    
    async def cleanup_expired(self, batch_size: int = 100) -> int:
        """
        Очистка устаревших записей кэша.
        
        :param batch_size: Размер пакета для удаления
        :return: Количество удалённых записей
        """
        now = datetime.utcnow()
        
        # Находим устаревшие записи
        result = await self.db.execute(
            select(DictionaryCache).where(
                DictionaryCache.cached_at + timedelta(seconds=DictionaryCache.ttl_seconds) < now,
            ).limit(batch_size)
        )
        expired_records = result.scalars().all()
        
        if not expired_records:
            return 0
        
        # Удаляем устаревшие записи
        record_ids = [r.id for r in expired_records]
        await self.db.execute(
            delete(DictionaryCache).where(DictionaryCache.id.in_(record_ids))
        )
        await self.db.commit()
        
        logger.info(f"Cleaned up {len(expired_records)} expired cache records")
        return len(expired_records)
