"""
Модели данных для кэша справочников МойСклад JSON API.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint, Index, JSON as SQLAlchemyJSON
from sqlalchemy.orm import relationship
from app.database import Base


class DictionaryCache(Base):
    """Кэш справочников МойСклад."""
    __tablename__ = "dictionary_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("moysklad_accounts.id"), nullable=False, index=True)
    
    # Тип справочника: organization, store, currency, productfolder, pricetype, customerorder_metadata, product_metadata
    dictionary_type = Column(String(100), nullable=False)
    
    # Данные справочника (JSON)
    data = Column(SQLAlchemyJSON, nullable=False)
    
    # Дата создания/обновления кэша
    cached_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # TTL в секундах (для разных типов может отличаться)
    ttl_seconds = Column(Integer, default=3600, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('account_id', 'dictionary_type', name='uq_dict_cache_account_type'),
        Index('idx_dict_cache_expiry', 'cached_at', 'ttl_seconds'),
    )


class ExportJob(Base):
    """Задания на выгрузку."""
    __tablename__ = "export_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("integration_profiles.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("moysklad_accounts.id"), nullable=False, index=True)
    
    # Статус задания: pending, running, completed, failed, cancelled
    status = Column(String(50), default="pending", nullable=False, index=True)
    
    # Тип выгрузки: customer_orders, price_list
    export_type = Column(String(50), nullable=False)
    
    # Параметры выгрузки (JSON): фильтры, период, настройки
    parameters = Column(SQLAlchemyJSON, nullable=True)
    
    # Дата начала выполнения
    started_at = Column(DateTime, nullable=True)
    
    # Дата завершения
    completed_at = Column(DateTime, nullable=True)
    
    # Сообщение об ошибке
    error_message = Column(Text, nullable=True)
    
    # Путь к файлу результата (если успешно)
    result_file_path = Column(String(500), nullable=True)
    
    # URL для скачивания (если облачное хранилище)
    download_url = Column(String(1000), nullable=True)
    
    # Количество обработанных записей
    records_processed = Column(Integer, default=0, nullable=False)
    
    # Дата создания
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    profile = relationship("IntegrationProfile", backref="export_jobs")
    account = relationship("MoyskladAccount", backref="export_jobs")


class JobEvent(Base):
    """Журнал событий заданий."""
    __tablename__ = "job_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("export_jobs.id"), nullable=False, index=True)
    
    # Тип события: started, progress, completed, failed, cancelled, api_request, api_error
    event_type = Column(String(50), nullable=False, index=True)
    
    # Сообщение
    message = Column(Text, nullable=True)
    
    # Детали (JSON)
    details = Column(SQLAlchemyJSON, nullable=True)
    
    # Дата события
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Связь
    job = relationship("ExportJob", backref="events")
