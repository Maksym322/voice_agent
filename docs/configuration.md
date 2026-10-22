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
`session_limit_seconds`, and `retention_days`. Unknown fields and unsupported
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
VF-003; VF-002 does not start sessions.

All reads require sign-in. Admins and operators can mutate configurations;
viewers can read only. Mutations require the existing CSRF and Origin checks.
Create, edit, import, publish, and activation write audit events with actor,
time, and identifiers. Audit details never store full configuration text.
