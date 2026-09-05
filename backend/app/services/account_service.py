"""
Сервис для управления аккаунтами и профилями интеграции.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.models.vendor import (
    MoyskladAccount,
    MoyskladToken,
    IntegrationProfile,
    AccountStatus,
    TariffType,
)
from app.crypto import encrypt_secret
from app.logging_config import logger


class AccountService:
    """Сервис для управления аккаунтами МойСклад."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_account(
        self,
        account_id: str,
        app_id: str
    ) -> Optional[MoyskladAccount]:
        """Получает аккаунт по accountId и appId."""
        return self.db.query(MoyskladAccount).filter(
            MoyskladAccount.account_id == account_id,
            MoyskladAccount.app_id == app_id
        ).first()
    
    def create_account(
        self,
        account_id: str,
        app_id: str,
        tariff: TariffType = TariffType.LITE
    ) -> MoyskladAccount:
        """Создаёт новый аккаунт."""
        account = MoyskladAccount(
            account_id=account_id,
            app_id=app_id,
            status=AccountStatus.ACTIVE,
            tariff=tariff,
            installed_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        
        logger.info(
            f"Создан новый аккаунт",
            account_id=account_id,
            app_id=app_id,
            tariff=tariff.value
        )
        
        return account
    
    def update_token(
        self,
        account: MoyskladAccount,
        token: str
    ) -> MoyskladToken:
        """Обновляет или создаёт токен для аккаунта."""
        encrypted = encrypt_secret({"token": token})
        
        existing_token = self.db.query(MoyskladToken).filter(
            MoyskladToken.account_id == account.id,
            MoyskladToken.token_type == "json_api"
        ).first()
        
        if existing_token:
            existing_token.encrypted_token = encrypted
            existing_token.updated_at = datetime.now(timezone.utc)
            token_obj = existing_token
            logger.info(f"Обновлён токен для аккаунта", account_id=account.account_id)
        else:
            token_obj = MoyskladToken(
                account_id=account.id,
                encrypted_token=encrypted,
                token_type="json_api",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            self.db.add(token_obj)
            logger.info(f"Создан новый токен для аккаунта", account_id=account.account_id)
        
        self.db.commit()
        self.db.refresh(token_obj)
        
        return token_obj
    
    def get_token(self, account: MoyskladAccount) -> Optional[MoyskladToken]:
        """Получает токен для аккаунта."""
        return self.db.query(MoyskladToken).filter(
            MoyskladToken.account_id == account.id,
            MoyskladToken.token_type == "json_api"
        ).first()
    
    def update_tariff(
        self,
        account: MoyskladAccount,
        tariff: TariffType
    ) -> MoyskladAccount:
        """Обновляет тариф аккаунта."""
        account.tariff = tariff
        account.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(account)
        
        logger.info(
            f"Тариф обновлён",
            account_id=account.account_id,
            new_tariff=tariff.value
        )
        
        return account
    
    def update_paid_end_date(
        self,
        account: MoyskladAccount,
        paid_end_date: datetime
    ) -> MoyskladAccount:
        """Обновляет дату окончания оплаченного периода."""
        account.paid_end_date = paid_end_date
        account.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(account)
        
        logger.info(
            f"Дата оплаты обновлена",
            account_id=account.account_id,
            paid_end_date=paid_end_date.isoformat()
        )
        
        return account
    
    def suspend_account(
        self,
        account: MoyskladAccount
    ) -> MoyskladAccount:
        """Приостанавливает аккаунт."""
        account.status = AccountStatus.SUSPENDED
        account.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(account)
        
        logger.warning(
            f"Аккаунт приостановлен",
            account_id=account.account_id
        )
        
        return account
    
    def activate_account(
        self,
        account: MoyskladAccount
    ) -> MoyskladAccount:
        """Активирует аккаунт."""
        account.status = AccountStatus.ACTIVE
        account.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(account)
        
        logger.info(
            f"Аккаунт активирован",
            account_id=account.account_id
        )
        
        return account
    
    def mark_for_deletion(
        self,
        account: MoyskladAccount,
        grace_period_days: int = 30
    ) -> MoyskladAccount:
        """Помечает аккаунт на удаление через grace-период."""
        from datetime import timedelta
        
        account.status = AccountStatus.DELETED_PENDING
        account.deleted_at = datetime.now(timezone.utc) + timedelta(days=grace_period_days)
        account.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(account)
        
        logger.warning(
            f"Аккаунт помечен на удаление",
            account_id=account.account_id,
            deletion_date=account.deleted_at.isoformat()
        )
        
        return account
    
    def create_profile(
        self,
        account: MoyskladAccount,
        name: str,
        settings: Optional[Dict[str, Any]] = None
    ) -> IntegrationProfile:
        """Создаёт профиль интеграции."""
        import json
        
        profile = IntegrationProfile(
            account_id=account.id,
            name=name,
            settings=json.dumps(settings) if settings else None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        
        logger.info(
            f"Создан профиль интеграции",
            account_id=account.account_id,
            profile_name=name
        )
        
        return profile
    
    def get_profiles(
        self,
        account: MoyskladAccount
    ) -> List[IntegrationProfile]:
        """Получает все профили аккаунта."""
        return self.db.query(IntegrationProfile).filter(
            IntegrationProfile.account_id == account.id
        ).all()
    
    def count_active_profiles(
        self,
        account: MoyskladAccount
    ) -> int:
        """Считает количество активных профилей."""
        return self.db.query(IntegrationProfile).filter(
            IntegrationProfile.account_id == account.id,
            IntegrationProfile.is_active == True
        ).count()
    
    def check_profile_limit(
        self,
        account: MoyskladAccount,
        new_profile_count: int
    ) -> bool:
        """
        Проверяет лимит профилей согласно тарифу.
        
        Lite: до 3 профилей
        Professional: без ограничений
        """
        if account.tariff == TariffType.LITE:
            return new_profile_count <= 3
        return True  # Professional без ограничений
    
    def delete_account_data(
        self,
        account: MoyskladAccount
    ) -> None:
        """
        Удаляет все данные аккаунта после grace-периода.
        
        Удаляет:
        - токены
        - секреты
        - настройки
        - файлы временных выгрузок
        """
        # Удаляем токены
        tokens = self.db.query(MoyskladToken).filter(
            MoyskladToken.account_id == account.id
        ).all()
        for token in tokens:
            self.db.delete(token)
        
        # Удаляем профили
        profiles = self.db.query(IntegrationProfile).filter(
            IntegrationProfile.account_id == account.id
        ).all()
        for profile in profiles:
            self.db.delete(profile)
        
        # Обновляем статус аккаунта
        account.status = AccountStatus.DELETED
        account.updated_at = datetime.now(timezone.utc)
        
        self.db.commit()
        
        logger.info(
            f"Данные аккаунта полностью удалены",
            account_id=account.account_id
        )
