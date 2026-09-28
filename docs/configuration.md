# Конфігурація

Клієнтський пакет: client.yaml, agents/, knowledge/, branding/, deployment/.
Секрети передаються середовищем або secret store, у файлах лише посилання.

Поля: schema_version, organization, branding, enabled_modules,
agent definitions, provider references, tool allowlists, locale, timezone,
session limits, retention policy.

Файл імпортується як валідована чернетка. Runtime читає опубліковану
версію з бази. Експорт повертає конфігурацію без секретів.
Не допускається неявне перезаписування UI-змін файлом.

Стани: draft -> published -> active binding.
Публікація створює незмінний snapshot. Активація атомарно змінює binding.
Активні розмови зберігають свою версію.

## VF-002 JSON contract

`AgentConfig` is the versioned API schema (`GET /openapi.json` exposes its JSON
Schema). Version 1 requires `instructions` and accepts `locale`, `timezone`,
`provider_references`, `tool_allowlist`, `enabled_modules`, `branding`,
`session_limit_seconds`, `retention_days`, and `voice`. The `voice` object pins
the supported Deepgram Nova-3 STT, OpenAI GPT-4o mini or Google Gemini 2.5
Flash-Lite / 3.5 Flash-Lite LLM, and Cartesia Sonic 3 TTS model IDs and a Cartesia voice ID in
each published snapshot. OpenAI remains the default; selecting Google requires
both `voice.llm_provider="google"` and
`voice.llm_model="gemini-3.5-flash-lite"` in the draft before publication.
Older published 2.5 Flash-Lite snapshots remain valid, though Google limits
access to existing users of that model.
The worker then reads `GOOGLE_API_KEY` rather than `OPENAI_API_KEY`. Only the
selected LLM key is required. This is a provisional provider choice pending
the owner decision; changing a draft cannot alter a
running session's model selection. Unknown fields and unsupported
schema versions fail validation with field-level HTTP 422 errors. Provider
values must be `env:NAME` or `secret:NAME` references. Do not enter raw secrets
in instructions or branding text; those fields are part of an export.

`POST /api/agents` creates a draft. `PUT /api/agents/{id}/draft` saves it;
`POST /api/agents/{id}/import` validates a JSON configuration and replaces the
draft. Both draft mutations require `If-Match: <current draft revision>`.
`POST /api/agents/{id}/publish` also requires that revision and creates a new
immutable snapshot. `GET /api/agents/{id}/versions/{version_id}/export` returns
the validated snapshot, with references but no secret values. There is no
published-version edit endpoint, and the database rejects updates and deletes.

`PUT /api/agents/{id}/bindings/{environment}` accepts a published version ID
and `expected_revision` (0 if no binding exists). `local`, `staging`, and
`production` are supported. An agent row lock serializes publication, draft
edits, and binding changes. Stale revisions return HTTP 409. Binding a previous
version performs rollback for future sessions. The target must belong to the
agent and use a supported schema version. Runtime session pinning starts in
VF-003; VF-002 does not start sessions. The VF-003 session row references the
published version selected by the environment binding at start. Later binding
changes cannot change this row. See `docs/sessions.md` for the session API.

All reads require sign-in. Admins and operators can mutate configurations;
viewers can read only. Mutations require the existing CSRF and Origin checks.
Create, edit, import, publish, and activation write audit events with actor,
time, and identifiers. Audit details never store full configuration text.

## VF-005 phone route configuration

Phone numbers and their active agent routes are stored per installation in
PostgreSQL and are excluded from agent configuration exports. Admins may add a
number only when it is actually owned and an active agent binding exists.
`INBOUND_SIP_ALLOWED_ADDRESSES` is a comma-separated carrier origination IP/CIDR
allowlist in ignored `.env`; it is required to create an inbound LiveKit trunk.
No default carrier or number is provisioned. `OUTBOUND_SIP_TRUNK_ID` and
`OUTBOUND_TEST_DESTINATION` remain independent settings for the bounded manual
outbound call. See `docs/sessions.md` for API and session direction contracts.
