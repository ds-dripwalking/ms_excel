"""
Тесты для клиента МойСклад API с поддержкой JWT аутентификации.
Спецификация: integration.md §11.2, пункты аудита A11, A12, B2-B6
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.moysklad.api_client import (
    MoyskladClient,
    MoyskladAPIError,
    MoyskladRateLimitError,
    MoyskladUnauthorizedError,
    MoyskladForbiddenError,
)
from app.services.jwt_outbound import OutboundJWTService


class TestMoyskladClientAuth:
    """Тесты аутентификации клиента."""

    def test_oauth_bearer_auth_headers(self):
        """Тест: OAuth Bearer токен в заголовках."""
        client = MoyskladClient(access_token="test-oauth-token")
        headers = client._get_auth_headers()
        
        assert headers["Authorization"] == "Bearer test-oauth-token"
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept-Encoding"] == "gzip"
        assert not client.use_app_jwt

    def test_app_jwt_auth_headers(self):
        """Тест: JWT приложения в заголовках."""
        secret_key = "test-secret-key-for-audit-2025-min32b"
        client = MoyskladClient(
            access_token=secret_key,
            use_app_jwt=True,
            app_uid="test-app-uid-12345"
        )
        
        assert client.use_app_jwt
        assert client.app_uid == "test-app-uid-12345"
        
        headers = client._get_auth_headers()
        
        # JWT должен быть сгенерирован
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept-Encoding"] == "gzip"
        
        # Проверяем валидность JWT
        jwt_token = headers["Authorization"].replace("Bearer ", "")
        service = OutboundJWTService(secret_key=secret_key)
        payload = service.verify_token(jwt_token)
        
        assert payload["sub"] == "test-app-uid-12345"
        assert "jti" in payload
        assert "exp" in payload

    def test_jwt_unique_per_request(self):
        """Тест: каждый запрос получает уникальный JWT (разные jti)."""
        secret_key = "test-secret-key-for-audit-2025-min32b"
        client = MoyskladClient(
            access_token=secret_key,
            use_app_jwt=True,
            app_uid="test-app-uid-12345"
        )
        
        headers1 = client._get_auth_headers()
        headers2 = client._get_auth_headers()
        
        token1 = headers1["Authorization"].replace("Bearer ", "")
        token2 = headers2["Authorization"].replace("Bearer ", "")
        
        service = OutboundJWTService(secret_key=secret_key)
        payload1 = service.verify_token(token1)
        payload2 = service.verify_token(token2)
        
        # jti должны быть уникальны
        assert payload1["jti"] != payload2["jti"]


class TestMoyskladClientPagination:
    """Тесты пагинации (пункт аудита B2)."""

    @pytest.mark.asyncio
    async def test_get_all_paginated_complete_cycle(self):
        """Тест: полный цикл пагинации до исчерпания выборки."""
        client = MoyskladClient(access_token="test-token")
        
        # Мок ответов API: 3 страницы по 1000 записей
        mock_responses = [
            {"rows": [{"id": f"page1-item{i}"} for i in range(1000)]},
            {"rows": [{"id": f"page2-item{i}"} for i in range(1000)]},
            {"rows": [{"id": f"page3-item{i}"} for i in range(500)]},  # Последняя страница
        ]
        
        with patch.object(client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = mock_responses
            
            result = await client.get_all_paginated(
                endpoint="entity/product",
                max_records=None,
            )
        
        # Должно быть 3 вызова (по количеству страниц)
        assert mock_get.call_count == 3
        
        # Проверка параметров вызовов
        calls = mock_get.call_args_list
        assert calls[0][1]["limit"] == 1000
        assert calls[0][1]["offset"] == 0
        
        assert calls[1][1]["limit"] == 1000
        assert calls[1][1]["offset"] == 1000
        
        assert calls[2][1]["limit"] == 1000
        assert calls[2][1]["offset"] == 2000
        
        # Итого 2500 записей
        assert len(result) == 2500

    @pytest.mark.asyncio
    async def test_get_all_paginated_with_max_records(self):
        """Тест: пагинация с ограничением max_records."""
        client = MoyskladClient(access_token="test-token")
        
        mock_responses = [
            {"rows": [{"id": f"item{i}"} for i in range(1000)]},
            {"rows": [{"id": f"item{i}"} for i in range(1000)]},
            {"rows": [{"id": f"item{i}"} for i in range(1000)]},
        ]
        
        with patch.object(client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = mock_responses
            
            result = await client.get_all_paginated(
                endpoint="entity/product",
                max_records=1500,
            )
        
        # Должно остановиться после 2 страниц (2000 > 1500)
        assert mock_get.call_count == 2
        assert len(result) == 2000  # Получили 2 страницы, но цикл остановился


class TestMoyskladClientExpand:
    """Тесты expand для заказов (пункт аудита B4)."""

    @pytest.mark.asyncio
    async def test_get_customer_orders_default_expand(self):
        """Тест: заказы покупателей с default expand."""
        client = MoyskladClient(access_token="test-token")
        
        expected_expand = ["organization", "store", "agent", "positions.assortment"]
        
        with patch.object(client, 'get_all_paginated', new_callable=AsyncMock) as mock_paginated:
            mock_paginated.return_value = []
            
            await client.get_customer_orders()
        
        # Проверка что expand передан правильно
        call_args = mock_paginated.call_args
        assert call_args[1]["expand"] == expected_expand

    @pytest.mark.asyncio
    async def test_get_customer_orders_custom_expand(self):
        """Тест: заказы с кастомным expand переопределяет default."""
        client = MoyskladClient(access_token="test-token")
        
        custom_expand = ["organization", "store"]
        
        with patch.object(client, 'get_all_paginated', new_callable=AsyncMock) as mock_paginated:
            mock_paginated.return_value = []
            
            await client.get_customer_orders(expand=custom_expand)
        
        call_args = mock_paginated.call_args
        assert call_args[1]["expand"] == custom_expand


class TestMoyskladClientPriceTypes:
    """Тесты типов цен (пункт аудита B7)."""

    @pytest.mark.asyncio
    async def test_get_price_types_endpoint(self):
        """Тест: получение типов цен из /context/companysettings/pricetype."""
        client = MoyskladClient(access_token="test-token")
        
        mock_response = {
            "rows": [
                {"id": "pt1", "name": "Розничная цена"},
                {"id": "pt2", "name": "Оптовая цена"},
            ]
        }
        
        with patch.object(client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            result = await client.get_price_types()
        
        mock_get.assert_called_once_with("context/companysettings/pricetype")
        assert len(result) == 2
        assert result[0]["name"] == "Розничная цена"


class TestMoyskladClientAppStatus:
    """Тесты обновления статуса приложения (пункт аудита A12)."""

    @pytest.mark.asyncio
    async def test_update_app_status_activated(self):
        """Тест: обновление статуса на Activated."""
        client = MoyskladClient(
            access_token="secret-key",
            use_app_jwt=True,
            app_uid="test-app-uid"
        )
        
        mock_response = {"status": "success"}
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await client.update_app_status(
                app_id="app-123",
                account_id="acc-456",
                status="Activated",
            )
        
        # Проверка вызова
        mock_request.assert_called_once_with(
            method="PUT",
            endpoint="/vendor/1.0/apps/app-123/acc-456/status",
            json_data={"status": "Activated"},
            use_apps_api=True,
        )
        assert result == mock_response

    @pytest.mark.asyncio
    async def test_update_app_status_with_comment(self):
        """Тест: обновление статуса с комментарием."""
        client = MoyskladClient(access_token="secret-key", use_app_jwt=True)
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "success"}
            
            await client.update_app_status(
                app_id="app-123",
                account_id="acc-456",
                status="SettingsRequired",
                comment="Требуется настройка профилей экспорта",
            )
        
        call_args = mock_request.call_args
        assert call_args[1]["json_data"]["comment"] == "Требуется настройка профилей экспорта"


class TestMoyskladClientRateLimit:
    """Тесты rate limiting (пункт аудита B3)."""

    def test_rate_limit_default(self):
        """Тест: rate limit по умолчанию 4 rps."""
        client = MoyskladClient(access_token="test-token")
        assert client.rate_limit == 4

    def test_rate_limit_custom(self):
        """Тест: кастомный rate limit."""
        client = MoyskladClient(access_token="test-token", rate_limit=3.0)
        assert client.rate_limit == 3.0

    @pytest.mark.asyncio
    async def test_rate_limit_wait(self):
        """Тест: ожидание между запросами."""
        client = MoyskladClient(access_token="test-token", rate_limit=10.0)  # 10 rps = 0.1s
        
        await client._rate_limit_wait()
        first_time = client._last_request_time
        
        await client._rate_limit_wait()
        second_time = client._last_request_time
        
        # Между запросами должно пройти минимум 0.1 сек
        elapsed = (second_time - first_time).total_seconds()
        assert elapsed >= 0.09  # Небольшой допуск
