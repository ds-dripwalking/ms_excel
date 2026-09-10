"""
Клиент МойСклад JSON API 1.2.

Базовый URL: https://api.moysklad.ru/api/remap/1.2
Аутентификация: OAuth 2.0, Bearer token
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.moysklad.ru/api/remap/1.2"

# Rate limiting: ~100 запросов / 30 сек ≈ 3-5 rps
DEFAULT_RATE_LIMIT = 4  # запросов в секунду
DEFAULT_CHUNK_SIZE = 1000  # макс. записей на страницу


class MoyskladAPIError(Exception):
    """Ошибка API МойСклад."""
    
    def __init__(self, status_code: int, message: str, response_data: Optional[Dict] = None):
        self.status_code = status_code
        self.message = message
        self.response_data = response_data
        super().__init__(f"[{status_code}] {message}")


class MoyskladRateLimitError(MoyskladAPIError):
    """Превышен лимит запросов (429)."""
    pass


class MoyskladUnauthorizedError(MoyskladAPIError):
    """Ошибка авторизации (401)."""
    pass


class MoyskladForbiddenError(MoyskladAPIError):
    """Доступ запрещён (403)."""
    pass


class MoyskladClient:
    """Клиент для работы с МойСклад JSON API 1.2."""
    
    def __init__(
        self,
        access_token: str,
        rate_limit: float = DEFAULT_RATE_LIMIT,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        timeout: float = 30.0,
    ):
        """
        Инициализация клиента.
        
        :param access_token: OAuth access token (Bearer)
        :param rate_limit: Макс. запросов в секунду
        :param chunk_size: Размер чанка для пагинации
        :param timeout: Таймаут запроса в секундах
        """
        self.access_token = access_token
        self.rate_limit = rate_limit
        self.chunk_size = chunk_size
        self.timeout = timeout
        
        self._last_request_time: Optional[datetime] = None
        self._request_count = 0
    
    async def _rate_limit_wait(self):
        """Ожидание для соблюдения rate limit."""
        if self._last_request_time:
            elapsed = (datetime.utcnow() - self._last_request_time).total_seconds()
            min_interval = 1.0 / self.rate_limit
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
        self._last_request_time = datetime.utcnow()
        self._request_count += 1
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Выполнение HTTP запроса к API.
        
        :param method: HTTP метод (GET, POST, PUT, DELETE)
        :param endpoint: Эндпоинт относительно BASE_URL
        :param params: Query параметры
        :param json_data: JSON тело запроса
        :return: Ответ API
        :raises MoyskladAPIError: При ошибке API
        """
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        
        await self._rate_limit_wait()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                )
                
                if response.status_code == 429:
                    raise MoyskladRateLimitError(
                        429,
                        "Too Many Requests - превышен лимит запросов",
                        response.json() if response.content else None,
                    )
                
                if response.status_code == 401:
                    raise MoyskladUnauthorizedError(
                        401,
                        "Unauthorized - неверный или истёкший токен",
                        response.json() if response.content else None,
                    )
                
                if response.status_code == 403:
                    raise MoyskladForbiddenError(
                        403,
                        "Forbidden - недостаточно прав доступа",
                        response.json() if response.content else None,
                    )
                
                if response.status_code >= 500:
                    raise MoyskladAPIError(
                        response.status_code,
                        f"Server Error: {response.status_code}",
                        response.json() if response.content else None,
                    )
                
                if response.status_code >= 400:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("errors", [{}])[0].get("message", "Unknown error")
                    raise MoyskladAPIError(
                        response.status_code,
                        error_msg,
                        error_data,
                    )
                
                return response.json() if response.content else {}
                
        except httpx.RequestError as e:
            raise MoyskladAPIError(0, f"Request error: {str(e)}")
    
    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        expand: Optional[List[str]] = None,
        filter_expr: Optional[str] = None,
        fields: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        GET запрос с поддержкой стандартных параметров API.
        
        :param endpoint: Эндпоинт
        :param params: Дополнительные query параметры
        :param expand: Список связанных объектов для подгрузки
        :param filter_expr: Выражение фильтрации (синтаксис API)
        :param fields: Список полей для выборки
        :param limit: Лимит записей
        :param offset: Смещение
        :return: Ответ API
        """
        query_params = params or {}
        
        if expand:
            query_params["expand"] = ",".join(expand)
        if filter_expr:
            query_params["filter"] = filter_expr
        if fields:
            query_params["fields"] = ",".join(fields)
        if limit is not None:
            query_params["limit"] = min(limit, self.chunk_size)
        if offset is not None:
            query_params["offset"] = offset
        
        return await self._request("GET", endpoint, params=query_params)
    
    async def get_all_paginated(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        expand: Optional[List[str]] = None,
        filter_expr: Optional[str] = None,
        fields: Optional[List[str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получение всех записей с пагинацией.
        
        :param endpoint: Эндпоинт
        :param params: Дополнительные параметры
        :param expand: Список связанных объектов
        :param filter_expr: Выражение фильтрации
        :param fields: Список полей
        :param max_records: Макс. количество записей (None = без ограничения)
        :return: Список всех записей
        """
        all_rows = []
        offset = 0
        limit = self.chunk_size
        
        while True:
            if max_records and len(all_rows) >= max_records:
                break
            
            current_limit = min(limit, max_records - len(all_rows)) if max_records else limit
            
            response = await self.get(
                endpoint=endpoint,
                params=params,
                expand=expand,
                filter_expr=filter_expr,
                fields=fields,
                limit=current_limit,
                offset=offset,
            )
            
            rows = response.get("rows", [])
            if not rows:
                break
            
            all_rows.extend(rows)
            
            # Если получили меньше чем лимит - значит это последняя страница
            if len(rows) < current_limit:
                break
            
            offset += current_limit
            
            logger.info(f"Fetched {len(all_rows)} records from {endpoint} (offset={offset})")
        
        return all_rows
    
    # ==================== ЗАКАЗЫ ПОКУПАТЕЛЕЙ ====================
    
    async def get_customer_orders(
        self,
        filter_expr: Optional[str] = None,
        expand: Optional[List[str]] = None,
        fields: Optional[List[str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получение списка заказов покупателей.
        
        :param filter_expr: Фильтр (напр. "moment>=2026-01-01;moment<=2026-01-31")
        :param expand: Подгрузка связанных объектов
                       (напр. ["organization", "store", "agent", "positions.assortment"])
        :param fields: Выборка полей
        :param max_records: Макс. количество записей
        :return: Список заказов
        """
        default_expand = ["organization", "store", "agent", "positions.assortment"]
        expand = expand or default_expand
        
        return await self.get_all_paginated(
            endpoint="entity/customerorder",
            filter_expr=filter_expr,
            expand=expand,
            fields=fields,
            max_records=max_records,
        )
    
    async def get_customer_order_by_id(self, order_id: str, expand: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Получение одного заказа по ID.
        
        :param order_id: UUID заказа
        :param expand: Подгрузка связанных объектов
        :return: Заказ
        """
        params = {}
        if expand:
            params["expand"] = ",".join(expand)
        
        return await self.get(f"entity/customerorder/{order_id}", params=params or None)
    
    async def get_customer_order_positions(self, order_id: str) -> List[Dict[str, Any]]:
        """
        Получение позиций заказа.
        
        :param order_id: UUID заказа
        :return: Список позиций
        """
        response = await self.get(f"entity/customerorder/{order_id}/positions")
        return response.get("rows", [])
    
    async def get_customer_order_metadata(self) -> Dict[str, Any]:
        """
        Получение метаданных заказов (статусы, доп. поля).
        
        :return: Метаданные
        """
        return await self.get("entity/customerorder/metadata")
    
    # ==================== ПРАЙС-ЛИСТ (АССОРТИМЕНТ) ====================
    
    async def get_assortment(
        self,
        filter_expr: Optional[str] = None,
        expand: Optional[List[str]] = None,
        fields: Optional[List[str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получение ассортимента (товары + услуги).
        
        :param filter_expr: Фильтр (напр. "archived=false")
        :param expand: Подгрузка (напр. ["productFolder"])
        :param fields: Выборка полей
        :param max_records: Макс. количество записей
        :return: Список товаров/услуг
        """
        default_filter = "archived=false"
        if filter_expr:
            default_filter = f"{default_filter};{filter_expr}"
        
        return await self.get_all_paginated(
            endpoint="entity/assortment",
            filter_expr=default_filter,
            expand=expand,
            fields=fields,
            max_records=max_records,
        )
    
    async def get_products(
        self,
        filter_expr: Optional[str] = None,
        expand: Optional[List[str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получение только товаров.
        
        :param filter_expr: Фильтр
        :param expand: Подгрузка
        :param max_records: Макс. количество
        :return: Список товаров
        """
        default_filter = "archived=false"
        if filter_expr:
            default_filter = f"{default_filter};{filter_expr}"
        
        return await self.get_all_paginated(
            endpoint="entity/product",
            filter_expr=default_filter,
            expand=expand,
            max_records=max_records,
        )
    
    async def get_product_images(self, product_id: str) -> List[Dict[str, Any]]:
        """
        Получение изображений товара.
        
        :param product_id: UUID товара
        :return: Список изображений
        """
        response = await self.get(f"entity/product/{product_id}/images")
        return response.get("rows", [])
    
    async def get_stock_report(self) -> List[Dict[str, Any]]:
        """
        Получение отчёта об остатках по всем складам.
        
        :return: Список строк остатков
        """
        response = await self.get("report/stock/all")
        return response.get("rows", [])
    
    async def get_price_types(self) -> List[Dict[str, Any]]:
        """
        Получение типов цен.
        
        :return: Список типов цен
        """
        response = await self.get("context/companysettings/pricetype")
        return response.get("rows", [])
    
    # ==================== СПРАВОЧНИКИ ====================
    
    async def get_organizations(self) -> List[Dict[str, Any]]:
        """Получение списка организаций."""
        response = await self.get("entity/organization")
        return response.get("rows", [])
    
    async def get_stores(self) -> List[Dict[str, Any]]:
        """Получение списка складов."""
        response = await self.get("entity/store")
        return response.get("rows", [])
    
    async def get_currencies(self) -> List[Dict[str, Any]]:
        """Получение списка валют."""
        response = await self.get("entity/currency")
        return response.get("rows", [])
    
    async def get_product_folders(self) -> List[Dict[str, Any]]:
        """Получение дерева групп товаров."""
        response = await self.get("entity/productfolder")
        return response.get("rows", [])
    
    async def get_product_metadata(self) -> Dict[str, Any]:
        """Получение метаданных товаров (доп. поля)."""
        return await self.get("entity/product/metadata")
    
    async def get_counterparties(self, filter_expr: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получение контрагентов.
        
        :param filter_expr: Фильтр
        :return: Список контрагентов
        """
        params = {"filter": filter_expr} if filter_expr else None
        response = await self.get("entity/counterparty", params=params)
        return response.get("rows", [])
    
    async def get_custom_entity_values(self, meta_id: str) -> List[Dict[str, Any]]:
        """
        Получение значений пользовательского справочника.
        
        :param meta_id: ID мета-сущности справочника
        :return: Значения справочника
        """
        response = await self.get(f"entity/customentity/{meta_id}")
        return response.get("rows", [])
