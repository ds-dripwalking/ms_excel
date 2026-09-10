"""
Модуль экспорта заказов покупателей.

Этап 6: Модуль «Заказы покупателей».

Режимы выгрузки:
1. Один заказ = одна строка (для бухгалтерии)
2. Заказ с позициями (каждая позиция отдельной строкой)

Фильтры P0:
- организация
- склад
- статусы
- период (сегодня, вчера, неделя, месяц, произвольный)
- сумма мин/макс
"""
import logging
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class OrderExportMode(str, Enum):
    """Режимы экспорта заказов."""
    ONE_ORDER_ONE_ROW = "one_order_one_row"  # Один заказ = одна строка
    ORDER_WITH_POSITIONS = "order_with_positions"  # Каждая позиция отдельной строкой


class OrderField(str, Enum):
    """Поля шапки заказа."""
    UUID = "uuid"
    NUMBER = "number"
    MOMENT = "moment"
    STATUS = "status"
    ORGANIZATION = "organization"
    STORE = "store"
    AGENT = "agent"
    PHONE = "phone"
    EMAIL = "email"
    DELIVERY_ADDRESS = "delivery_address"
    SUM = "sum"
    PAID_SUM = "paid_sum"
    SHIPPED_SUM = "shipped_sum"
    DISCOUNT = "discount"
    VAT = "vat"
    CURRENCY = "currency"
    MANAGER = "manager"
    PROJECT = "project"
    AGREEMENT = "agreement"
    COMMENT = "comment"
    CUSTOM_FIELDS = "custom_fields"
    MOYSKLAD_LINK = "moysklad_link"


class PositionField(str, Enum):
    """Поля позиций заказа."""
    PRODUCT = "product"
    ARTICLE = "article"
    CODE = "code"
    BARCODE = "barcode"
    QUANTITY = "quantity"
    PRICE = "price"
    SUM = "sum"
    DISCOUNT = "discount"
    VAT = "vat"
    UNIT = "unit"


class OrdersExportService:
    """Сервис экспорта заказов покупателей."""
    
    def __init__(self, api_client):
        """
        Инициализация сервиса.
        
        :param api_client: MoyskladClient instance
        """
        self.api_client = api_client
        self.logger = logging.getLogger(__name__)
    
    async def export_orders(
        self,
        mode: OrderExportMode = OrderExportMode.ONE_ORDER_ONE_ROW,
        filters: Optional[Dict[str, Any]] = None,
        fields_config: Optional[Dict[str, Any]] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Экспорт заказов покупателей.
        
        :param mode: Режим экспорта
        :param filters: Фильтры (organization, store, statuses, period, sum_min, sum_max)
        :param fields_config: Конфигурация полей (какие поля включать)
        :param max_records: Макс. количество записей
        :return: Список строк для экспорта
        """
        filters = filters or {}
        fields_config = fields_config or {}
        
        # Формируем фильтр для API
        api_filter = self._build_api_filter(filters)
        
        # Определяем expand для подгрузки связанных объектов
        expand = self._build_expand_list(mode, fields_config)
        
        # Получаем заказы из API
        self.logger.info(f"Fetching orders with filter: {api_filter}")
        orders = await self.api_client.get_customer_orders(
            filter_expr=api_filter,
            expand=expand,
            max_records=max_records,
        )
        
        self.logger.info(f"Fetched {len(orders)} orders")
        
        # Преобразуем в плоские строки согласно режиму
        if mode == OrderExportMode.ONE_ORDER_ONE_ROW:
            return self._transform_to_single_row_format(orders, fields_config)
        else:
            return self._transform_to_positions_format(orders, fields_config)
    
    def _build_api_filter(self, filters: Dict[str, Any]) -> Optional[str]:
        """
        Построение фильтра для API МойСклад.
        
        Поддерживаемые фильтры:
        - organization: UUID организации
        - store: UUID склада
        - statuses: список UUID статусов
        - period: today, yesterday, week, month, custom
        - date_from: дата от (для custom)
        - date_to: дата до (для custom)
        - sum_min: минимальная сумма
        - sum_max: максимальная сумма
        
        :param filters: Словарь фильтров
        :return: Строка фильтра в синтаксисе API
        """
        filter_parts = []
        
        # Организация
        if org_id := filters.get("organization"):
            filter_parts.append(f"organization.id={org_id}")
        
        # Склад
        if store_id := filters.get("store"):
            filter_parts.append(f"store.id={store_id}")
        
        # Статусы
        if statuses := filters.get("statuses"):
            if isinstance(statuses, list):
                status_filter = ",".join(f"id={s}" for s in statuses)
                filter_parts.append(f"state.id=({status_filter})")
            else:
                filter_parts.append(f"state.id={statuses}")
        
        # Период
        period = filters.get("period")
        if period:
            date_from, date_to = self._calculate_date_range(period, filters)
            if date_from:
                filter_parts.append(f"moment>={date_from}")
            if date_to:
                filter_parts.append(f"moment<={date_to}")
        elif filters.get("date_from") or filters.get("date_to"):
            # Произвольный диапазон
            if date_from := filters.get("date_from"):
                filter_parts.append(f"moment>={date_from}")
            if date_to := filters.get("date_to"):
                filter_parts.append(f"moment<={date_to}")
        
        # Сумма
        if sum_min := filters.get("sum_min"):
            filter_parts.append(f"sum>={sum_min}")
        if sum_max := filters.get("sum_max"):
            filter_parts.append(f"sum<={sum_max}")
        
        if not filter_parts:
            return None
        
        return ";".join(filter_parts)
    
    def _calculate_date_range(
        self,
        period: str,
        filters: Dict[str, Any],
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Расчёт диапазона дат для периода.
        
        :param period: today, yesterday, week, month, custom
        :param filters: Дополнительные фильтры
        :return: (date_from, date_to) в формате YYYY-MM-DD
        """
        today = date.today()
        
        if period == "today":
            return today.isoformat(), today.isoformat()
        
        elif period == "yesterday":
            yesterday = today - timedelta(days=1)
            return yesterday.isoformat(), yesterday.isoformat()
        
        elif period == "week":
            # Начало недели (понедельник)
            start_of_week = today - timedelta(days=today.weekday())
            return start_of_week.isoformat(), today.isoformat()
        
        elif period == "month":
            # Начало месяца
            start_of_month = today.replace(day=1)
            return start_of_month.isoformat(), today.isoformat()
        
        elif period == "custom":
            # Произвольный диапазон из фильтров
            date_from = filters.get("date_from")
            date_to = filters.get("date_to")
            return date_from, date_to
        
        return None, None
    
    def _build_expand_list(
        self,
        mode: OrderExportMode,
        fields_config: Dict[str, Any],
    ) -> List[str]:
        """
        Построение списка expand для подгрузки связанных объектов.
        
        :param mode: Режим экспорта
        :param fields_config: Конфигурация полей
        :return: Список expand параметров
        """
        # Базовый набор всегда подгружаем
        expand = ["organization", "store", "agent", "state"]
        
        # Для режима с позициями подгружаем positions
        if mode == OrderExportMode.ORDER_WITH_POSITIONS:
            expand.append("positions.assortment")
        
        # Если нужны доп. поля, подгружаем их
        if fields_config.get("include_custom_fields"):
            # Метаданные понадобятся для расшифровки custom fields
            pass
        
        return expand
    
    def _transform_to_single_row_format(
        self,
        orders: List[Dict[str, Any]],
        fields_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Преобразование заказов в формат "один заказ = одна строка".
        
        :param orders: Список заказов из API
        :param fields_config: Конфигурация полей
        :return: Список строк
        """
        result = []
        
        selected_fields = fields_config.get("order_fields", [f.value for f in OrderField])
        
        for order in orders:
            row = {}
            
            # UUID
            if "uuid" in selected_fields:
                row["uuid"] = order.get("id", "")
            
            # Номер
            if "number" in selected_fields:
                row["number"] = order.get("name", "")
            
            # Дата
            if "moment" in selected_fields:
                row["moment"] = order.get("moment", "")
            
            # Статус
            if "status" in selected_fields:
                state = order.get("state", {})
                row["status"] = state.get("name", "") if state else ""
            
            # Организация
            if "organization" in selected_fields:
                org = order.get("organization", {})
                row["organization"] = org.get("name", "") if org else ""
            
            # Склад
            if "store" in selected_fields:
                store = order.get("store", {})
                row["store"] = store.get("name", "") if store else ""
            
            # Контрагент/покупатель
            if "agent" in selected_fields:
                agent = order.get("agent", {})
                row["agent"] = agent.get("name", "") if agent else ""
            
            # Телефон и email (из контрагента или delivery)
            if "phone" in selected_fields or "email" in selected_fields:
                agent = order.get("agent", {})
                delivery = order.get("delivery", {})
                
                if "phone" in selected_fields:
                    row["phone"] = (
                        agent.get("phone", "") or 
                        delivery.get("phone", "") or 
                        ""
                    )
                
                if "email" in selected_fields:
                    row["email"] = (
                        agent.get("email", "") or 
                        delivery.get("email", "") or 
                        ""
                    )
            
            # Адрес доставки
            if "delivery_address" in selected_fields:
                delivery = order.get("delivery", {})
                address = delivery.get("address", {})
                row["delivery_address"] = address.get("text", "") if address else ""
            
            # Сумма
            if "sum" in selected_fields:
                row["sum"] = order.get("sum", 0) / 100  # В API сумма в копейках
            
            # Оплачено
            if "paid_sum" in selected_fields:
                row["paid_sum"] = order.get("paidSum", 0) / 100
            
            # Отгружено
            if "shipped_sum" in selected_fields:
                row["shipped_sum"] = order.get("shippedSum", 0) / 100
            
            # Скидка
            if "discount" in selected_fields:
                row["discount"] = order.get("discount", 0)
            
            # НДС
            if "vat" in selected_fields:
                vat_sum = order.get("vatSum", 0)
                row["vat"] = vat_sum / 100 if vat_sum else 0
            
            # Валюта
            if "currency" in selected_fields:
                currency = order.get("currency", {})
                row["currency"] = currency.get("isoCode", "RUB") if currency else "RUB"
            
            # Менеджер
            if "manager" in selected_fields:
                manager = order.get("owner", {})
                row["manager"] = manager.get("name", "") if manager else ""
            
            # Проект
            if "project" in selected_fields:
                project = order.get("group", {})
                row["project"] = project.get("name", "") if project else ""
            
            # Договор
            if "agreement" in selected_fields:
                agreement = order.get("agreement", {})
                row["agreement"] = agreement.get("name", "") if agreement else ""
            
            # Комментарий
            if "comment" in selected_fields:
                row["comment"] = order.get("comments", "")
            
            # Дополнительные поля
            if "custom_fields" in selected_fields and fields_config.get("include_custom_fields"):
                row["custom_fields"] = self._extract_custom_fields(order)
            
            # Ссылка в МойСклад
            if "moysklad_link" in selected_fields:
                order_id = order.get("id", "")
                row["moysklad_link"] = f"https://online.moysklad.ru/app/customerorder.edit.html?id={order_id}" if order_id else ""
            
            result.append(row)
        
        return result
    
    def _transform_to_positions_format(
        self,
        orders: List[Dict[str, Any]],
        fields_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Преобразование заказов в формат "заказ с позициями".
        
        Каждая позиция отдельной строкой с информацией о заказе.
        
        :param orders: Список заказов из API
        :param fields_config: Конфигурация полей
        :return: Список строк
        """
        result = []
        
        order_fields = fields_config.get("order_fields", [f.value for f in OrderField])
        position_fields = fields_config.get("position_fields", [f.value for f in PositionField])
        
        for order in orders:
            # Базовая информация о заказе (повторяется для каждой позиции)
            order_info = {}
            
            if "uuid" in order_fields:
                order_info["order_uuid"] = order.get("id", "")
            if "number" in order_fields:
                order_info["order_number"] = order.get("name", "")
            if "moment" in order_fields:
                order_info["order_moment"] = order.get("moment", "")
            if "status" in order_fields:
                state = order.get("state", {})
                order_info["order_status"] = state.get("name", "") if state else ""
            if "organization" in order_fields:
                org = order.get("organization", {})
                order_info["order_organization"] = org.get("name", "") if org else ""
            if "store" in order_fields:
                store = order.get("store", {})
                order_info["order_store"] = store.get("name", "") if store else ""
            if "agent" in order_fields:
                agent = order.get("agent", {})
                order_info["order_agent"] = agent.get("name", "") if agent else ""
            if "sum" in order_fields:
                order_info["order_sum"] = order.get("sum", 0) / 100
            
            # Получаем позиции
            positions = order.get("positions", {}).get("rows", [])
            
            if not positions:
                # Если позиций нет, создаём одну строку только с информацией о заказе
                row = {**order_info}
                result.append(row)
                continue
            
            # Создаём строку для каждой позиции
            for position in positions:
                row = {**order_info}
                
                assortment = position.get("assortment", {})
                
                # Товар
                if "product" in position_fields:
                    row["product"] = assortment.get("name", "")
                
                # Артикул
                if "article" in position_fields:
                    row["article"] = assortment.get("article", "")
                
                # Код
                if "code" in position_fields:
                    row["code"] = assortment.get("code", "")
                
                # Штрихкод
                if "barcode" in position_fields:
                    barcodes = assortment.get("barcodes", [])
                    row["barcode"] = barcodes[0] if barcodes else ""
                
                # Количество
                if "quantity" in position_fields:
                    row["quantity"] = position.get("quantity", 0)
                
                # Цена (в копейках, переводим в рубли)
                if "price" in position_fields:
                    price = position.get("price", 0)
                    row["price"] = price / 100
                
                # Сумма позиции
                if "sum" in position_fields:
                    sum_val = position.get("sum", 0)
                    row["sum"] = sum_val / 100
                
                # Скидка позиции
                if "discount" in position_fields:
                    row["discount"] = position.get("discount", 0)
                
                # НДС позиции
                if "vat" in position_fields:
                    vat = position.get("vat", 0)
                    row["vat"] = vat / 100 if vat else 0
                
                # Единица измерения
                if "unit" in position_fields:
                    unit = assortment.get("uom", {})
                    row["unit"] = unit.get("name", "шт") if unit else "шт"
                
                result.append(row)
        
        return result
    
    def _extract_custom_fields(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Извлечение дополнительных полей из заказа.
        
        :param order: Заказ из API
        :return: Словарь дополнительных полей
        """
        custom_fields = {}
        
        attributes = order.get("attributes", [])
        for attr in attributes:
            name = attr.get("name", "unknown")
            value = attr.get("value", "")
            
            # Если значение - это объект с meta, извлекаем name
            if isinstance(value, dict) and "meta" in value:
                value = value.get("name", str(value))
            
            custom_fields[name] = value
        
        return custom_fields
    
    async def get_available_statuses(
        self,
    ) -> List[Dict[str, Any]]:
        """
        Получение доступных статусов заказов.
        
        :return: Список статусов
        """
        metadata = await self.api_client.get_customer_order_metadata()
        states = metadata.get("states", [])
        
        return [
            {"id": s.get("id"), "name": s.get("name")}
            for s in states
        ]
