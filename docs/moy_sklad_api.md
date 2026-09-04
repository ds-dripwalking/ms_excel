# МойСклад JSON API 1.2 — справочник по сущностям для MVP «Комбайн»

> Только работа с API: эндпоинты, поля, фильтры, ограничения, оптимизация.
> Базовый URL: `https://api.moysklad.ru/api/remap/1.2`
> Аутентификация: OAuth 2.0, Bearer token (per-client, хранится зашифрованным).

---

## Содержание

1. Общие принципы
2. Права доступа (scope)
3. Модуль «Заказы покупателей»
4. Модуль «Прайс-лист»
5. Справочники и метаданные (кэширование)
6. Дополнительные поля (attributes)
7. Ограничения и обработка ошибок
8. Оптимизация запросов
9. Схема сборки данных
10. Чек-лист перед разработкой
11. Итоговая карта эндпоинтов

---

## 1. Общие принципы

| Механизм | Описание |
|---|---|
| Пагинация | `offset` + `limit` (макс. 1000 записей на страницу); большие выборки — циклом по чанкам |
| Rate limits | ~100 запросов / 30 сек на токен (≈3–5 rps); воркеры с throttling и очередью |
| `expand=` | подгрузка связанных объектов в одном запросе (избегание N+1); поддерживает вложенные коллекции, напр. `positions.assortment` |
| `filter=` | фильтрация на сервере: сравнения (`>`, `<`, `>=`, `<=`, `=`), несколько условий через `;` |
| `fields=` | выборка только нужных полей (ускорение; усложняет поддержку — использовать точечно) |
| `search=` | текстовый поиск (для UI-подсказок, не для выгрузок) |

---

## 2. Права доступа (scope)

Только просмотр (конкурентное преимущество против админ-прав Склад24):

- Валюты — просмотр
- Склады — просмотр
- Товары и услуги — просмотр
- Юр. лица — просмотр
- Контрагенты — просмотр
- Заказы покупателей — просмотр
- Опционально: просмотр себестоимости, цен закупок и прибыли (для расширенных полей)

---

## 3. Модуль «Заказы покупателей»

### 3.1 Эндпоинты

| Эндпоинт | Назначение |
|---|---|
| `GET /entity/customerorder` | список заказов (пагинация + фильтры + expand) |
| `GET /entity/customerorder/{id}` | один заказ |
| `GET /entity/customerorder/{id}/positions` | позиции заказа (если не использован expand) |
| `GET /entity/customerorder/metadata` | метаданные: статусы (states), доп. поля, справочная структура |

### 3.2 Поля шапки (используем в конструкторе)

```
uuid, name (номер), moment (дата), created, updated
status, organization, store, agent (контрагент/покупатель)
sum, payedSum, shippedSum, discount, vatEnabled, vatIncluded, vatSum
currency, manager, project, contract, group
deliveryPlannedMoment, deliveryAddress
description (комментарий), attributes (доп. поля)
meta.href (ссылка в МойСклад)
```

### 3.3 Поля позиций

```
assortment (товар/услуга — через expand)
quantity, price, discount, vat, vatValue, reserve, shipped
```

### 3.4 Фильтры (P0)

- период: `moment>=…;moment<=…` (пресеты: сегодня/вчера/неделя/месяц/диапазон)
- статусы: по id статусов из metadata (один или несколько)
- организация / склад: по id ссылочных полей (синтаксис — см. документацию filter)
- сумма: `sum>=…;sum<=…`

### 3.5 Expand

```
GET /entity/customerorder?expand=organization,store,agent,positions.assortment&limit=1000
```

Один запрос возвращает до 1000 заказов вместе с позициями и ссылочными объектами.

---

## 4. Модуль «Прайс-лист»

### 4.1 Эндпоинты

| Эндпоинт | Назначение |
|---|---|
| `GET /entity/assortment` | универсальная лента: товары + услуги (+ в P1: модификации, комплекты) |
| `GET /entity/product` | только товары |
| `GET /entity/product/{id}/images` | изображения товара |
| `GET /report/stock/all` | остатки по всем складам одним запросом |
| `GET /context/companysettings/pricetype` | справочник типов цен |
| `GET /entity/variant` (P1) | модификации |
| `GET /entity/bundle` (P1) | комплекты |

### 4.2 Поля товара

```
uuid, name, code, article, barcodes, externalCode
productFolder / pathName (группа/категория — expand)
unit, weight, volume, description
archived (фильтр archived=false)
attributes (доп. поля)
salePrices[]: { value, currency, priceType }  ← каждый тип цены → своя колонка
minPrice, buyPrice (если выдано доп. право)
```

### 4.3 Остатки

```
GET /report/stock/all
→ rows[]: { assortment (meta), store, quantity, reserve, inTransit, available }
```

Стратегия: один запрос на весь каталог → join на нашей стороне по `assortment.id` с уже загруженным ассортиментом (либо `expand=assortment`, если каталог небольшой).

### 4.4 Изображения

```
GET /entity/product/{id}/images
→ { filename, size, miniature, tiny }
```

`miniature`/`tiny` — постоянные публичные ссылки: выгружаем как есть (конкуренты делают так же). Ленивая загрузка: запрашиваем только если поле «изображения» включено в профиле.

### 4.5 Фильтры (P0)

- `archived=false`
- группа: по id `productFolder`
- «остаток > 0», цена мин/макс — на нашей стороне после join с остатками/ценами (API по ним не фильтрует в ленте ассортимента)
- склады и типы цен — выбор в профиле, обработка на нашей стороне

---

## 5. Справочники и метаданные (кэширование)

| Эндпоинт | Назначение | Кэш |
|---|---|---|
| `GET /entity/organization` | организации | да, TTL ~1 ч |
| `GET /entity/store` | склады | да |
| `GET /entity/currency` | валюты | да |
| `GET /entity/productfolder` | дерево групп товаров | да |
| `GET /entity/customerorder/metadata` | статусы заказов + доп. поля заказов | да |
| `GET /entity/product/metadata` | доп. поля товаров | да |
| `GET /context/companysettings/pricetype` | типы цен | да |
| `GET /entity/counterparty` | контрагенты | нет (большие объемы; только по необходимости) |
| `GET /entity/customentity/{id}` | значения пользовательских справочников (доп. поля типа «справочник») | да, короткий TTL |

Загрузка справочников — при первом запуске профиля и по TTL; в UI фильтров отдаем из кэша.

---

## 6. Дополнительные поля (attributes)

- Приходят внутри сущностей: `attributes: [{ name, value, type }]`.
- Типы значений: `string`, `long`, `double`, `boolean`, `time`, `text`, `link`, `file`, `customentity` — конструктор UI и генераторы форматов должны обрабатывать все.
- Метаданные доп. полей — из `/entity/*/metadata` (для построения чекбоксов в конструкторе).
- Значения справочников-типов — `GET /entity/customentity/{metaId}`.
- Фильтрация по доп. полям (P1) — через `filter=` с meta-id поля (синтаксис — см. документацию).

---

## 7. Ограничения и обработка ошибок

| Ситуация | Обработка |
|---|---|
| `429` Too Many Requests | backoff + retry, throttling воркеров (очередь Redis) |
| `401` Unauthorized | refresh токена, повтор запроса; при неудаче — просьба переустановить приложение |
| `403` Forbidden | нет прав — понятное сообщение в UI (какое право нужно) |
| `5xx` | retry с экспоненциальной задержкой, алерт в журнал |
| Большие выборки | чанки по 1000, ограничение конкурентности воркеров per-client |

---

## 8. Оптимизация запросов

**Заказы (типовая выгрузка за период):**
```
GET /entity/customerorder
  ?filter=moment>=2026-01-01;moment<=2026-01-31
  &expand=organization,store,agent,positions.assortment
  &limit=1000&offset=N
```

**Прайс-лист:**
```
GET /entity/assortment?filter=archived=false&expand=productFolder&limit=1000   (циклом)
GET /report/stock/all                                                          (один запрос)
join по assortment.id на нашей стороне
```

**Правило:** expand — для связей «1→1» и вложенных коллекций заказа; справочники — отдельно и в кэш; изображения — лениво.

---

## 9. Схема сборки данных

```
Scheduler → Queue (Redis) → Worker
  ├─ МойСклад API: справочники (кэш) → сущности (чанки, expand) → остатки/изображения
  ├─ Трансформация: конструктор полей, фильтры, режимы строк
  ├─ Формат: XLSX / CSV / JSON / YML
  ├─ Доставка: Яндекс.Диск / Mail.ru / Google Drive / ссылка / Email
  └─ Журнал + уведомления
```

---

## 10. Чек-лист перед разработкой

- [ ] Тестовый аккаунт МойСклад с демо-данными (заказы, товары, остатки, типы цен, доп. поля, изображения)
- [ ] OAuth flow: redirect URI, обмен кода, refresh
- [ ] Реальные rate limits и поведение `429` на выборках 10k+
- [ ] `expand=positions.assortment` на заказах с большим числом позиций
- [ ] `/report/stock/all` на каталоге 50k+ SKU (время ответа, память воркера)
- [ ] Публичность ссылок `miniature`/`tiny` изображений
- [ ] Синтаксис filter по ссылочным полям и доп. полям
- [ ] Состав `attributes` и все типы значений на демо-данных

---

## 11. Итоговая карта эндпоинтов

| Модуль | Эндпоинты | Запросов на 1000 записей |
|---|---|---|
| Заказы | `/entity/customerorder` (+ expand) | 1–2 |
| Прайс | `/entity/assortment` + `/report/stock/all` | 2–3 |
| Изображения | `/entity/product/{id}/images` | N (лениво, только при включенном поле) |
| Справочники | organization, store, currency, productfolder, pricetype, metadata | ~6 (кэш) |
| P1 | `/entity/variant`, `/entity/bundle`, filter по доп. полям | — |

**Итог:** типовая выгрузка = 5–10 запросов к API — comfortably в пределах rate limits даже при расписании «каждые N часов».