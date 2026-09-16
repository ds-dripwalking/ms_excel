# Graph Report - excel  (2026-09-16)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 770 nodes · 1433 edges · 41 communities (33 shown, 8 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 85 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `02a4e539`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- v1/vendor.py
- MoyskladClient
- package.json
- PriceExportService
- database.py
- OrdersExportService
- crypto.py
- RemoteFileMeta
- encrypt_secret
- GoogleDriveAdapter
- StorageError
- profiles.py
- MoyskladAccount
- TestVendorEndpoints
- BaseStorageAdapter
- SecretStr
- test_vendor_api.py
- schemas/__init__.py
- YandexDiskAdapter
- compilerOptions
- auth.py
- AccountService
- DictionaryCacheService
- decrypt_secret
- factory.py
- MailRuCloudAdapter
- mask_token
- moysklad_api.py
- compilerOptions
- client
- get_current_user_context
- SensitiveFilter
- .__init__
- .create_profile
- .__init__
- .__init__
- .__init__
- .get_profiles

## God Nodes (most connected - your core abstractions)
1. `AccountService` - 47 edges
2. `MoyskladAccount` - 39 edges
3. `MoyskladClient` - 28 edges
4. `StorageError` - 28 edges
5. `BaseStorageAdapter` - 27 edges
6. `GoogleDriveAdapter` - 26 edges
7. `YandexDiskAdapter` - 25 edges
8. `RemoteFileMeta` - 23 edges
9. `MailRuCloudAdapter` - 22 edges
10. `PriceExportService` - 22 edges

## Surprising Connections (you probably didn't know these)
- `PriceExportService` --uses--> `MoyskladClient`  [INFERRED]
  backend/app/services/export/price_export.py → backend/app/services/moysklad/api_client.py
- `GoogleDriveAdapter` --uses--> `AuthError`  [INFERRED]
  backend/app/services/channels/google_drive.py → backend/app/services/channels/base.py
- `MailRuCloudAdapter` --uses--> `AuthError`  [INFERRED]
  backend/app/services/channels/mailru_cloud.py → backend/app/services/channels/base.py
- `S3CompatibleAdapter` --uses--> `AuthError`  [INFERRED]
  backend/app/services/channels/s3_compatible.py → backend/app/services/channels/base.py
- `YandexDiskAdapter` --uses--> `AuthError`  [INFERRED]
  backend/app/services/channels/yandex_disk.py → backend/app/services/channels/base.py

## Import Cycles
- None detected.

## Communities (41 total, 8 thin omitted)

### Community 0 - "v1/vendor.py"
Cohesion: 0.06
Nodes (54): activate_app(), deactivate_app(), get_mysklad_secret_key(), handle_autoprolongation(), handle_install(), handle_resume(), handle_suspend(), handle_tariff_changed() (+46 more)

### Community 1 - "MoyskladClient"
Cohesion: 0.06
Nodes (37): Модуль экспорта прайс-листов из МойСклад. Поддерживает: - Товары, модификации,…, MoyskladAPIError, MoyskladClient, MoyskladForbiddenError, MoyskladRateLimitError, MoyskladUnauthorizedError, Any, Exception (+29 more)

### Community 2 - "package.json"
Cohesion: 0.05
Nodes (36): dependencies, axios, pinia, primevue, vue, vue-router, devDependencies, typescript (+28 more)

### Community 3 - "PriceExportService"
Cohesion: 0.10
Nodes (19): PriceExportService, Any, Получить список организаций., Получить список складов., Получить группы товаров., Загрузить ассортимент (товары, модификации, комплекты). Args: account_id: ID…, Загрузить остатки по всем складам. Returns: Словарь: {product_id: {store_id:…, Сервис экспорта прайс-листов. Собирает данные: - ассортимент (товары,… (+11 more)

### Community 4 - "database.py"
Cohesion: 0.08
Nodes (21): Run migrations in 'offline' mode., Run migrations in 'online' mode., run_migrations_offline(), run_migrations_online(), Config, Settings, get_async_db(), get_db() (+13 more)

### Community 5 - "OrdersExportService"
Cohesion: 0.12
Nodes (20): Модули сервиса экспорта., OrderExportMode, OrderField, OrdersExportService, PositionField, Any, Enum, str (+12 more)

### Community 6 - "crypto.py"
Cohesion: 0.10
Nodes (19): mask_email(), mask_phone(), mask_sensitive_value(), Модуль шифрования секретов. Использует AES-256-GCM для authenticated encryption…, Маскирует email адрес. Пример: user@example.com -> u***@example.com, Маскирует телефон. Пример: +79991234567 -> +7*** *** ** 67, Автоматически определяет тип чувствительных данных и маскирует их. Args: value:…, Тесты для модуля шифрования секретов. (+11 more)

### Community 7 - "RemoteFileMeta"
Cohesion: 0.10
Nodes (16): Метаданные удаленного файла., RemoteFileMeta, BinaryIO, Загрузка файла в Облако Mail.ru., BinaryIO, Создание папки (в S3 это ключ с суффиксом /)., Получение метаданных объекта., Публикация файла. Для S3 требуется настройка bucket policy на стороне… (+8 more)

### Community 8 - "encrypt_secret"
Cohesion: 0.10
Nodes (17): encrypt_secret(), _get_master_key(), Получает мастер-ключ из переменной окружения., Шифрует словарь с секретами. Args: payload: Словарь с данными для шифрования.…, Отсутствие мастер-ключа должно вызывать ошибку., Каждое шифрование должно использовать уникальный nonce., Неверный тип payload должен вызывать TypeError., Неверный тип payload для расшифровки должен вызывать TypeError. (+9 more)

### Community 9 - "GoogleDriveAdapter"
Cohesion: 0.11
Nodes (13): GoogleDriveAdapter, BinaryIO, Проверка подключения к Google Drive., Поиск папки по имени., Адаптер для Google Drive. Использует Drive API v3. OAuth scope:…, Загрузка файла в Google Drive., Получение или создание папки по пути., Поиск файла по имени. (+5 more)

### Community 10 - "StorageError"
Cohesion: 0.18
Nodes (20): AuthError, NotFoundError, PermissionError, Exception, QuotaExceededError, Базовый интерфейс для облачных хранилищ., Элемент списка папки., Базовое исключение для ошибок хранилища. (+12 more)

### Community 11 - "profiles.py"
Cohesion: 0.15
Nodes (24): create_profile(), delete_profile(), get_account_from_context(), get_profile(), list_profiles(), AsyncSession, delete, get (+16 more)

### Community 12 - "MoyskladAccount"
Cohesion: 0.08
Nodes (13): MoyskladAccount, Аккаунт пользователя МойСклад., Обновляет тариф аккаунта., Обновляет дату окончания оплаченного периода., Приостанавливает аккаунт., Помечает аккаунт на удаление через grace-период., Считает количество активных профилей., Проверяет лимит профилей согласно тарифу. Lite: до 3 профилей Professional: без… (+5 more)

### Community 13 - "TestVendorEndpoints"
Cohesion: 0.11
Nodes (14): create_jwt_token(), Тесты эндпоинтов Vendor API., Тест установки приложения (Install)., Тест возобновления приложения (Resume)., Тест смены тарифа (TariffChanged)., Тест автопродления (Autoprolongation)., Тест приостановки (Suspend)., Тест удаления (Uninstall). (+6 more)

### Community 14 - "BaseStorageAdapter"
Cohesion: 0.09
Nodes (13): ABC, BaseStorageAdapter, BinaryIO, Создание папки (идемпотентно). Args: path: Путь к папке. Returns: str: Полный…, Загрузка файла в хранилище. Args: stream: Поток данных файла (streaming для…, Публикация файла (создание публичной ссылки). Args: path: Путь к файлу.…, Список содержимого папки. Args: path: Путь к папке. Returns:…, Удаление файла или папки. Args: path: Путь к ресурсу. Returns: bool: True если… (+5 more)

### Community 15 - "SecretStr"
Cohesion: 0.13
Nodes (11): str, Строковый класс для секретных значений с безопасным выводом. При печати или…, Возвращает замаскированное представление., Возвращает оригинальное значение (использовать с осторожностью!)., SecretStr, Тесты класса SecretStr., str() должен возвращать замаскированное значение., repr() должен возвращать замаскированное значение. (+3 more)

### Community 16 - "test_vendor_api.py"
Cohesion: 0.20
Nodes (16): Модели данных проекта., AccountStatus, CauseType, IntegrationProfile, MoyskladToken, ProcessedJTI, Base, str (+8 more)

### Community 17 - "schemas/__init__.py"
Cohesion: 0.14
Nodes (19): BillingSummary, Config, DictionaryResponse, ExportJobResponse, JobEventResponse, JobStatus, ProfileBase, ProfileCreate (+11 more)

### Community 18 - "YandexDiskAdapter"
Cohesion: 0.17
Nodes (8): BinaryIO, Проверка подключения к Яндекс.Диску., Загрузка файла в Яндекс.Диск., Загрузка через REST API (двухэтапная: получение ссылки -> PUT)., Адаптер для Яндекс.Диска. Поддерживает: - REST API (основной режим):…, Загрузка через WebDAV (PUT)., Установка соединения с Яндекс.Диском., YandexDiskAdapter

### Community 19 - "compilerOptions"
Cohesion: 0.11
Nodes (18): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+10 more)

### Community 20 - "auth.py"
Cohesion: 0.15
Nodes (16): auth_context(), create_mysklad_jwt(), create_session_token(), fetch_user_context(), post, API для авторизации через контекст МойСклад. Этап 4: Авторизация фронтенда…, Создаёт сессионный токен для фронтенда. Хранит: - account_id: accountId из…, Авторизация через contextKey из iframe МойСклад. 1. Получает contextKey из… (+8 more)

### Community 21 - "AccountService"
Cohesion: 0.16
Nodes (10): AccountService, Session, Сервис для управления аккаунтами МойСклад., Тесты сервиса аккаунтов., Создание нового аккаунта., Обновление токена аккаунта., Приостановка аккаунта., Пометка аккаунта на удаление. (+2 more)

### Community 22 - "DictionaryCacheService"
Cohesion: 0.14
Nodes (10): DictionaryCacheService, Any, AsyncSession, Получение из кэша или загрузка через API. :param account_id: ID аккаунта :param…, Инвалидация кэша. :param account_id: ID аккаунта :param dictionary_type: Тип…, Получение списка закэшированных типов справочников для аккаунта. :param…, Очистка устаревших записей кэша. :param batch_size: Размер пакета для удаления…, Сервис для кэширования справочников МойСклад. (+2 more)

### Community 23 - "decrypt_secret"
Cohesion: 0.17
Nodes (10): decrypt_secret(), Расшифровывает зашифрованные данные. Args: payload: Base64-строка с…, Тесты для проверки типов полей, которые должны шифроваться: - токен МойСклад -…, Шифрование токена МойСклад., Шифрование OAuth-токенов Яндекс., Шифрование OAuth-токенов Google., Шифрование пароля приложения Mail.ru., Шифрование SMTP-пароля. (+2 more)

### Community 24 - "factory.py"
Cohesion: 0.17
Nodes (12): str, Типы поддерживаемых облачных хранилищ., StorageType, Any, Фабрика адаптеров облачных хранилищ., Регистрация адаптера для типа хранилища., Создание адаптера для указанного типа хранилища. Args: storage_type: Тип…, Получение списка поддерживаемых типов хранилищ. (+4 more)

### Community 25 - "MailRuCloudAdapter"
Cohesion: 0.13
Nodes (8): MailRuCloudAdapter, Публикация файла (создание публичной ссылки). Облако Mail.ru официально не…, Адаптер для Облака Mail.ru (cloud.mail.ru). Использует WebDAV протокол.…, Установка соединения с Облаком Mail.ru., Проверка подключения к Облаку Mail.ru., Создание папки (идемпотентно)., Список содержимого папки., Удаление файла или папки.

### Community 26 - "mask_token"
Cohesion: 0.25
Nodes (5): mask_token(), Маскирует токен/ключ. Пример: sk-abc123...xyz -> sk-abc123...****, Маскирование длинного токена., Маскирование короткого токена., Маскирование пустого токена.

### Community 27 - "moysklad_api.py"
Cohesion: 0.32
Nodes (7): DictionaryCache, ExportJob, JobEvent, Base, Модели данных для кэша справочников МойСклад JSON API., Кэш справочников МойСклад., Журнал событий заданий.

### Community 28 - "compilerOptions"
Cohesion: 0.25
Nodes (7): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, include

### Community 29 - "client"
Cohesion: 0.29
Nodes (5): client(), db_session(), Создаёт новую сессию БД для каждого теста., Создаёт тестовый клиент FastAPI., fixture

### Community 30 - "get_current_user_context"
Cohesion: 0.33
Nodes (6): get_current_account(), get_current_user_context(), Any, AsyncSession, Зависимость для получения текущего аккаунта из токена. Используется в…, Зависимость для получения контекста текущего пользователя. Возвращает: -…

### Community 31 - "SensitiveFilter"
Cohesion: 0.40
Nodes (4): Фильтр для логов, который маскирует чувствительные данные., Маскирует чувствительные данные в сообщении лога., SensitiveFilter, LogRecord

### Community 32 - ".__init__"
Cohesion: 0.40
Nodes (3): Any, Any, Инициализация адаптера. Args: credentials: { "access_token": str,…

## Knowledge Gaps
- **52 isolated node(s):** `S3Object`, `Config`, `allowImportingTsExtensions`, `isolatedModules`, `jsx` (+47 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 378 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MoyskladClient` connect `MoyskladClient` to `PriceExportService`, `DictionaryCacheService`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Why does `AccountService` connect `AccountService` to `v1/vendor.py`, `.create_profile`, `.get_profiles`, `MoyskladAccount`, `TestVendorEndpoints`, `test_vendor_api.py`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `MoyskladAccount` connect `MoyskladAccount` to `v1/vendor.py`, `.create_profile`, `.get_profiles`, `profiles.py`, `test_vendor_api.py`, `auth.py`, `AccountService`, `get_current_user_context`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `AccountService` (e.g. with `activate_app()` and `deactivate_app()`) actually correct?**
  _`AccountService` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `MoyskladAccount` (e.g. with `auth_context()` and `get_current_account()`) actually correct?**
  _`MoyskladAccount` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `StorageError` (e.g. with `GoogleDriveAdapter` and `MailRuCloudAdapter`) actually correct?**
  _`StorageError` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `S3Object`, `Config`, `allowImportingTsExtensions` to the rest of the system?**
  _52 weakly-connected nodes found - possible documentation gaps or missing edges._