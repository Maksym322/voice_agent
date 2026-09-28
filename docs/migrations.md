# VF-001 database migrations

Alembic revision `0001_foundation` creates only `users` and
`login_sessions`. Agent, voice, configuration, and integration tables belong to
later tasks. PostgreSQL data is stored in Compose's named `db_data` volume.

On a clean installation, `docker compose up -d` waits for database health and
runs `alembic upgrade head` through the one-shot `migrate` service. API startup
depends on migration success. `GET /health/ready` checks connectivity and the
expected revision. A migration failure exits nonzero and leaves the API
unavailable; it never resets data automatically.

For an explicit first or repeat run:

```text
docker compose run --rm api alembic upgrade head
```

The second run is idempotent and must preserve accounts. Back up the database
before upgrades. A configuration rollback does not roll back database schema.
Only in a uniquely named, disposable development/test Compose project may you
run `docker compose down --volumes` to discard its synthetic data. Never run
that command against a real installation. VF-001 does not define an automated
production rollback procedure.

## VF-002

Revision `0002_agent_configurations` adds `agents`, `agent_versions`,
`deployment_bindings`, and `audit_events`. It retains existing users and login
sessions. A trigger rejects updates and deletes to published version rows.
Downgrading this revision removes all agent configurations and audit history;
back up the database and use application-level binding rollback for normal
configuration rollback.

## VF-003

Revision `0003_voice_sessions` adds `voice_sessions` and `session_events`.
Each session row has a foreign key to the immutable published agent version,
its room name, owner, deadline, state, and error/metric fields. Events hold
transcript text and lifecycle details. The migration preserves existing data.
Downgrading removes the complete voice session history and transcripts; back up
the database first. No audio recording table or object store is introduced.
Worker events and provider metrics use this revision's existing JSON fields;
the worker completion adds no new migration. Terminal rows and their cascaded
events are deleted by the API's hourly sweep using the pinned published
`retention_days` value. Installations upgrading from the pre-worker VF-003
draft should run `alembic upgrade head`; no data rewrite is required.
Adding the Google Gemini LLM selection changes only validation of new agent
drafts and worker dependencies. Existing published OpenAI snapshots remain
valid and require no schema or data migration. Allowing Gemini 3.5 Flash-Lite
after Google's 2.5 access restriction is another validation-only change:
published 2.5 snapshots and their session pins remain untouched.

## VF-009

Revision `0004_operator_console` adds browser `channel` to session rows and
`source` to event rows, with server defaults for existing data. It adds sort
indexes, bounded `session_diagnostics`, and per-user `operator_views`.
It also adds `room_cleanup_pending`, so API cleanup retries survive worker
shutdown or a provider failure even for databases already at revision 0003.
Diagnostics cascade when a retained session is deleted. The API readiness
check expects this revision; an older schema returns 503. Downgrade removes
saved views and diagnostics. See `docs/operator-console.md` for query behavior.

## VF-005 outbound test slice

Revision `0005_outbound_test` adds a masked destination suffix and a separate
provider call ID to `voice_sessions`, plus a check limiting `channel` to
`browser` or `phone`. Existing browser rows remain valid; no transcript or
recording data is rewritten. The API readiness revision advances to 0005.
Downgrading drops the new phone metadata but keeps session and transcript rows.

## VF-005 inbound routing

Revision `0006_phone_numbers` creates `phone_numbers` with a unique E.164
number, provider label, active route agent, LiveKit inbound trunk and dispatch
rule IDs, and an optimistic route revision. It adds `direction` and optional
`phone_number_id` to voice sessions. Existing browser and phone-test rows are
backfilled as `browser` and `outbound`. Inbound sessions have no `started_by`
user because the caller enters via SIP. The API readiness check expects 0006.

The downgrade refuses to run while number routes or inbound sessions exist:
first remove the corresponding LiveKit resources and export/delete any inbound
history. A database downgrade alone cannot remove provider-side SIP resources.

Revision `0007_phone_route_lifecycle` adds `phone_numbers.status` with `active`,
`deprovisioning`, and `retired` values. Existing rows become `active`; no SIP
resources are changed by migration. API readiness expects 0007. Downgrade
refuses if any route is not active, since the older API cannot represent an
inactive route. Deactivate/reactivate through the API before a downgrade.

