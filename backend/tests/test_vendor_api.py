"""
Тесты для Vendor API МойСклад.

Проверяют:
1. Валидацию JWT токенов
2. Идемпотентность (повторные запросы с тем же jti)
3. Обработку различных событий (Install, Resume, TariffChanged, Autoprolongation, Suspend, Uninstall)
"""
import os
import base64
import jwt
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from fastapi import HTTPException

# Настраиваем тестовую базу данных
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Импортируем модели и создаём таблицы
from app.database import Base
from app.models.vendor import (
    MoyskladAccount,
    MoyskladToken,
    IntegrationProfile,
    ProcessedJTI,
    AccountStatus,
    TariffType,
)
Base.metadata.create_all(bind=engine)


# Устанавливаем тестовый мастер-ключ
TEST_MASTER_KEY = os.urandom(32)
os.environ["MASTER_KEY"] = base64.b64encode(TEST_MASTER_KEY).decode("ascii")

# Тестовый секретный ключ для JWT
TEST_SECRET_KEY = "test-secret-key-for-jwt-validation"


@pytest.fixture
def db_session():
    """Создаёт новую сессию БД для каждого теста."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    """Создаёт тестовый клиент FastAPI."""
    from app.api.vendor import router
    from fastapi import FastAPI
    
    app = FastAPI()
    app.include_router(router)
    
    # Переопределяем зависимость get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    # Переопределяем зависимость get_mysklad_secret_key
    def override_get_secret():
        return TEST_SECRET_KEY
    
    app.dependency_overrides[override_get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


def create_jwt_token(secret_key: str, jti: str, exp_minutes: int = 5) -> str:
    """Создаёт тестовый JWT токен."""
    payload = {
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=exp_minutes)).timestamp()),
        "jti": jti,
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


class TestJWTValidation:
    """Тесты валидации JWT токенов."""
    
    def test_valid_jwt(self, db_session):
        """Валидный JWT токен должен проходить проверку."""
        jti = "test-jti-123"
        token = create_jwt_token(TEST_SECRET_KEY, jti)
        
        from app.services.jwt_auth import validate_mysklad_jwt
        
        payload = validate_mysklad_jwt(token, TEST_SECRET_KEY, db_session)
        
        assert payload["jti"] == jti
        assert "exp" in payload
        assert "iat" in payload
    
    def test_expired_jwt(self, db_session):
        """Просроченный JWT токен должен отклоняться."""
        jti = "test-jti-expired"
        token = create_jwt_token(TEST_SECRET_KEY, jti, exp_minutes=-1)
        
        from app.services.jwt_auth import validate_mysklad_jwt, JWTValidationError
        
        with pytest.raises(JWTValidationError, match="истёк|Expired"):
            validate_mysklad_jwt(token, TEST_SECRET_KEY, db_session)
    
    def test_wrong_algorithm_jwt(self, db_session):
        """JWT с неверным алгоритмом должен отклоняться."""
        # Создаём токен с HS384 вместо HS256
        payload = {
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
            "jti": "test-jti-wrong-alg",
        }
        token = jwt.encode(payload, TEST_SECRET_KEY, algorithm="HS384")
        
        from app.services.jwt_auth import validate_mysklad_jwt, JWTValidationError
        
        with pytest.raises(JWTValidationError, match="алгоритм|Algorithm"):
            validate_mysklad_jwt(token, TEST_SECRET_KEY, db_session)
    
    def test_reused_jti(self, db_session):
        """Повторное использование jti должно отклоняться."""
        jti = "test-jti-reuse"
        token = create_jwt_token(TEST_SECRET_KEY, jti)
        
        from app.services.jwt_auth import validate_mysklad_jwt, mark_jti_as_used, JWTValidationError
        
        # Первый раз должен пройти
        payload = validate_mysklad_jwt(token, TEST_SECRET_KEY, db_session)
        assert payload["jti"] == jti
        
        # Отмечаем jti как использованный
        mark_jti_as_used(db_session, jti, request_id="test-request-1")
        
        # Второй раз должен отклониться
        token2 = create_jwt_token(TEST_SECRET_KEY, jti)
        with pytest.raises(JWTValidationError, match="уже был использован"):
            validate_mysklad_jwt(token2, TEST_SECRET_KEY, db_session)


class TestIdempotency:
    """Тесты идемпотентности."""
    
    def test_mark_jti_as_used(self, db_session):
        """Отметка jti как использованного."""
        from app.services.jwt_auth import mark_jti_as_used
        
        jti = "test-jti-mark"
        result = mark_jti_as_used(
            db_session,
            jti,
            request_id="test-request-123",
            operation_type="Install",
            account_id="test-account-123"
        )
        
        assert result.jti == jti
        assert result.request_id == "test-request-123"
        assert result.operation_type == "Install"
        assert result.account_id == "test-account-123"
    
    def test_get_existing_jti(self, db_session):
        """Получение существующего jti."""
        from app.services.jwt_auth import mark_jti_as_used, get_existing_jti
        
        jti = "test-jti-existing"
        mark_jti_as_used(db_session, jti, request_id="test-request-456")
        
        existing = get_existing_jti(db_session, jti)
        
        assert existing is not None
        assert existing.jti == jti
        assert existing.request_id == "test-request-456"
        
        # Несуществующий jti
        non_existing = get_existing_jti(db_session, "non-existent-jti")
        assert non_existing is None


class TestAccountService:
    """Тесты сервиса аккаунтов."""
    
    def test_create_account(self, db_session):
        """Создание нового аккаунта."""
        from app.services.account_service import AccountService
        
        service = AccountService(db_session)
        account = service.create_account(
            account_id="test-account-id",
            app_id="test-app-id",
            tariff=TariffType.LITE
        )
        
        assert account.account_id == "test-account-id"
        assert account.app_id == "test-app-id"
        assert account.status == AccountStatus.ACTIVE
        assert account.tariff == TariffType.LITE
    
    def test_get_account(self, db_session):
        """Получение аккаунта."""
        from app.services.account_service import AccountService
        
        service = AccountService(db_session)
        
        # Создаём аккаунт
        created = service.create_account("acc-123", "app-123")
        
        # Получаем аккаунт
        retrieved = service.get_account("acc-123", "app-123")
        
        assert retrieved is not None
        assert retrieved.id == created.id
        
        # Несуществующий аккаунт
        not_found = service.get_account("non-existent", "app-123")
        assert not_found is None
    
    def test_update_token(self, db_session):
        """Обновление токена аккаунта."""
        from app.services.account_service import AccountService
        
        service = AccountService(db_session)
        account = service.create_account("acc-token-test", "app-123")
        
        token = service.update_token(account, "test-token-123")
        
        assert token is not None
        assert token.account_id == account.id
        
        # Обновляем тот же токен
        token2 = service.update_token(account, "new-token-456")
        assert token2.id == token.id  # Тот же объект
    
    def test_suspend_account(self, db_session):
        """Приостановка аккаунта."""
        from app.services.account_service import AccountService
        
        service = AccountService(db_session)
        account = service.create_account("acc-suspend", "app-123")
        
        suspended = service.suspend_account(account)
        
        assert suspended.status == AccountStatus.SUSPENDED
    
    def test_activate_account(self, db_session):
        """Активация аккаунта."""
        from app.services.account_service import AccountService
        
        service = AccountService(db_session)
        account = service.create_account("acc-activate", "app-123")
        service.suspend_account(account)
        
        activated = service.activate_account(account)
        
        assert activated.status == AccountStatus.ACTIVE
    
    def test_mark_for_deletion(self, db_session):
        """Пометка аккаунта на удаление."""
        from app.services.account_service import AccountService
        from datetime import timedelta
        
        service = AccountService(db_session)
        account = service.create_account("acc-delete", "app-123")
        
        deleted = service.mark_for_deletion(account, grace_period_days=30)
        
        assert deleted.status == AccountStatus.DELETED_PENDING
        assert deleted.deleted_at is not None
        assert deleted.deleted_at > datetime.now(timezone.utc)
    
    def test_tariff_limits(self, db_session):
        """Проверка лимитов тарифов."""
        from app.services.account_service import AccountService
        
        service = AccountService(db_session)
        
        # Lite тариф - максимум 3 профиля
        lite_account = service.create_account("acc-lite", "app-123", TariffType.LITE)
        
        assert service.check_profile_limit(lite_account, 1) == True
        assert service.check_profile_limit(lite_account, 3) == True
        assert service.check_profile_limit(lite_account, 4) == False
        
        # Professional тариф - без ограничений
        prof_account = service.create_account("acc-prof", "app-123", TariffType.PROFESSIONAL)
        
        assert service.check_profile_limit(prof_account, 1) == True
        assert service.check_profile_limit(prof_account, 100) == True
        assert service.check_profile_limit(prof_account, 1000) == True


class TestVendorEndpoints:
    """Тесты эндпоинтов Vendor API."""
    
    def test_install_cause(self, client, db_session):
        """Тест установки приложения (Install)."""
        jti = "test-install-jti"
        token = create_jwt_token(TEST_SECRET_KEY, jti)
        
        response = client.put(
            "/api/moysklad/vendor/1.0/apps/test-app-id/test-account-id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "cause": "Install",
                "token": "test-mysklad-token",
                "subscription": {
                    "tariffPlanName": "Lite",
                    "paidEndDate": "2025-12-31T23:59:59Z"
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SettingsRequired"
    
    def test_resume_cause(self, client, db_session):
        """Тест возобновления приложения (Resume)."""
        from app.services.account_service import AccountService
        
        # Создаём приостановленный аккаунт
        service = AccountService(db_session)
        account = service.create_account("test-resume-acc", "test-app-id")
        service.suspend_account(account)
        
        jti = "test-resume-jti"
        token = create_jwt_token(TEST_SECRET_KEY, jti)
        
        response = client.put(
            "/api/moysklad/vendor/1.0/apps/test-app-id/test-resume-acc",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "cause": "Resume",
                "token": "new-token",
                "subscription": {
                    "tariffPlanName": "Professional",
                    "paidEndDate": "2025-12-31T23:59:59Z"
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Activated"
        
        # Проверяем, что аккаунт активирован
        updated_account = service.get_account("test-resume-acc", "test-app-id")
        assert updated_account.status == AccountStatus.ACTIVE
    
    def test_tariff_changed_cause(self, client, db_session):
        """Тест смены тарифа (TariffChanged)."""
        from app.services.account_service import AccountService
        
        # Создаём аккаунт с Lite тарифом
        service = AccountService(db_session)
        account = service.create_account("test-tariff-acc", "test-app-id", TariffType.LITE)
        
        jti = "test-tariff-jti"
        token = create_jwt_token(TEST_SECRET_KEY, jti)
        
        response = client.put(
            "/api/moysklad/vendor/1.0/apps/test-app-id/test-tariff-acc",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "cause": "TariffChanged",
                "subscription": {
                    "tariffPlanName": "Professional"
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Activated"
        
        # Проверяем, что тариф изменён
        updated_account = service.get_account("test-tariff-acc", "test-app-id")
        assert updated_account.tariff == TariffType.PROFESSIONAL
    
    def test_autoprolongation_cause(self, client, db_session):
        """Тест автопродления (Autoprolongation)."""
        from app.services.account_service import AccountService
        
        # Создаём аккаунт
        service = AccountService(db_session)
        account = service.create_account("test-auto-acc", "test-app-id")
        
        jti = "test-auto-jti"
        token = create_jwt_token(TEST_SECRET_KEY, jti)
        
        paid_end_date = "2026-01-15T00:00:00Z"
        
        response = client.put(
            "/api/moysklad/vendor/1.0/apps/test-app-id/test-auto-acc",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "cause": "Autoprolongation",
                "subscription": {
                    "paidEndDate": paid_end_date
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Activated"
    
    def test_suspend_cause(self, client, db_session):
        """Тест приостановки (Suspend)."""
        from app.services.account_service import AccountService
        
        # Создаём активный аккаунт
        service = AccountService(db_session)
        account = service.create_account("test-suspend-acc", "test-app-id")
        
        jti = "test-suspend-jti"
        token = create_jwt_token(TEST_SECRET_KEY, jti)
        
        response = client.delete(
            "/api/moysklad/vendor/1.0/apps/test-app-id/test-suspend-acc",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "cause": "Suspend"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Deactivated"
        
        # Проверяем, что аккаунт приостановлен
        updated_account = service.get_account("test-suspend-acc", "test-app-id")
        assert updated_account.status == AccountStatus.SUSPENDED
    
    def test_uninstall_cause(self, client, db_session):
        """Тест удаления (Uninstall)."""
        from app.services.account_service import AccountService
        
        # Создаём активный аккаунт
        service = AccountService(db_session)
        account = service.create_account("test-uninstall-acc", "test-app-id")
        
        jti = "test-uninstall-jti"
        token = create_jwt_token(TEST_SECRET_KEY, jti)
        
        response = client.delete(
            "/api/moysklad/vendor/1.0/apps/test-app-id/test-uninstall-acc",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "cause": "Uninstall"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Deactivated"
        
        # Проверяем, что аккаунт помечен на удаление
        updated_account = service.get_account("test-uninstall-acc", "test-app-id")
        assert updated_account.status == AccountStatus.DELETED_PENDING
        assert updated_account.deleted_at is not None
    
    def test_idempotent_request(self, client, db_session):
        """Тест идемпотентности - повторный запрос с тем же jti."""
        from app.services.jwt_auth import mark_jti_as_used
        
        jti = "test-idempotent-jti"
        
        # Сначала отмечаем jti как использованный
        mark_jti_as_used(db_session, jti, request_id="original-request-id", operation_type="Install")
        
        token = create_jwt_token(TEST_SECRET_KEY, jti)
        
        # Повторный запрос должен вернуть результат без создания дубликатов
        response = client.put(
            "/api/moysklad/vendor/1.0/apps/test-app-id/test-idempotent-acc",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "cause": "Install",
                "token": "test-token"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Activated"  # Возвращает предыдущий результат
    
    def test_invalid_jwt(self, client, db_session):
        """Тест невалидного JWT токена."""
        response = client.put(
            "/api/moysklad/vendor/1.0/apps/test-app-id/test-account-id",
            headers={
                "Authorization": "Bearer invalid-token",
                "Content-Type": "application/json",
            },
            json={
                "cause": "Install",
                "token": "test-token"
            }
        )
        
        assert response.status_code == 401
    
    def test_missing_authorization(self, client, db_session):
        """Тест отсутствия заголовка Authorization."""
        response = client.put(
            "/api/moysklad/vendor/1.0/apps/test-app-id/test-account-id",
            headers={
                "Content-Type": "application/json",
            },
            json={
                "cause": "Install",
                "token": "test-token"
            }
        )
        
        assert response.status_code == 401
    
    def test_unknown_cause(self, client, db_session):
        """Тест неизвестного типа события."""
        jti = "test-unknown-cause-jti"
        token = create_jwt_token(TEST_SECRET_KEY, jti)
        
        response = client.put(
            "/api/moysklad/vendor/1.0/apps/test-app-id/test-account-id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "cause": "UnknownCause"
            }
        )
        
        assert response.status_code == 400
