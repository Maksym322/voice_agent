# Розширення

MVP використовує перевірені модулі, встановлені під час збирання/деплою.
Довільне завантаження коду через панель не підтримується.
Модуль у процесі backend є довіреним і не має sandbox-ізоляції.

Контракт модуля: id, version, core compatibility, config schema,
secret references, tool schemas, timeout policy, error categories,
health check, contract tests.

Контекст операції: session_id, agent_version_id, permissions,
deadline, correlation_id та idempotency_key для мутацій.
Аргументи моделі валідовані; модель не визначає власні дозволи.

UI MVP: загальна форма налаштувань за схемою.
Складні власні UI-модулі — майбутнє розширення.

Перший адаптер: demo-booking, операції list_services, find_slots,
create_booking. Він використовує тестові дані й перевіряє конфлікти слотів.
