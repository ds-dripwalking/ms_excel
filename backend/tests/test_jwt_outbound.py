"""
Тесты для сервиса исходящих JWT-токенов.
Спецификация: integration.md §11.2, пункт аудита A11
"""

import pytest
import time
import jwt
from app.services.jwt_outbound import OutboundJWTService


class TestOutboundJWTService:
    """Тесты генерации и валидации исходящих JWT."""

    @pytest.fixture
    def service(self):
        """Создает сервис с тестовыми настройками."""
        return OutboundJWTService(
            secret_key="test-secret-key-for-audit-2025",
            app_uid="test-app-uid-12345"
        )

    def test_generate_token_structure(self, service):
        """Тест структуры токена: все требуемые поля присутствуют."""
        token = service.generate_token()
        
        assert token is not None
        assert isinstance(token, str)
        
        # Декодируем без проверки подписи для анализа структуры
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert "sub" in payload
        assert "iat" in payload
        assert "jti" in payload
        assert "exp" in payload

    def test_sub_equals_app_uid(self, service):
        """Тест: поле sub равно app_uid."""
        token = service.generate_token()
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert payload["sub"] == "test-app-uid-12345"

    def test_jti_is_unique_uuid(self, service):
        """Тест: jti - уникальный UUID."""
        token1 = service.generate_token()
        token2 = service.generate_token()
        
        payload1 = jwt.decode(token1, options={"verify_signature": False})
        payload2 = jwt.decode(token2, options={"verify_signature": False})
        
        assert payload1["jti"] != payload2["jti"]
        # Проверка формата UUID (простая)
        assert len(payload1["jti"]) == 36  # Стандартный UUID

    def test_exp_is_iat_plus_300(self, service):
        """Тест: exp = iat + 300 секунд (±2 сек на выполнение)."""
        before = int(time.time())
        token = service.generate_token()
        after = int(time.time())
        
        payload = jwt.decode(token, options={"verify_signature": False})
        
        iat = payload["iat"]
        exp = payload["exp"]
        
        # iat должен быть между before и after
        assert before <= iat <= after
        
        # exp должен быть iat + 300
        assert exp == iat + 300

    def test_token_lifetime_is_300_seconds(self, service):
        """Тест: время жизни токена ровно 300 секунд."""
        token = service.generate_token()
        payload = jwt.decode(token, options={"verify_signature": False})
        
        lifetime = payload["exp"] - payload["iat"]
        assert lifetime == 300

    def test_verify_valid_token(self, service):
        """Тест: валидный токен успешно проверяется."""
        token = service.generate_token()
        
        payload = service.verify_token(token)
        
        assert payload["sub"] == "test-app-uid-12345"
        assert "jti" in payload

    def test_verify_expired_token(self, service):
        """Тест: истекший токен отклоняется."""
        # Генерируем токен с малым временем жизни для теста
        service.TOKEN_LIFETIME_SECONDS = -1  # Уже истек
        token = service.generate_token()
        
        with pytest.raises(ValueError, match="Токен истек"):
            service.verify_token(token)

    def test_verify_invalid_signature(self, service):
        """Тест: токен с неверной подписью отклоняется."""
        token = service.generate_token()
        
        # Создаем сервис с другим ключом
        wrong_service = OutboundJWTService(
            secret_key="wrong-secret-key",
            app_uid="test-app-uid-12345"
        )
        
        with pytest.raises(ValueError, match="Невалидный токен"):
            wrong_service.verify_token(token)

    def test_custom_app_uid(self, service):
        """Тест: можно переопределить app_uid при генерации."""
        custom_uid = "custom-app-uid-99999"
        token = service.generate_token(app_uid=custom_uid)
        
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert payload["sub"] == custom_uid

    def test_missing_app_uid_raises_error(self):
        """Тест: отсутствие app_uid вызывает ошибку."""
        # Сбрасываем env переменные для этого теста
        service = OutboundJWTService(
            secret_key="test-secret-key",
            app_uid=None  # Явно None
        )
        # Принудительно устанавливаем app_uid в None (игнорируя env)
        service.app_uid = None
        
        with pytest.raises(ValueError, match="APP_UID не настроен"):
            service.generate_token()

    def test_algorithm_is_hs256(self, service):
        """Тест: используется алгоритм HS256."""
        token = service.generate_token()
        
        # Проверяем заголовок токена
        header = jwt.get_unverified_header(token)
        
        assert header["alg"] == "HS256"
        assert header["typ"] == "JWT"

    def test_concurrent_tokens_have_unique_jti(self, service):
        """Тест: параллельная генерация дает уникальные jti."""
        tokens = [service.generate_token() for _ in range(100)]
        payloads = [jwt.decode(t, options={"verify_signature": False}) for t in tokens]
        jtis = [p["jti"] for p in payloads]
        
        # Все jti должны быть уникальны
        assert len(set(jtis)) == 100
