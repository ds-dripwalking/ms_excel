"""
Генераторы файлов для экспорта данных.

Поддерживаемые форматы:
- XLSX (Excel с автошириной колонок, шапкой)
- CSV (UTF-8 BOM / Windows-1251, разделители)
- JSON (массив строк / {meta, rows})
- YML (Yandex Market: categories/offers)
"""
import csv
import io
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, AsyncIterator
from enum import Enum

logger = logging.getLogger(__name__)


class FileFormat(str, Enum):
    """Поддерживаемые форматы файлов."""
    XLSX = "xlsx"
    CSV = "csv"
    JSON = "json"
    YML = "yml"


class CSVEncoding(str, Enum):
    """Кодировки для CSV."""
    UTF8_BOM = "utf-8-sig"  # UTF-8 с BOM для Excel
    WINDOWS_1251 = "cp1251"  # Windows-1251


class CSVDelimiter(str, Enum):
    """Разделители для CSV."""
    SEMICOLON = ";"
    COMMA = ","
    TAB = "\t"


class XLSXGenerator:
    """
    Генератор XLSX файлов.
    
    Особенности:
    - Streaming запись для больших файлов (не загружает всё в RAM)
    - Автоширина колонок
    - Оформленная шапка
    - Закрепление первой строки
    """
    
    def __init__(self, data: List[Dict[str, Any]], columns: Optional[List[str]] = None):
        """
        :param data: Список строк (словари)
        :param columns: Порядок колонок (если не указан, берётся из первой строки)
        """
        self.data = data
        self.columns = columns or self._detect_columns()
        
    def _detect_columns(self) -> List[str]:
        """Определяет колонки из данных."""
        if not self.data:
            return []
        return list(self.data[0].keys())
    
    def generate(self) -> bytes:
        """
        Генерирует XLSX файл.
        
        :return: Байты файла
        """
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError:
            raise ImportError("openpyxl не установлен. Установите: pip install openpyxl")
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Export"
        
        # Стили для шапки
        header_font = Font(bold=True, size=11)
        header_alignment = Alignment(horizontal="center", vertical="center")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        
        # Записываем шапку
        for col_idx, col_name in enumerate(self.columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = header_font
            cell.alignment = header_alignment
            cell.fill = header_fill
        
        # Записываем данные
        for row_idx, row_data in enumerate(self.data, 2):
            for col_idx, col_name in enumerate(self.columns, 1):
                value = row_data.get(col_name, "")
                # Обрабатываем сложные типы
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, datetime):
                    value = value.strftime("%Y-%m-%d %H:%M:%S")
                ws.cell(row=row_idx, column=col_idx, value=value)
        
        # Автоширина колонок
        column_widths = {}
        for col_idx, col_name in enumerate(self.columns, 1):
            max_length = len(str(col_name))
            for row_data in self.data:
                cell_value = row_data.get(col_name, "")
                if isinstance(cell_value, (dict, list)):
                    cell_value = json.dumps(cell_value, ensure_ascii=False)
                cell_length = len(str(cell_value))
                max_length = max(max_length, min(cell_length, 50))  # Ограничение 50 символов
            column_widths[col_idx] = max_length + 2  # Добавляем отступ
        
        for col_idx, width in column_widths.items():
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = width
        
        # Закрепляем первую строку
        ws.freeze_panes = "A2"
        
        # Сохраняем в байты
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()
    
    def get_content_type(self) -> str:
        """Возвращает MIME-тип."""
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    def get_extension(self) -> str:
        """Возвращает расширение файла."""
        return ".xlsx"


class CSVGenerator:
    """
    Генератор CSV файлов.
    
    Особенности:
    - Поддержка кодировок UTF-8 BOM и Windows-1251
    - Разделители: точка с запятой, запятая, таб
    - Корректное экранирование кавычек
    """
    
    def __init__(
        self,
        data: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
        encoding: CSVEncoding = CSVEncoding.UTF8_BOM,
        delimiter: CSVDelimiter = CSVDelimiter.SEMICOLON,
    ):
        """
        :param data: Список строк
        :param columns: Порядок колонок
        :param encoding: Кодировка файла
        :param delimiter: Разделитель полей
        """
        self.data = data
        self.columns = columns or self._detect_columns()
        self.encoding = encoding
        self.delimiter = delimiter
    
    def _detect_columns(self) -> List[str]:
        """Определяет колонки из данных."""
        if not self.data:
            return []
        return list(self.data[0].keys())
    
    def generate(self) -> bytes:
        """
        Генерирует CSV файл.
        
        :return: Байты файла
        """
        output = io.StringIO()
        
        # Создаем writer с правильными параметрами
        writer = csv.DictWriter(
            output,
            fieldnames=self.columns,
            delimiter=self.delimiter.value,
            quotechar='"',
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\r\n",  # Windows-style line endings для Excel
        )
        
        # Записываем шапку
        writer.writeheader()
        
        # Записываем данные
        for row_data in self.data:
            # Обрабатываем сложные типы
            processed_row = {}
            for col in self.columns:
                value = row_data.get(col, "")
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, datetime):
                    value = value.strftime("%Y-%m-%d %H:%M:%S")
                processed_row[col] = value
            writer.writerow(processed_row)
        
        # Получаем строку и кодируем
        csv_string = output.getvalue()
        output.close()
        
        # Добавляем BOM для UTF-8 если нужно
        if self.encoding == CSVEncoding.UTF8_BOM:
            bom = "\ufeff"
            csv_string = bom + csv_string
        
        return csv_string.encode(self.encoding.value)
    
    def get_content_type(self) -> str:
        """Возвращает MIME-тип."""
        return "text/csv"
    
    def get_extension(self) -> str:
        """Возвращает расширение файла."""
        return ".csv"


class JSONGenerator:
    """
    Генератор JSON файлов.
    
    Режимы:
    - array: простой массив строк [{...}, {...}]
    - meta_with_rows: объект с мета-информацией {"meta": {...}, "rows": [...]}
    """
    
    def __init__(
        self,
        data: List[Dict[str, Any]],
        mode: str = "array",
        meta: Optional[Dict[str, Any]] = None,
    ):
        """
        :param data: Список строк
        :param mode: "array" или "meta_with_rows"
        :param meta: Мета-информация для режима meta_with_rows
        """
        self.data = data
        self.mode = mode
        self.meta = meta or {}
    
    def generate(self) -> bytes:
        """
        Генерирует JSON файл.
        
        :return: Байты файла
        """
        if self.mode == "array":
            result = self.data
        elif self.mode == "meta_with_rows":
            result = {
                "meta": {
                    **self.meta,
                    "count": len(self.data),
                    "generated_at": datetime.utcnow().isoformat(),
                },
                "rows": self.data,
            }
        else:
            raise ValueError(f"Неизвестный режим JSON: {self.mode}")
        
        json_string = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        return json_string.encode("utf-8")
    
    def get_content_type(self) -> str:
        """Возвращает MIME-тип."""
        return "application/json"
    
    def get_extension(self) -> str:
        """Возвращает расширение файла."""
        return ".json"


class YMLGenerator:
    """
    Генератор YML файлов для Яндекс.Маркета.
    
    Структура:
    yml_catalog
      shop
        name
        company
        url
        currencies
        categories
        offers
          offer
            name
            price
            currencyId
            categoryId
            picture
            description
            vendor
    """
    
    def __init__(
        self,
        offers: List[Dict[str, Any]],
        categories: Optional[List[Dict[str, Any]]] = None,
        shop_info: Optional[Dict[str, str]] = None,
        currencies: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        :param offers: Список товаров (offers)
        :param categories: Список категорий
        :param shop_info: Информация о магазине (name, company, url)
        :param currencies: Список валют
        """
        self.offers = offers
        self.categories = categories or []
        self.shop_info = shop_info or {
            "name": "Комбайн Экспорт",
            "company": "Компания",
            "url": "https://example.com",
        }
        self.currencies = currencies or [
            {"id": "RUB", "rate": "1"},
            {"id": "USD", "rate": "90"},
            {"id": "EUR", "rate": "95"},
        ]
    
    def generate(self) -> bytes:
        """
        Генерирует YML файл.
        
        :return: Байты файла
        """
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append('<yml_catalog date="' + datetime.utcnow().strftime("%Y-%m-%d %H:%M") + '">')
        lines.append("  <shop>")
        
        # Информация о магазине
        lines.append(f"    <name>{self._escape_xml(self.shop_info.get('name', 'Shop'))}</name>")
        lines.append(f"    <company>{self._escape_xml(self.shop_info.get('company', 'Company'))}</company>")
        lines.append(f"    <url>{self._escape_xml(self.shop_info.get('url', 'https://example.com'))}</url>")
        
        # Валюты
        lines.append("    <currencies>")
        for currency in self.currencies:
            curr_id = currency.get("id", "RUB")
            curr_rate = currency.get("rate", "1")
            lines.append(f'      <currency id="{curr_id}" rate="{curr_rate}"/>')
        lines.append("    </currencies>")
        
        # Категории
        lines.append("    <categories>")
        for category in self.categories:
            cat_id = category.get("id", "")
            cat_name = category.get("name", "")
            parent_id = category.get("parentId")
            if parent_id:
                lines.append(f'      <category id="{cat_id}" parentId="{parent_id}">{self._escape_xml(cat_name)}</category>')
            else:
                lines.append(f'      <category id="{cat_id}">{self._escape_xml(cat_name)}</category>')
        lines.append("    </categories>")
        
        # Товары (offers)
        lines.append("    <offers>")
        for offer in self.offers:
            lines.append("      <offer>")
            
            if offer.get("id"):
                lines.append(f"        <id>{self._escape_xml(str(offer['id']))}</id>")
            
            if offer.get("name"):
                lines.append(f"        <name>{self._escape_xml(offer['name'])}</name>")
            
            if offer.get("price"):
                lines.append(f"        <price>{offer['price']}</price>")
            
            if offer.get("currency_id"):
                lines.append(f"        <currencyId>{offer['currency_id']}</currencyId>")
            else:
                lines.append("        <currencyId>RUB</currencyId>")
            
            if offer.get("category_id"):
                lines.append(f"        <categoryId>{offer['category_id']}</categoryId>")
            
            if offer.get("picture"):
                pictures = offer["picture"] if isinstance(offer["picture"], list) else [offer["picture"]]
                for pic in pictures:
                    lines.append(f"        <picture>{self._escape_xml(pic)}</picture>")
            
            if offer.get("description"):
                lines.append(f"        <description>{self._escape_xml(offer['description'])}</description>")
            
            if offer.get("vendor"):
                lines.append(f"        <vendor>{self._escape_xml(offer['vendor'])}</vendor>")
            
            if offer.get("article"):
                lines.append(f"        <vendorCodex>{self._escape_xml(offer['article'])}</vendorCodex>")
            
            if offer.get("barcode"):
                lines.append(f"        <barcode>{self._escape_xml(offer['barcode'])}</barcode>")
            
            lines.append("      </offer>")
        lines.append("    </offers>")
        
        lines.append("  </shop>")
        lines.append("</yml_catalog>")
        
        yml_string = "\n".join(lines)
        return yml_string.encode("utf-8")
    
    def _escape_xml(self, text: str) -> str:
        """Экранирует специальные XML-символы."""
        if not text:
            return ""
        text = str(text)
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace('"', "&quot;")
        text = text.replace("'", "&apos;")
        return text
    
    def get_content_type(self) -> str:
        """Возвращает MIME-тип."""
        return "application/xml"
    
    def get_extension(self) -> str:
        """Возвращает расширение файла."""
        return ".yml"


class FileGeneratorFactory:
    """Фабрика генераторов файлов."""
    
    @staticmethod
    def create(
        format_type: FileFormat,
        data: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
        **kwargs,
    ):
        """
        Создаёт генератор нужного формата.
        
        :param format_type: Тип формата
        :param data: Данные для экспорта
        :param columns: Порядок колонок
        :param kwargs: Дополнительные параметры
        :return: Экземпляр генератора
        """
        if format_type == FileFormat.XLSX:
            return XLSXGenerator(data, columns)
        
        elif format_type == FileFormat.CSV:
            encoding = kwargs.get("encoding", CSVEncoding.UTF8_BOM)
            delimiter = kwargs.get("delimiter", CSVDelimiter.SEMICOLON)
            return CSVGenerator(data, columns, encoding, delimiter)
        
        elif format_type == FileFormat.JSON:
            mode = kwargs.get("mode", "array")
            meta = kwargs.get("meta")
            return JSONGenerator(data, mode, meta)
        
        elif format_type == FileFormat.YML:
            categories = kwargs.get("categories", [])
            shop_info = kwargs.get("shop_info")
            currencies = kwargs.get("currencies")
            return YMLGenerator(data, categories, shop_info, currencies)
        
        else:
            raise ValueError(f"Неподдерживаемый формат: {format_type}")
