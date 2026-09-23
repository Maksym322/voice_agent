# Архітектура v0

VF-001 implements the proposed Python/FastAPI, React/TypeScript, PostgreSQL,
and Docker Compose foundation. LiveKit Agents remains a future voice task.
The current exact application and tool versions are pinned in `uv.lock`,
`package-lock.json`, and the Dockerfiles. Authentication uses local accounts
and server-side opaque sessions. See `docs/authentication.md` and
`docs/migrations.md`. Owner confirmation of these implementation choices is
recorded in `docs/decisions.md` when received.

## Компоненти
- apps/web: панель оператора, конфігурації, playground, сесії та звіти.
- apps/api: авторизація, конфігурації, запуск сесій і реєстр інтеграцій.
- apps/voice-worker: виконання сесій, взаємодія з LiveKit і моделями.
- PostgreSQL: конфігурації, користувачі, події та результати.
- Об'єктне сховище: додається, коли потрібні аудіо й великі артефакти.

Браузер -> LiveKit <-> worker -> STT/LLM/TTS.
Телефон -> Twilio/SIP -> LiveKit.
Панель -> API -> PostgreSQL.
Worker -> перевірені бізнес-інструменти -> зовнішні API.

## Контракти
Сесія отримує серверно перевірений контекст і незмінний snapshot конфігурації.
Токен браузера короткоживучий і обмежений потрібною кімнатою.
Worker не довіряє клієнтському agent_id без серверної перевірки.
Права на читання та зміни перевіряє API.
Повторення мутацій використовує idempotency key; невідомий результат звіряється.
Ліміти тривалості, паралельності й викликів задаються конфігурацією.
Завершення worker має коректно обробляти активні сесії.

## Дані
Organization (одна на інсталяцію), User, Agent, AgentVersion,
DeploymentBinding, Integration, Session, SessionEvent, TestSuite, TestRun, AuditEvent.

## Релізи
Версія продукту, версія схеми конфігурації та версія агента відокремлені.
Rollback конфігурації не відкочує базу. Оновлення коду потребує
перевірки сумісності міграцій та окремого плану відновлення.

Довідка: https://docs.livekit.io/agents/
