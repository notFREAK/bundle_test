# Спецификация web-сервиса OPC UA -> REST Gateway (v1, draft)

## 1. Назначение
Сервис выступает шлюзом между mini OPC UA сервером (`Objects/DeviceMetrics`) и внешними клиентами (web/mobile/другие сервисы), предоставляя REST API и JWT-аутентификацию.

## 2. Основные функции
- Подключение к OPC UA серверу и периодическое чтение метрик.
- Кэширование последнего снапшота метрик в памяти.
- (Опционально) сохранение метрик в PostgreSQL в `metric_snapshots`.
- REST API для получения метрик и статуса шлюза.
- JWT auth: `register`, `login`, `refresh`, `logout`, `me`.
- Логирование действий в `audit_log`.
- Хранение пользователей и refresh-токенов в PostgreSQL.

## 3. Источник данных OPC UA (AS-IS)
- Endpoint (пример): `opc.tcp://opcua-server:4840/metrics/server/`
- Namespace URI: `urn:argum:demo:metrics`
- Root object: `Objects/DeviceMetrics`

### Узлы OPC UA (текущая реализация)
- `TemperatureC : Double`
- `CpuLoadPercent : Double`
- `RamLoadPercent : Double`
- `UptimeSeconds : UInt32`
- `SupplyVoltageV : Double`
- `TimestampUtc : String` (UTC ISO-8601)

### Маппинг REST -> OPC UA
- `temperatureC` -> `TemperatureC`
- `cpuLoadPercent` -> `CpuLoadPercent`
- `ramLoadPercent` -> `RamLoadPercent`
- `uptimeSeconds` -> `UptimeSeconds`
- `supplyVoltageV` -> `SupplyVoltageV`
- `timestampUtc` -> `TimestampUtc`

## 4. Конфигурация сервиса
Минимально необходимые параметры:
- `server.port`
- `server.basePath` (`/api/v1`)
- `opcua.endpointUrl`
- `opcua.namespaceUri`
- `opcua.rootPath` (`Objects/DeviceMetrics`)
- `opcua.pollIntervalMs` (рекомендуется `1000`)
- `jwt.issuer`, `jwt.audience`, `jwt.secret` (или keypair)
- `jwt.accessTokenTtlSec` (например `900`)
- `jwt.refreshTokenTtlSec` (например `2592000`)
- `postgres.dsn`

## 5. Роли и доступ
- `admin` — полный доступ (users, gateway admin endpoints, metrics)
- `operator` — чтение метрик и статуса шлюза
- `viewer` — только чтение метрик (и, при желании, `auth/me`)

## 6. REST API (MVP)
Базовый префикс: `/api/v1`

### 6.1 Auth
#### `POST /auth/register`
Создание пользователя (по умолчанию роль `viewer`).
- Пишет в БД: `users`
- Пишет в `audit_log` (`auth.register`)

#### `POST /auth/login`
Проверка логина/пароля, выдача `accessToken` + `refreshToken`.
- Читает: `users`
- Пишет: `refresh_tokens`, обновляет `users.last_login_at`
- Пишет в `audit_log` (`auth.login`)

#### `POST /auth/refresh`
Обновление access token по refresh token (rotation рекомендуется).
- Читает/обновляет: `refresh_tokens`
- Пишет в `audit_log` (`auth.refresh`)

#### `POST /auth/logout`
Инвалидация refresh token.
- Обновляет: `refresh_tokens.revoked_at`
- Пишет в `audit_log` (`auth.logout`)

#### `GET /auth/me`
Возвращает данные текущего пользователя по access token.
- Читает: `users`

### 6.2 Metrics
#### `GET /metrics/current`
Возвращает последний снапшот метрик из внутреннего кэша шлюза.
- Если кэш пустой: `503 SOURCE_UNAVAILABLE`
- Может писать в `audit_log` (опционально, или только при ошибках)

#### `GET /gateway/status`
Статус web-сервиса + OPC UA клиента + состояние кэша.
- Читает: in-memory state
- Может читать `opcua_sources` (если состояние хранится/синхронизируется в БД)

### 6.3 Admin (опционально в MVP, но рекомендуется в спецификации)
#### `GET /users`
Список пользователей (`admin` only).
- Читает: `users`
- Пишет в `audit_log` (`users.list`)

#### `PATCH /users/{userId}`
Изменение роли/активности/отображаемого имени (`admin` only).
- Обновляет: `users`
- Пишет в `audit_log` (`users.update`)

## 7. Формат токенов и безопасность
### Access token (JWT)
Рекомендуемые claims:
- `sub` (user id)
- `role`
- `iss`, `aud`
- `iat`, `exp`
- `jti`

### Refresh token
- Может быть opaque string или JWT, но в БД хранится **только hash** (`refresh_tokens.token_hash`).
- Рекомендуется rotation + revoke chain (`token_family_id`, `replaced_by_token_id`).

### Пароли
- Хранить только хэш (`Argon2id` / `bcrypt`).
- В БД поле: `users.password_hash`.

## 8. Работа с OPC UA внутри шлюза
### Режим чтения
Для MVP используется polling:
- раз в `opcua.pollIntervalMs` читать 6 узлов из `Objects/DeviceMetrics`
- обновлять in-memory snapshot
- обновлять `opcua_sources.last_read_at/status`
- при включённой истории сохранять запись в `metric_snapshots`

### Правило консистентности
`TimestampUtc` считать маркером готового снапшота (на OPC UA сервере он обновляется последним).

### Поведение при ошибках
- держать `consecutive_errors`
- менять `opcua_sources.status` на `degraded/error`
- не падать процессом целиком
- REST `/metrics/current` может отдавать последний известный снапшот + признак устаревания (рекомендуется в v1.1)

## 9. Единый формат ошибок REST
```json
{
  "error": {
    "code": "SOURCE_UNAVAILABLE",
    "message": "OPC UA source is unavailable",
    "details": {},
    "traceId": "req_xxx"
  }
}
```

Рекомендуемые коды:
- `VALIDATION_ERROR` (`400`)
- `UNAUTHORIZED` (`401`)
- `FORBIDDEN` (`403`)
- `NOT_FOUND` (`404`)
- `CONFLICT` (`409`)
- `RATE_LIMITED` (`429`)
- `SOURCE_UNAVAILABLE` (`503`)
- `SOURCE_TIMEOUT` (`504`)
- `INTERNAL_ERROR` (`500`)

## 10. БД (минимально необходимые таблицы)
Сервис должен использовать таблицы:
- `users`
- `refresh_tokens`
- `audit_log`
- `opcua_sources` (состояние источника/конфиг)
- `metric_snapshots` (опционально, для истории)

## 11. Минимальный жизненный цикл (MVP)
1. Сервис стартует, читает конфиг.
2. Подключается к Postgres.
3. Подключается к OPC UA (или начинает цикл реконнекта).
4. Запускает polling метрик и обновляет кэш.
5. Обслуживает REST-запросы с JWT auth.
6. Логирует auth/admin действия в `audit_log`.

## 12. Версионирование
- REST API versioning: `/api/v1`
- Изменения с ломкой контракта -> `/api/v2`
