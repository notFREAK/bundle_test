# 12 реализаций OPC UA -> REST Gateway

Реализованы 12 технологий:
1. C# / ASP.NET Core
2. Golang (Go)
3. Java / Spring Boot
4. Kotlin / Spring Boot
5. Node.js / TypeScript / NestJS
6. Node.js / Express
7. Python / FastAPI
8. Python / Django
9. PHP / Laravel-style (single-file router)
10. Ruby / Rails-style (WEBrick app)
11. Rust / Axum
12. Elixir / Phoenix-style (Plug router)

## Единый контракт endpoint-ов
Для всех реализаций добавлены endpoint-ы:
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/metrics/current`
- `GET /api/v1/gateway/status`
- `DELETE /api/v1/auth/self` (для удаления benchmark-пользователя)

## Docker
Для каждого стека добавлен `Dockerfile`.
Общий запуск: `docker compose -f docker-compose.implementations.yml up --build`.

## Benchmark
`benchmark-runner/run_benchmark.py` строит сравнительную таблицу и проверяет full-sequence:
`register -> login -> me -> metrics -> status -> refresh -> logout`.


Требование бенчмарка: данные метрик должны читаться из OPC UA, а `register/login` должны работать через PostgreSQL и удалять тестового пользователя через `DELETE /api/v1/auth/self`.
