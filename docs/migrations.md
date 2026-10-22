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

