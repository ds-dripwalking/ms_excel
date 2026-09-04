# МойСклад Vendor API 1.0 — Спецификация для MVP «Комбайн»

Документ суммирует требования и технические детали интеграции с маркетплейсом МойСклад для приложения выгрузки заказов и прайс-листов.

**Источник**: https://dev.moysklad.ru/doc/api/vendor/1.0/

---

## 1. Тип решения и основные характеристики

### 1.1 Тип решения
- **Серверное решение** — основной тип для нашего MVP
- Использует JSON API 1.2 для доступа к данным
- Может быть платным (обязательно для серверных решений)
- Поддерживает активацию/деактивацию через Vendor API

### 1.2 Идентификаторы решения
После создания черновика получаем:
- **appId** (UUID) — идентификатор решения в каталоге
- **appUid** (String) — глобальный идентификатор для JWT
- **secretKey** — секретный ключ для подписи JWT (HS256)

### 1.3 Права доступа (scope)
Используем уровень **custom** (не admin) для конкурентного преимущества "только просмотр":

**Обязательные права для MVP:**
- `customerorder`: view (заказы покупателей)
- `product`: view (товары)
- `variant`: view (модификации, P1)
- `bundle`: view (комплекты, P1)
- `store`: view (склады)
- `organization`: view (организации)
- `counterparty`: view (контрагенты)
- `currency`: view (валюты)
- `productfolder`: view (группы товаров)
- `stock`: view (остатки)
- `customAttributes`: view (доп. поля)

**Дополнительно (для расширенных полей):**
- `pnl`: view (себестоимость, прибыль)
- `company_crm`: view

**Права на вебхуки (P2 для realtime):**
- `useOwnWebhooks` — создание/управление своими вебхуками

---

## 2. Аутентификация Vendor API (JWT)

### 2.1 Механизм
Все запросы подписываются JWT-токенами (RFC 7519):
- Алгоритм: **HS256** (HMAC SHA-256)
- Секретный ключ: `secretKey` из ЛК разработчика

### 2.2 Исходящие запросы (МойСклад → Мы)
МойСклад подписывает запросы к нашим эндпоинтам:

**JWT Header:**
```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

**JWT Payload:**
```json
{
  "iat": 1516239022,      // Время генерации (NumericDate)
  "exp": 1516239322,      // Время истечения
  "jti": "6S3BQLsaSRNdEnhPCoW9lplY2LozRUOq"  // Уникальный ID (одноразовость)
}
```

**Обработка на нашей стороне:**
- Проверять `exp` — отклонять просроченные токены
- Проверять `jti` — отклонять повторно использованные токены
- Заголовок: `Authorization: Bearer <token>`

### 2.3 Входящие запросы (Мы → МойСклад)
Мы подписываем запросы к МойСклад:

**JWT Payload (обязательные поля):**
```json
{
  "sub": "appUid",        // appUid решения
  "iat": 1516239022,      // Время генерации
  "exp": 1516239322,      // Опционально
  "jti": "unique-id"      // Уникальный ID токена
}
```

**Ограничения МойСклад:**
1. JWT одноразовый — `jti` проверяется на уникальность
2. Максимальное время жизни: **300 секунд** (5 минут)
   - Если `exp` отсутствует или `(exp - iat) > 300`, используется `iat + 300`

---

## 3. Жизненный цикл решения

### 3.1 Статусы решения
- **Draft** — черновик (разработка/тестирование)
- **Ready** — готово к модерации
- **Published** — опубликовано в каталоге
- **Hidden** — снято с публикации
- **Merged** — версия опубликована (внутренний)

### 3.2 Статусы установки на аккаунте
- **Activated** — решение активно
- **Activating** — асинхронная активация (если >10 сек)
- **SettingsRequired** — требуется настройка пользователем
- **ActivationFailed** — ошибка установки
- **DeactivationFailed** — ошибка удаления

---

## 4. Процесс активации решения

### 4.1 Эндпоинт на нашей стороне
```
PUT https://{endpointBase}/api/moysklad/vendor/1.0/apps/{appId}/{accountId}
```

**Параметры URL:**
- `endpointBase` — наш базовый URL из дескриптора
- `appId` — UUID решения
- `accountId` — UUID аккаунта МойСклад

### 4.2 Тело запроса от МойСклад
```json
{
  "appUid": "string",
  "accountName": "string",
  "cause": "Install | Resume | TariffChanged | Autoprolongation",
  "access": [
    {
      "scope": "customerorder",
      "token": "bearer-token-for-json-api"
    }
  ],
  "subscription": {
    "tariffId": "uuid",
    "tariffName": "Professional",
    "isTrial": true,
    "trialEndDate": "2026-09-17T00:00:00Z",
    "paidEndDate": "2026-10-03T00:00:00Z"
  }
}
```

**Причины активации (`cause`):**
- `Install` — первая установка
- `Resume` — возобновление после приостановки
- `TariffChanged` — смена тарифа
- `Autoprolongation` — автопродление подписки

### 4.3 Тело ответа (наш ответ)
```json
{
  "status": "Activated | Activating | SettingsRequired"
}
```

**Статусы:**
- **Activated** — решение готово к работе
- **Activating** — асинхронная активация (если занимает >10 сек)
  - Затем вызываем эндпоинт МойСклад для изменения статуса
- **SettingsRequired** — требуется настройка в главном окне

### 4.4 Обработка ошибок
- **200 OK** — успешная обработка
- **4xx** — ошибка, переход в `ActivationFailed`
- **551** — кастомная ошибка, `ActivationFailed`
- **5xx** (кроме 551) — запускается Retry
- **Таймаут 10 сек** — запускается Retry

---

## 5. Процесс деактивации решения

### 5.1 Эндпоинт на нашей стороне
```
DELETE https://{endpointBase}/api/moysklad/vendor/1.0/apps/{appId}/{accountId}
```

### 5.2 Тело запроса
```json
{
  "cause": "Uninstall | Suspend"
}
```

**Причины деактивации:**
- `Uninstall` — удаление решения пользователем
- `Suspend` — приостановка из-за неоплаты (только платные решения)

### 5.3 Критически важно: разница между Suspend и Uninstall

**Suspend (приостановка):**
- Временная остановка
- **Сохраняем все настройки и конфигурацию**
- При `Resume` возвращаем `Activated` без повторной настройки
- Токен JSON API аннулируется

**Uninstall (удаление):**
- Полное удаление (но может быть временным для переустановки)
- Рекомендуется сохранить настройки на grace-период
- Токен JSON API аннулируется

### 5.4 Тело ответа
**Пустое** (только HTTP-статус)

### 5.5 Обработка ошибок
- **200 OK** — успешно деактивировано
- **204 No Content** — никогда не было активировано
- **4xx** — ошибка, переход в `DeactivationFailed`
- **551** — кастомная ошибка, `DeactivationFailed`
- **5xx** (кроме 551) — запускается Retry
- **Таймаут 10 сек** — запускается Retry

---

## 6. Приостановка и возобновление

### 6.1 Приостановка (Suspend)
**Триггеры:**
- Закончилась подписка
- Недостаточно средств на балансе
- Пользователь отключил автопродление

**Действия на нашей стороне:**
1. Остановить все задачи планировщика
2. **Сохранить настройки профилей экспорта**
3. Сохранить маппинг полей и фильтры
4. Очистить токены облачных дисков после grace-периода
5. НЕ удалять историю выполнений

### 6.2 Возобновление (Resume)
**Триггеры:**
- Пополнение баланса
- Оплата подписки
- Включение автопродления

**Действия на нашей стороне:**
1. Получить новый токен JSON API
2. Восстановить настройки из БД
3. Проверить актуальность токенов облачных дисков
4. Вернуть статус `Activated`
5. Возобновить работу планировщика

**Важно:** Возвращаем `SettingsRequired` только если:
- Настройки отсутствуют
- Настройки устарели
- Требуется действие пользователя (например, переподключение диска)

---

## 7. Retry механизм МойСклад

### 7.1 Когда срабатывает
- Таймаут ответа (>10 сек)
- HTTP 5xx (кроме 551)
- Сетевые ошибки

### 7.2 Параметры Retry

| Операция | Длительность | Периодичность |
|----------|--------------|---------------|
| Активация (Install, Resume) | 3 минуты | 10 сек |
| Деактивация (Uninstall, Suspend) | 3 минуты | 10 сек |
| Активация (TariffChanged, Autoprolongation) | 24 часа | 5 минут |
| Дополнительные события | 24 часа | 5 минут |

### 7.3 Идентификация повторов
Заголовок `X_Lognex_RequestId` — одинаковый для всех попыток одного запроса.

**Обработка на нашей стороне:**
- Идемпотентность операций
- Проверка `jti` в JWT
- Логирование с `X_Lognex_RequestId`

---

## 8. REST-эндпоинты на стороне МойСклад

**Базовый URL:** `https://apps-api.moysklad.ru/api/vendor/1.0`

**Обязательный заголовок:** `Accept-Encoding: gzip`

### 8.1 Получение статуса решения
```
GET /apps/{appId}/{accountId}/status
```

**Ответ:**
```json
{
  "status": "Activated",
  "cause": "Install",
  "subscription": {
    "tariffId": "uuid",
    "isTrial": false
  },
  "access": [...]
}
```

### 8.2 Изменение статуса решения
```
PUT /apps/{appId}/{accountId}/status
```

**Тело запроса:**
```json
{
  "status": "Activated | Activating | SettingsRequired"
}
```

**Использование:**
- После асинхронной активации (статус `Activating`)
- После завершения настройки пользователем (статус `SettingsRequired`)

### 8.3 Получение контекста пользователя
```
POST /context/{contextKey}
```

**Использование:**
- Получение информации о текущем пользователе в UI
- Проверка прав администратора
- `contextKey` передается в GET-параметрах при загрузке iframe

---

## 9. Дескриптор решения (XML)

### 9.1 Обязательные блоки

```xml
<app>
  <name>Комбайн</name>
  <alias>kombain-export</alias>

  <vendorApi>
    <endpointBase>https://kombain.example.com</endpointBase>
  </vendorApi>

  <access>
    <custom>
      <customerorder>
        <view>ALL</view>
      </customerorder>
      <product>
        <view>ALL</view>
      </product>
      <store>
        <view>ALL</view>
      </store>
      <organization>
        <view>ALL</view>
      </organization>
      <counterparty>
        <view>ALL</view>
      </counterparty>
      <currency>
        <view>ALL</view>
      </currency>
      <productfolder>
        <view>ALL</view>
      </productfolder>
      <stock>
        <view>ALL</view>
      </stock>
      <customAttributes>
        <view>ALL</view>
      </customAttributes>
      <webhook>
        <view>ALL</view>
        <create>OWN</create>
        <update>OWN</update>
        <delete>OWN</delete>
      </webhook>
    </custom>
  </access>

  <iframes>
    <iframe>
      <name>main</name>
      <sourceUrl>https://kombain.example.com/ui/main</sourceUrl>
      <title>Настройки выгрузки</title>
    </iframe>
  </iframes>
</app>
```

### 9.2 Опциональные блоки (P1+)

**Виджеты (P2):**
```xml
<widgets>
  <widget>
    <name>export-button</name>
    <sourceUrl>https://kombain.example.com/ui/widget</sourceUrl>
    <extensionPoint>customerorder</extensionPoint>
  </widget>
</widgets>
```

**Кастомные кнопки (P2):**
```xml
<buttons>
  <button>
    <name>export-now</name>
    <endpoint>https://kombain.example.com/api/button</endpoint>
    <extensionPoint>customerorder</extensionPoint>
  </button>
</buttons>
```

---

## 10. Биллинг и тарифы

### 10.1 Модель оплаты
- Все платежи через биллинг МойСклад
- Вознаграждение разработчика: **75%** от полученной суммы
- НДС 22% вычитается перед расчетом вознаграждения

**Пример расчета:**
- Цена тарифа: 990 ₽/мес (с НДС)
- НДС: 990 - (990 / 1.22) = 180,33 ₽
- Сумма без НДС: 809,67 ₽
- Вознаграждение: 809,67 × 0.75 = **607,25 ₽**

### 10.2 Наши тарифы

**Lite — 590 ₽/мес:**
- Один модуль (Заказы ИЛИ Прайс-лист)
- До 3 профилей экспорта
- Форматы: XLSX, CSV, JSON, YML
- Каналы: Яндекс.Диск, Mail.ru, Google Drive, ссылка, Email
- Telegram: уведомления об ошибках
- Триал: 14 дней (на Pro)

**Professional — 990 ₽/мес:**
- Оба модуля
- Без ограничений на профили
- Все форматы + XML (P1)
- Все каналы + Google Таблицы, FTP, Webhook (P1)
- Telegram + MAX: файлы, кнопки, команды
- Модификации и комплекты
- Триал: 14 дней

### 10.3 Пробный период
- **14 дней** (максимум по документации)
- Только на одном тарифе (выбираем Pro)
- Начинается с момента первой установки
- Пользователь может удалять/устанавливать многократно
- Продление: 1 раз через ЛК разработчика

### 10.4 Годовая подписка
- Скидка 20% для клиента
- Наш доход: (Цена × 12 - 20%) - 25%
- Снижает churn, дает предоплату

### 10.5 Партнерская программа
- Партнеры МойСклад: скидка 30%
- Наш доход: (Цена - 30%) - 25%

---

## 11. Главное окно (iframe)

### 11.1 Назначение
- Настройка профилей экспорта
- Конструктор полей
- Подключение облачных дисков
- Журнал выполнений
- Управление подпиской

### 11.2 Требования к UI
- Автоматическое масштабирование по высоте (без вертикального скролла)
- Визуальный стиль МойСклад (рекомендуется)
- Адаптивный дизайн

### 11.3 Получение контекста пользователя
```javascript
// При загрузке iframe получаем contextKey из GET-параметров
const contextKey = new URLSearchParams(window.location.search).get('contextKey');

// Запрашиваем контекст
const response = await fetch(`https://apps-api.moysklad.ru/api/vendor/1.0/context/${contextKey}`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${jwtToken}`,
    'Accept-Encoding': 'gzip'
  }
});

const context = await response.json();
// context содержит информацию о пользователе и его правах
```

---

## 12. Работа с токенами JSON API

### 12.1 Получение токена
Токен передается в запросе активации:
```json
{
  "access": [
    {
      "scope": "customerorder",
      "token": "bearer-token-12345"
    }
  ]
}
```

### 12.2 Использование токена
```
Authorization: Bearer <access_token>
```

### 12.3 Время жизни
- **Не ограничено** (пока решение активно)
- Аннулируется при:
  - Деактивации (Uninstall)
  - Приостановке (Suspend)
  - Удалении решения

### 12.4 Хранение токенов
- **Шифрование at rest** (AES-256-GCM)
- Ключ шифрования вне БД (env/KMS)
- Маскирование в логах

### 12.5 Обработка ошибок токена
- **401 Unauthorized** — токен недействителен
  - Проверить статус решения через Vendor API
  - Если решение приостановлено — ожидать Resume
  - Если удалено — очистить данные после grace-периода

---

## 13. Требования к модерации

### 13.1 Обязательные требования
1. **Полезность** — решение должно решать реальную задачу
2. **Доступ через токен** — только JSON API 1.2, никаких логин/паролей
3. **Настройка в UI МойСклад** — все настройки в главном окне (iframe)
4. **Бесперебойная работа** — стабильность установки/удаления

### 13.2 Требования к иконке
- Размер: минимум 300×300 px
- Формат: SVG (рекомендуется), PNG, JPEG
- Отчетливая крупная форма на цветном фоне
- Без скриншотов и логотипа МойСклад
- Минимум текста

### 13.3 Что НЕ пройдет модерацию
- Форма сбора лидов без функциональности
- Настройка только во внешнем сервисе
- Запрос логин/пароля вместо токена
- Нестабильная работа при установке/удалении

---

## 14. Чек-лист перед разработкой

### 14.1 Подготовка
- [ ] Зарегистрировать ИП/ООО с ОКВЭД 62.01
- [ ] Открыть расчетный счет в рублях
- [ ] Получить доступ к ЛК разработчика (анкета на apps@moysklad.ru)
- [ ] Создать тестовый аккаунт МойСклад с демо-данными

### 14.2 Создание черновика
- [ ] Создать черновик в ЛК разработчика
- [ ] Получить appId, appUid, secretKey
- [ ] Сгенерировать дескриптор (XML)
- [ ] Указать endpointBase (HTTPS)

### 14.3 Реализация Vendor API
- [ ] JWT-аутентификация (HS256)
- [ ] Эндпоинт активации (PUT)
- [ ] Эндпоинт деактивации (DELETE)
- [ ] Обработка Suspend vs Uninstall
- [ ] Retry-защита (идемпотентность, jti)
- [ ] Таймаут 10 сек

### 14.4 Интеграция с JSON API
- [ ] Хранение токенов (шифрование)
- [ ] Обработка 401 (токен недействителен)
- [ ] Пагинация и rate limits
- [ ] Expand для связанных объектов

### 14.5 Главное окно
- [ ] iframe с настройками
- [ ] Получение контекста пользователя
- [ ] Конструктор полей
- [ ] Подключение облачных дисков

### 14.6 Биллинг
- [ ] Настройка тарифов (Lite 590₽, Pro 990₽)
- [ ] Триал 14 дней на Pro
- [ ] Обработка TariffChanged
- [ ] Обработка Autoprolongation

### 14.7 Тестирование
- [ ] Установка на аккаунт разработчика (24 часа)
- [ ] Приостановка/возобновление
- [ ] Удаление и повторная установка
- [ ] Смена тарифа
- [ ] Все причины активации/деактивации

### 14.8 Модерация
- [ ] Подготовить иконку (300×300 px, SVG)
- [ ] Написать инструкцию (HTML + скриншоты)
- [ ] Заполнить описание тарифов
- [ ] Отправить на модерацию
- [ ] Комментарий для модератора с тестовыми данными

---

## 15. Архитектурные решения для MVP

### 15.1 Обработка жизненного цикла

```python
class MoySkladLifecycleHandler:
    def handle_activation(self, request):
        cause = request.data['cause']
        access_token = request.data['access'][0]['token']
        subscription = request.data['subscription']

        if cause == 'Install':
            # Первая установка
            self.create_account(request.account_id, access_token, subscription)
            return {'status': 'SettingsRequired'}  # Требуется настройка

        elif cause == 'Resume':
            # Возобновление после приостановки
            self.update_token(request.account_id, access_token)
            self.resume_scheduler(request.account_id)
            return {'status': 'Activated'}

        elif cause in ['TariffChanged', 'Autoprolongation']:
            # Смена тарифа или автопродление
            self.update_subscription(request.account_id, subscription)
            return {'status': 'Activated'}

    def handle_deactivation(self, request):
        cause = request.data['cause']

        if cause == 'Suspend':
            # Приостановка - сохраняем настройки
            self.stop_scheduler(request.account_id)
            self.mark_suspended(request.account_id)
            # НЕ удаляем настройки и токены дисков

        elif cause == 'Uninstall':
            # Удаление - помечаем для очистки
            self.stop_scheduler(request.account_id)
            self.mark_for_deletion(request.account_id, grace_period_days=30)
```

### 15.2 База данных (схема)

```sql
-- Аккаунты МойСклад
CREATE TABLE accounts (
    id UUID PRIMARY KEY,
    account_name VARCHAR(255),
    app_uid VARCHAR(255),
    access_token TEXT ENCRYPTED,  -- Токен JSON API
    subscription_tier VARCHAR(50), -- 'lite' | 'professional'
    is_trial BOOLEAN,
    trial_end_date TIMESTAMP,
    paid_end_date TIMESTAMP,
    status VARCHAR(50), -- 'activated' | 'suspended' | 'deleted'
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Профили экспорта
CREATE TABLE export_profiles (
    id UUID PRIMARY KEY,
    account_id UUID REFERENCES accounts(id),
    name VARCHAR(255),
    module VARCHAR(50), -- 'orders' | 'pricelist'
    fields_config JSONB, -- Конструктор полей
    filters JSONB,
    format VARCHAR(10), -- 'xlsx' | 'csv' | 'json' | 'yml'
    channel_config JSONB, -- Настройки канала доставки
    schedule_config JSONB, -- Расписание
    is_active BOOLEAN,
    created_at TIMESTAMP
);

-- Токены облачных дисков
CREATE TABLE cloud_tokens (
    id UUID PRIMARY KEY,
    account_id UUID REFERENCES accounts(id),
    provider VARCHAR(50), -- 'yandex' | 'mailru' | 'google'
    access_token TEXT ENCRYPTED,
    refresh_token TEXT ENCRYPTED,
    expires_at TIMESTAMP,
    created_at TIMESTAMP
);

-- История выполнений
CREATE TABLE export_jobs (
    id UUID PRIMARY KEY,
    profile_id UUID REFERENCES export_profiles(id),
    status VARCHAR(50), -- 'success' | 'error' | 'running'
    rows_count INTEGER,
    file_size INTEGER,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

### 15.3 Обработка вебхуков (P2)

```python
# При активации создаем вебхуки для realtime-синхронизации
def setup_webhooks(account_id, access_token):
    webhooks = [
        {
            'url': f'{WEBHOOK_BASE_URL}/moysklad/orders',
            'action': 'POST',
            'entityType': 'customerorder',
            'eventTypes': ['create', 'update', 'delete']
        },
        {
            'url': f'{WEBHOOK_BASE_URL}/moysklad/products',
            'action': 'POST',
            'entityType': 'product',
            'eventTypes': ['update']
        }
    ]

    for webhook in webhooks:
        requests.post(
            'https://api.moysklad.ru/api/remap/1.2/entity/webhook',
            headers={'Authorization': f'Bearer {access_token}'},
            json=webhook
        )
```

---

## 16. Go-to-market через маркетплейс

### 16.1 Страница в каталоге
**Заголовок:**
«Комбайн — выгрузка заказов и прайс-листов в Excel, CSV, JSON, YML»

**Подзаголовок:**
«Одно приложение вместо двух. Яндекс.Диск, Облако Mail.ru, Google Drive. Права — только просмотр»

**Ключевые преимущества:**
- ✅ 2-в-1: заказы + прайс-листы в одной подписке
- ✅ Российские облака: Яндекс.Диск, Облако Mail.ru
- ✅ Права только просмотр (безопасность данных)
- ✅ 14 дней бесплатно на полном тарифе
- ✅ От 590 ₽/мес (дешевле конкурентов)

### 16.2 Сегменты клиентов
1. **E-commerce/маркетплейсы** — YML + Яндекс.Диск для Яндекс.Маркета
2. **Бухгалтерия/отчетность** — заказы в XLSX для анализа
3. **Интеграции с сайтом** — CSV/JSON для импорта
4. **Корпоративный сектор** — MAX + российские облака (152-ФЗ)

### 16.3 Метрики успеха
- Первый успешный экспорт в первые 24 часа триала
- Конверсия триал → paid: цель >30%
- Churn M1: <10%, M3: <20%
- Доля Pro в платящих: >40%

---

## 17. Риски и митигации

### 17.1 Технические риски

| Риск | Митигация |
|------|-----------|
| Токен JSON API аннулирован | Проверка статуса через Vendor API, уведомление пользователя |
| Таймаут активации (>10 сек) | Асинхронная активация, статус `Activating` |
| Retry от МойСклад | Идемпотентность, проверка `jti`, логирование `X_Lognex_RequestId` |
| Suspend без предупреждения | Сохранение настроек, grace-период для токенов дисков |

### 17.2 Бизнес-риски

| Риск | Митигация |
|------|-----------|
| Отказ в модерации | Следование требованиям, тестирование на аккаунте разработчика |
| Демпинг конкурентов | УТП: российские облака, 2-в-1, MAX |
| Низкая конверсия триала | Онбординг: первый экспорт за 24 часа, кнопка «Тест» |
| Churn после триала | Годовая подписка со скидкой, апсейл Lite→Pro |

---

## 18. Порядок работ

### Фаза 1: Подготовка (1 неделя)
1. Регистрация ИП/ООО
2. Получение доступа к ЛК разработчика
3. Создание тестового аккаунта МойСклад
4. Проектирование БД и API

### Фаза 2: Vendor API (1 неделя)
1. JWT-аутентификация
2. Эндпоинты активации/деактивации
3. Обработка жизненного цикла
4. Retry-защита

### Фаза 3: JSON API интеграция (2 недели)
1. Модуль «Заказы покупателей»
2. Модуль «Прайс-лист»
3. Конструктор полей и фильтры
4. Генераторы форматов (XLSX, CSV, JSON, YML)

### Фаза 4: Каналы доставки (2 недели)
1. Яндекс.Диск (OAuth + REST)
2. Облако Mail.ru (WebDAV)
3. Google Drive (OAuth)
4. Файл-ссылка и Email

### Фаза 5: UI и биллинг (1 неделя)
1. Главное окно (iframe)
2. Настройка тарифов
3. Триал 14 дней
4. Журнал выполнений

### Фаза 6: Тестирование и модерация (1 неделя)
1. Тестирование на аккаунте разработчика
2. Исправление багов
3. Подготовка документации
4. Отправка на модерацию

**Итого: 8 недель до запуска**

---

## 19. Полезные ссылки

- **Документация Vendor API**: https://dev.moysklad.ru/doc/api/vendor/1.0/
- **JSON API 1.2**: https://dev.moysklad.ru/doc/api/remap/1.2/
- **ЛК разработчика**: https://dev.moysklad.ru/
- **Демо-решения**: GitHub репозитории (Node.js, PHP, Python)
- **Поддержка**: apps@moysklad.ru

---

## 20. Ключевые выводы для MVP

1. **Тип решения**: Серверное с правами `custom` (только просмотр)
2. **Аутентификация**: JWT (HS256) с `secretKey`
3. **Жизненный цикл**: Активация (PUT) → Активен → Деактивация (DELETE)
4. **Критично**: Разная обработка `Suspend` (сохранить) и `Uninstall` (удалить)
5. **Токены JSON API**: Хранить зашифрованными, аннулируются при деактивации
6. **Биллинг**: 75% от суммы без НДС, триал 14 дней
7. **UI**: iframe в МойСклад, автоматическое масштабирование
8. **Retry**: Идемпотентность, проверка `jti`, логирование `X_Lognex_RequestId`
9. **Модерация**: Полезность, настройка в UI, стабильность
10. **Go-to-market**: УТП — российские облака, 2-в-1, цена ниже конкурентов

**Следующий шаг**: Создание черновика решения в ЛК разработчика и генерация дескриптора.