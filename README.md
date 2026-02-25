# OPC UA + PostgreSQL bundle (draft)

Архив содержит заготовку окружения для проекта:
- `docker-compose.yml` — поднимает **mini OPC UA server** + **PostgreSQL**
- `opcua-server/` — Dockerfile и код mini OPC UA сервера метрик
- `postgres/init/01_schema.sql` — init-schema с таблицами `users`, `refresh_tokens`, `audit_log` и доп. таблицами
- `docs/web_service_spec.md` — спецификация web-сервиса (OPC UA -> REST Gateway, JWT, БД)
- `docs/rest_sequence.mmd` — sequence-диаграммы для REST API

## Быстрый старт
```bash
docker compose up --build
```

## Что будет доступно
- OPC UA server: `opc.tcp://localhost:4840/metrics/server/`
- PostgreSQL: `localhost:5432`
  - DB: `gatewaydb`
  - User: `gateway_user`
  - Password: `gateway_pass`

## Примечания
- Web-сервис (REST Gateway) в архив **не реализован кодом**, только описан спецификацией и sequence-диаграммами.
- В `users` добавляется seed admin с заглушкой `password_hash`; приложение должно заменить хэш на реальный (Argon2/bcrypt).
- mini OPC UA сервер публикует узлы `Objects/DeviceMetrics/*` и обновляет значения раз в ~1 сек.
