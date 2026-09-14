"""
Модуль экспорта прайс-листов из МойСклад.

Поддерживает:
- Товары, модификации, комплекты
- Цены по типам цен
- Остатки по складам
- Изображения
- Дополнительные поля
- Фильтры (архивные, организация, склады, категории, цены, остатки)
"""

import logging
from typing import Any
from datetime import datetime
from uuid import UUID

from app.services.moysklad.api_client import MoyskladClient
from app.services.moysklad.cache_service import DictionaryCacheService

logger = logging.getLogger(__name__)


class PriceExportService:
    """
    Сервис экспорта прайс-листов.
    
    Собирает данные:
    - ассортимент (товары, модификации, комплекты)
    - цены по типам цен
    - остатки по складам
    - группы/категории
    - изображения
    - дополнительные поля
    """
    
    def __init__(self, client: MoyskladClient, cache_service: DictionaryCacheService):
        self.client = client
        self.cache_service = cache_service
    
    async def export_pricelist(
        self,
        account_id: UUID,
        organization_ids: list[str] | None = None,
        store_ids: list[str] | None = None,
        product_folder_ids: list[str] | None = None,
        price_type_ids: list[str] | None = None,
        archived: bool = False,
        only_with_stock: bool = False,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Экспорт прайс-листа с фильтрами.
        
        Args:
            account_id: ID аккаунта
            organization_ids: фильтры по организациям
            store_ids: фильтры по складам
            product_folder_ids: фильтры по категориям
            price_type_ids: фильтры по типам цен
            archived: включать архивные товары
            only_with_stock: только товары в наличии
            min_price: минимальная цена
            max_price: максимальная цена
            
        Returns:
            Список словарей с данными товаров
        """
        logger.info(f"Начало экспорта прайс-листа для аккаунта {account_id}")
        
        # Загружаем справочники
        organizations = await self._get_organizations(account_id, organization_ids)
        stores = await self._get_stores(account_id, store_ids)
        price_types = await self._get_price_types(account_id, price_type_ids)
        product_folders = await self._get_product_folders(account_id, product_folder_ids)
        
        # Загружаем ассортимент
        assortment = await self._get_assortment(
            account_id=account_id,
            archived=archived,
            product_folder_ids=product_folder_ids,
        )
        
        # Загружаем остатки
        stock_data = await self._get_stock_data(account_id, store_ids)
        
        # Загружаем изображения для товаров
        images_data = await self._get_images_data(account_id, assortment)
        
        # Формируем результат
        results = []
        for product in assortment:
            # Применяем фильтры на нашей стороне
            if not self._apply_product_filters(
                product=product,
                organizations=organizations,
                stores=stores,
                price_types=price_types,
                stock_data=stock_data,
                only_with_stock=only_with_stock,
                min_price=min_price,
                max_price=max_price,
            ):
                continue
            
            row = self._build_product_row(
                product=product,
                organizations=organizations,
                stores=stores,
                price_types=price_types,
                stock_data=stock_data,
                images_data=images_data,
            )
            results.append(row)
        
        logger.info(f"Экспорт прайс-листа завершен. Найдено {len(results)} товаров")
        return results
    
    async def _get_organizations(
        self, 
        account_id: UUID, 
        organization_ids: list[str] | None = None
    ) -> list[dict]:
        """Получить список организаций."""
        if organization_ids:
            # Если указаны конкретные организации, загружаем их
            organizations = []
            for org_id in organization_ids:
                try:
                    org = await self.client.get_organizations(account_id, limit=1000)
                    organizations.extend([o for o in org if o['id'] == org_id])
                except Exception:
                    continue
            return organizations
        
        # Иначе кэшируем все организации
        return await self.cache_service.get_or_fetch(
            account_id=account_id,
            dictionary_type='organizations',
            fetch_func=lambda: self.client.get_organizations(account_id, limit=1000),
            ttl_seconds=3600,
        )
    
    async def _get_stores(
        self, 
        account_id: UUID, 
        store_ids: list[str] | None = None
    ) -> list[dict]:
        """Получить список складов."""
        if store_ids:
            stores = await self.client.get_stores(account_id, limit=1000)
            return [s for s in stores if s['id'] in store_ids]
        
        return await self.cache_service.get_or_fetch(
            account_id=account_id,
            dictionary_type='stores',
            fetch_func=lambda: self.client.get_stores(account_id, limit=1000),
            ttl_seconds=3600,
        )
    
    async def _get_price_types(
        self, 
        account_id: UUID, 
        price_type_ids: list[str] | None = None
    ) -> list[dict]:
        """Получить типы цен."""
        if price_type_ids:
            price_types = await self.client.get_price_types(account_id, limit=1000)
            return [pt for pt in price_types if pt['id'] in price_type_ids]
        
        return await self.cache_service.get_or_fetch(
            account_id=account_id,
            dictionary_type='price_types',
            fetch_func=lambda: self.client.get_price_types(account_id, limit=1000),
            ttl_seconds=1800,
        )
    
    async def _get_product_folders(
        self, 
        account_id: UUID, 
        folder_ids: list[str] | None = None
    ) -> list[dict]:
        """Получить группы товаров."""
        if folder_ids:
            folders = await self.client.get_product_folders(account_id, limit=1000)
            return [f for f in folders if f['id'] in folder_ids]
        
        return await self.cache_service.get_or_fetch(
            account_id=account_id,
            dictionary_type='product_folders',
            fetch_func=lambda: self.client.get_product_folders(account_id, limit=1000),
            ttl_seconds=3600,
        )
    
    async def _get_assortment(
        self,
        account_id: UUID,
        archived: bool = False,
        product_folder_ids: list[str] | None = None,
    ) -> list[dict]:
        """
        Загрузить ассортимент (товары, модификации, комплекты).
        
        Args:
            account_id: ID аккаунта
            archived: включать архивные товары
            product_folder_ids: фильтровать по группам товаров
        """
        filters = ['archived=false'] if not archived else []
        
        if product_folder_ids:
            # Фильтр по группе товаров
            folder_filter = 'productFolder.id=' + ','.join(product_folder_ids)
            filters.append(folder_filter)
        
        filter_str = ';'.join(filters) if filters else None
        
        # Получаем весь ассортимент
        assortment = await self.client.get_assortment(
            account_id=account_id,
            filter=filter_str,
        )
        
        logger.info(f"Загружено {len(assortment)} позиций ассортимента")
        return assortment
    
    async def _get_stock_data(
        self,
        account_id: UUID,
        store_ids: list[str] | None = None,
    ) -> dict[str, dict]:
        """
        Загрузить остатки по всем складам.
        
        Returns:
            Словарь: {product_id: {store_id: {'available': ..., 'stock': ...}}}
        """
        # Строим фильтр по складам
        filter_str = None
        if store_ids:
            filter_str = 'store.id=' + ','.join(store_ids)
        
        stock_report = await self.client.get_stock_report(
            account_id=account_id,
            filter=filter_str,
        )
        
        # Преобразуем в удобный формат
        stock_data: dict[str, dict] = {}
        for row in stock_report:
            product_id = row.get('assortment', {}).get('id')
            if not product_id:
                continue
            
            if product_id not in stock_data:
                stock_data[product_id] = {}
            
            store_id = row.get('store', {}).get('id')
            stock_data[product_id][store_id] = {
                'available': row.get('available', 0),
                'stock': row.get('stock', 0),
                'reserved': row.get('reserved', 0),
                'inWay': row.get('inWay', 0),
            }
        
        logger.info(f"Загружены остатки для {len(stock_data)} товаров")
        return stock_data
    
    async def _get_images_data(
        self,
        account_id: UUID,
        assortment: list[dict],
    ) -> dict[str, list[str]]:
        """
        Загрузить изображения для товаров.
        
        Returns:
            Словарь: {product_id: [image_url, ...]}
        """
        images_data: dict[str, list[str]] = {}
        
        # Получаем товары с изображениями
        products_with_images = [p for p in assortment if p.get('meta', {}).get('type') == 'product']
        
        for product in products_with_images[:50]:  # Ограничиваем количество запросов
            product_id = product['id']
            try:
                images = await self.client.get_product_images(account_id, product_id)
                if images:
                    images_data[product_id] = [img.get('href', '') for img in images]
            except Exception as e:
                logger.warning(f"Не удалось загрузить изображения для товара {product_id}: {e}")
        
        return images_data
    
    def _apply_product_filters(
        self,
        product: dict,
        organizations: list[dict],
        stores: list[dict],
        price_types: list[dict],
        stock_data: dict,
        only_with_stock: bool,
        min_price: float | None,
        max_price: float | None,
    ) -> bool:
        """
        Применить фильтры к товару.
        
        Returns:
            True если товар проходит фильтры
        """
        # Фильтр "только в наличии"
        if only_with_stock:
            product_stock = stock_data.get(product['id'], {})
            total_available = sum(s.get('available', 0) for s in product_stock.values())
            if total_available <= 0:
                return False
        
        # Фильтры по цене
        prices = product.get('prices', [])
        if min_price is not None or max_price is not None:
            has_matching_price = False
            for price in prices:
                value = price.get('value', 0) / 100  # Копейки -> рубли
                if min_price is not None and value < min_price:
                    continue
                if max_price is not None and value > max_price:
                    continue
                has_matching_price = True
                break
            
            if not has_matching_price:
                return False
        
        return True
    
    def _build_product_row(
        self,
        product: dict,
        organizations: list[dict],
        stores: list[dict],
        price_types: list[dict],
        stock_data: dict,
        images_data: dict,
    ) -> dict[str, Any]:
        """
        Построить строку данных товара.
        
        Поля:
        - uuid: UUID товара
        - name: Наименование
        - article: Артикул
        - code: Код
        - barcode: Штрихкод (первый)
        - barcodes: Все штрихкоды через запятую
        - group: Группа/категория
        - unit: Единица измерения
        - description: Описание
        - weight: Вес (г)
        - volume: Объем (л)
        - Цена {type_name}: Цены по типам цен
        - available: Доступно (сумма по складам)
        - stock: Остаток (сумма по складам)
        - reserved: Резерв (сумма по складам)
        - in_way: В пути (сумма по складам)
        - images: Ссылки на изображения
        - custom_fields: Дополнительные поля
        - archived: Архивный
        - moysklad_link: Ссылка на товар в МойСклад
        """
        # Базовые поля
        row = {
            'uuid': product.get('id'),
            'name': product.get('name', ''),
            'article': product.get('article', ''),
            'code': product.get('code', ''),
            'barcode': self._get_first_barcode(product),
            'barcodes': self._get_all_barcodes(product),
            'group': self._get_product_group(product),
            'unit': product.get('unit', {}).get('name', ''),
            'description': product.get('description', ''),
            'weight': product.get('weight', 0),
            'volume': product.get('volume', 0),
            'archived': product.get('archived', False),
            'moysklad_link': f"https://online.moysklad.ru/app/products/edit.html?id={product.get('id')}",
        }
        
        # Цены по типам цен
        prices = product.get('prices', [])
        for price_type in price_types:
            type_id = price_type['id']
            type_name = price_type.get('name', 'Цена')
            
            price_value = 0
            for price in prices:
                if price.get('priceType', {}).get('id') == type_id:
                    price_value = price.get('value', 0) / 100  # Копейки -> рубли
                    break
            
            row[f'Цена {type_name}'] = price_value
        
        # Остатки
        product_stock = stock_data.get(product['id'], {})
        row['available'] = sum(s.get('available', 0) for s in product_stock.values())
        row['stock'] = sum(s.get('stock', 0) for s in product_stock.values())
        row['reserved'] = sum(s.get('reserved', 0) for s in product_stock.values())
        row['in_way'] = sum(s.get('inWay', 0) for s in product_stock.values())
        
        # Изображения
        row['images'] = ';'.join(images_data.get(product['id'], []))
        
        # Дополнительные поля
        row['custom_fields'] = self._extract_custom_fields(product)
        
        return row
    
    def _get_first_barcode(self, product: dict) -> str:
        """Получить первый штрихкод."""
        barcodes = product.get('barcodes', [])
        if barcodes:
            return barcodes[0].get('barcode', '')
        
        # Для модификаций и комплектов
        if 'barcode' in product:
            return product['barcode']
        
        return ''
    
    def _get_all_barcodes(self, product: dict) -> str:
        """Получить все штрихкоды через запятую."""
        barcodes = product.get('barcodes', [])
        barcode_list = [bc.get('barcode', '') for bc in barcodes if bc.get('barcode')]
        
        if not barcode_list and 'barcode' in product:
            barcode_list.append(product['barcode'])
        
        return ','.join(barcode_list)
    
    def _get_product_group(self, product: dict) -> str:
        """Получить группу товара."""
        group = product.get('productFolder')
        if group:
            return group.get('name', '')
        return ''
    
    def _extract_custom_fields(self, product: dict) -> dict[str, Any]:
        """Извлечь дополнительные поля."""
        custom_fields = {}
        attributes = product.get('attributes', [])
        
        for attr in attributes:
            name = attr.get('name', '')
            value = attr.get('value')
            
            # Обрабатываем разные типы значений
            if isinstance(value, dict):
                # Ссылка или сложный объект
                value = value.get('name', str(value))
            
            if name:
                custom_fields[name] = value
        
        return custom_fields
    
    async def get_available_price_types(self, account_id: UUID) -> list[dict]:
        """Получить доступные типы цен для аккаунта."""
        return await self.cache_service.get_or_fetch(
            account_id=account_id,
            dictionary_type='price_types',
            fetch_func=lambda: self.client.get_price_types(account_id, limit=1000),
            ttl_seconds=1800,
        )
    
    async def get_available_product_folders(self, account_id: UUID) -> list[dict]:
        """Получить доступные группы товаров."""
        return await self.cache_service.get_or_fetch(
            account_id=account_id,
            dictionary_type='product_folders',
            fetch_func=lambda: self.client.get_product_folders(account_id, limit=1000),
            ttl_seconds=3600,
        )
