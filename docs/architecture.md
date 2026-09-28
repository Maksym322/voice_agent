# Архітектура v0

VF-001 implements the proposed Python/FastAPI, React/TypeScript, PostgreSQL,
and Docker Compose foundation. VF-003 adds the session/API/browser boundary
and a registered LiveKit Agents worker with a provisional direct-provider
pipeline. Live audio acceptance remains pending the provider, language, budget,
credential, and media hosting choices.
VF-009 adds a reusable operator console over the same server-owned session
records. Deployment brand/navigation defaults are validated environment
settings, while personal board views are stored per user. Product events,
sanitized diagnostics, and agent-change audit records remain separate. See
`docs/operator-console.md`.
VF-005's first slice adds an admin-triggered call from API through a stored
LiveKit outbound SIP trunk and Twilio to one configured +380 destination.
The phone participant joins the same pinned worker/session model as the
browser. VF-005 also prepares a number-scoped inbound trunk and dispatch route,
with one pinned session per call. Carrier delivery has not been verified.
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
Телефон -> SIP-провайдер -> LiveKit SIP -> worker.
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
