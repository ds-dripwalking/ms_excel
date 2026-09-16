"""
Тесты генераторов файлов.
"""
import pytest
import json
from datetime import datetime
from app.services.export.file_generators import (
    XLSXGenerator,
    CSVGenerator,
    JSONGenerator,
    YMLGenerator,
    FileFormat,
    CSVEncoding,
    CSVDelimiter,
    FileGeneratorFactory,
)


class TestXLSXGenerator:
    """Тесты генератора XLSX."""

    def test_generate_basic(self):
        """Базовый тест генерации XLSX."""
        data = [
            {"name": "Товар 1", "price": 100, "quantity": 10},
            {"name": "Товар 2", "price": 200, "quantity": 20},
        ]
        generator = XLSXGenerator(data)
        result = generator.generate()
        
        assert isinstance(result, bytes)
        assert len(result) > 0
        # Проверяем, что это ZIP-файл (XLSX - это ZIP-архив)
        assert result[:4] == b'PK\x03\x04'

    def test_generate_with_columns(self):
        """Тест с явным указанием колонок."""
        data = [
            {"name": "Товар 1", "price": 100, "quantity": 10},
            {"name": "Товар 2", "price": 200, "quantity": 20},
        ]
        columns = ["name", "price"]
        generator = XLSXGenerator(data, columns=columns)
        result = generator.generate()
        
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_generate_empty_data(self):
        """Тест с пустыми данными."""
        data = []
        generator = XLSXGenerator(data)
        result = generator.generate()
        
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_generate_with_datetime(self):
        """Тест с datetime полями."""
        data = [
            {"name": "Товар 1", "created_at": datetime(2024, 1, 15, 10, 30, 0)},
        ]
        generator = XLSXGenerator(data)
        result = generator.generate()
        
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_content_type(self):
        """Тест MIME-типа."""
        generator = XLSXGenerator([])
        assert generator.get_content_type() == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def test_extension(self):
        """Тест расширения файла."""
        generator = XLSXGenerator([])
        assert generator.get_extension() == ".xlsx"


class TestCSVGenerator:
    """Тесты генератора CSV."""

    def test_generate_utf8_bom(self):
        """Тест UTF-8 с BOM."""
        data = [
            {"name": "Товар 1", "price": 100},
            {"name": "Товар 2", "price": 200},
        ]
        generator = CSVGenerator(data, encoding=CSVEncoding.UTF8_BOM)
        result = generator.generate()
        
        assert isinstance(result, bytes)
        # Проверяем BOM
        assert result[:3] == b'\xef\xbb\xbf'
        # Проверяем, что данные декодируются
        decoded = result.decode('utf-8-sig')
        assert "Товар 1" in decoded
        assert "name;price" in decoded

    def test_generate_windows_1251(self):
        """Тест Windows-1251 кодировки."""
        data = [
            {"name": "Товар 1", "price": 100},
        ]
        generator = CSVGenerator(data, encoding=CSVEncoding.WINDOWS_1251)
        result = generator.generate()
        
        assert isinstance(result, bytes)
        # Проверяем, что декодируется в cp1251
        decoded = result.decode('cp1251')
        assert "Товар 1" in decoded

    def test_generate_semicolon_delimiter(self):
        """Тест разделителя точка с запятой."""
        data = [
            {"name": "Товар 1", "price": 100},
        ]
        generator = CSVGenerator(data, delimiter=CSVDelimiter.SEMICOLON)
        result = generator.generate()
        
        decoded = result.decode('utf-8-sig')
        assert "name;price" in decoded

    def test_generate_comma_delimiter(self):
        """Тест разделителя запятая."""
        data = [
            {"name": "Товар 1", "price": 100},
        ]
        generator = CSVGenerator(data, delimiter=CSVDelimiter.COMMA)
        result = generator.generate()
        
        decoded = result.decode('utf-8-sig')
        assert "name,price" in decoded

    def test_generate_tab_delimiter(self):
        """Тест разделителя таб."""
        data = [
            {"name": "Товар 1", "price": 100},
        ]
        generator = CSVGenerator(data, delimiter=CSVDelimiter.TAB)
        result = generator.generate()
        
        decoded = result.decode('utf-8-sig')
        assert "name\tprice" in decoded

    def test_generate_with_quotes(self):
        """Тест экранирования кавычек."""
        data = [
            {"name": 'Товар "Премиум"', "price": 100},
        ]
        generator = CSVGenerator(data)
        result = generator.generate()
        
        decoded = result.decode('utf-8-sig')
        assert '"Товар ""Премиум"""' in decoded or 'Товар "Премиум"' in decoded

    def test_content_type(self):
        """Тест MIME-типа."""
        generator = CSVGenerator([])
        assert generator.get_content_type() == "text/csv"

    def test_extension(self):
        """Тест расширения файла."""
        generator = CSVGenerator([])
        assert generator.get_extension() == ".csv"


class TestJSONGenerator:
    """Тесты генератора JSON."""

    def test_generate_array_mode(self):
        """Тест режима массива."""
        data = [
            {"name": "Товар 1", "price": 100},
            {"name": "Товар 2", "price": 200},
        ]
        generator = JSONGenerator(data, mode="array")
        result = generator.generate()
        
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "Товар 1"

    def test_generate_meta_with_rows_mode(self):
        """Тест режима с мета-информацией."""
        data = [
            {"name": "Товар 1", "price": 100},
        ]
        meta = {"export_type": "orders", "version": "1.0"}
        generator = JSONGenerator(data, mode="meta_with_rows", meta=meta)
        result = generator.generate()
        
        assert isinstance(result, bytes)
        parsed = json.loads(result)
        assert "meta" in parsed
        assert "rows" in parsed
        assert parsed["meta"]["export_type"] == "orders"
        assert parsed["meta"]["count"] == 1
        assert "generated_at" in parsed["meta"]

    def test_generate_invalid_mode(self):
        """Тест неверного режима."""
        data = [{"name": "Товар 1"}]
        with pytest.raises(ValueError, match="Неизвестный режим JSON"):
            generator = JSONGenerator(data, mode="invalid")
            generator.generate()

    def test_content_type(self):
        """Тест MIME-типа."""
        generator = JSONGenerator([])
        assert generator.get_content_type() == "application/json"

    def test_extension(self):
        """Тест расширения файла."""
        generator = JSONGenerator([])
        assert generator.get_extension() == ".json"


class TestYMLGenerator:
    """Тесты генератора YML."""

    def test_generate_basic(self):
        """Базовый тест генерации YML."""
        offers = [
            {
                "id": "123",
                "name": "Товар 1",
                "price": 1000,
                "category_id": "1",
                "vendor": "Производитель",
            }
        ]
        categories = [{"id": "1", "name": "Категория 1"}]
        generator = YMLGenerator(offers, categories=categories)
        result = generator.generate()
        
        assert isinstance(result, bytes)
        xml_string = result.decode('utf-8')
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml_string
        assert '<yml_catalog' in xml_string
        assert '<shop>' in xml_string
        assert '<name>' in xml_string
        assert '<offer>' in xml_string
        assert '<id>123</id>' in xml_string

    def test_generate_with_pictures(self):
        """Тест с изображениями."""
        offers = [
            {
                "id": "123",
                "name": "Товар 1",
                "price": 1000,
                "picture": ["https://example.com/img1.jpg", "https://example.com/img2.jpg"],
            }
        ]
        generator = YMLGenerator(offers)
        result = generator.generate()
        
        xml_string = result.decode('utf-8')
        assert '<picture>https://example.com/img1.jpg</picture>' in xml_string
        assert '<picture>https://example.com/img2.jpg</picture>' in xml_string

    def test_generate_xml_escaping(self):
        """Тест экранирования XML-символов."""
        offers = [
            {
                "id": "123",
                "name": "Товар & <Спец>символы\"'",
                "price": 1000,
            }
        ]
        generator = YMLGenerator(offers)
        result = generator.generate()
        
        xml_string = result.decode('utf-8')
        # Проверяем, что спецсимволы экранированы
        assert "&amp;" in xml_string
        assert "&lt;" in xml_string
        assert "&gt;" in xml_string
        assert "&quot;" in xml_string
        assert "&apos;" in xml_string

    def test_generate_with_custom_shop_info(self):
        """Тест с кастомной информацией о магазине."""
        offers = [{"id": "123", "name": "Товар", "price": 1000}]
        shop_info = {
            "name": "Мой Магазин",
            "company": "ООО Ромашка",
            "url": "https://myshop.ru",
        }
        generator = YMLGenerator(offers, shop_info=shop_info)
        result = generator.generate()
        
        xml_string = result.decode('utf-8')
        assert "<name>Мой Магазин</name>" in xml_string
        assert "<company>ООО Ромашка</company>" in xml_string
        assert "<url>https://myshop.ru</url>" in xml_string

    def test_content_type(self):
        """Тест MIME-типа."""
        generator = YMLGenerator([])
        assert generator.get_content_type() == "application/xml"

    def test_extension(self):
        """Тест расширения файла."""
        generator = YMLGenerator([])
        assert generator.get_extension() == ".yml"


class TestFileGeneratorFactory:
    """Тесты фабрики генераторов."""

    def test_create_xlsx(self):
        """Тест создания XLSX генератора."""
        generator = FileGeneratorFactory.create(FileFormat.XLSX, [])
        assert isinstance(generator, XLSXGenerator)

    def test_create_csv(self):
        """Тест создания CSV генератора."""
        generator = FileGeneratorFactory.create(FileFormat.CSV, [])
        assert isinstance(generator, CSVGenerator)

    def test_create_csv_with_params(self):
        """Тест создания CSV генератора с параметрами."""
        generator = FileGeneratorFactory.create(
            FileFormat.CSV,
            [],
            encoding=CSVEncoding.WINDOWS_1251,
            delimiter=CSVDelimiter.COMMA,
        )
        assert isinstance(generator, CSVGenerator)
        assert generator.encoding == CSVEncoding.WINDOWS_1251
        assert generator.delimiter == CSVDelimiter.COMMA

    def test_create_json(self):
        """Тест создания JSON генератора."""
        generator = FileGeneratorFactory.create(FileFormat.JSON, [])
        assert isinstance(generator, JSONGenerator)

    def test_create_json_with_params(self):
        """Тест создания JSON генератора с параметрами."""
        generator = FileGeneratorFactory.create(
            FileFormat.JSON,
            [],
            mode="meta_with_rows",
            meta={"test": "value"},
        )
        assert isinstance(generator, JSONGenerator)
        assert generator.mode == "meta_with_rows"

    def test_create_yml(self):
        """Тест создания YML генератора."""
        generator = FileGeneratorFactory.create(FileFormat.YML, [])
        assert isinstance(generator, YMLGenerator)

    def test_create_invalid_format(self):
        """Тест неверного формата."""
        with pytest.raises(ValueError, match="Неподдерживаемый формат"):
            FileGeneratorFactory.create("invalid", [])
