# Home Installation Upgrade Runbook: `voice-fleet-home`

This document provides a reviewable, provider-neutral runbook for safely preparing and upgrading the existing home laptop deployment of Voice Fleet from historical snapshot `dcc59c9` to the target tested upstream revision `23c633e16dc5c9a9ed27f643852a5b1977c3b793`.

> [!IMPORTANT]
> **Safety Guardrails and Boundary Rules:**
> - Never run `docker compose down --volumes` or destroy/prune the existing database volume `voice-fleet-home_db_data`.
> - Never execute automatic schema downgrades against live data. Rollback is strictly defined as pairing old application images/code with a verified pre-upgrade database restore executed during an explicit maintenance window.
> - Never print, copy, inspect, or log the contents of `.env`, home override compose files, user records, credentials, or session transcripts.
> - Never create synthetic production accounts on the live system, enable paid third-party services, or initiate live audio/SIP calls during preparation or upgrade.
> - Published configurations are immutable and each session pins its configuration version at startup. Upgrading code and schema does not alter existing published configuration snapshots.

---

## 1. Current State & Access Blocker

### 1.1 Historical Evidence vs. Unexecuted Host Checks
- **Historical Evidence (Observed 2026-10-21 via key-authenticated SSH):**
  - Application readiness endpoint `/health/ready` responded with HTTP `200`.
  - Docker socket `/var/run/docker.sock` has ownership `root:docker` and permissions `0660`.
  - The unprivileged SSH user `waks` is **not** a member of the `docker` group.
  - Non-interactive sudo check (`sudo -n true`) exits nonzero and reports that a password is required.
  - Previous deployment documentation names project `voice-fleet-home`, deployment directory `/home/waks/projects/voice`, database volume `voice-fleet-home_db_data`, and snapshot `dcc59c9`.
- **Unexecuted Host Checks (Must NOT be claimed as already run):**
  - Live Docker container inspection (`docker ps`, `docker inspect`).
  - Active PostgreSQL database connection, direct table row inspections, or live volume integrity scans.
  - Direct read of the existing production `.env` file or Docker Compose override files.
  - Live migration verification or owner acceptance on the laptop host.

### 1.2 Access Blocker & Owner Requirement
Because the SSH user `waks` lacks Docker daemon permissions and non-interactive `sudo` access:
- **Blocker:** Automated agents or unprivileged scripts cannot query Docker or invoke privileged administrative commands remotely.
- **Resolution:** The system owner must run all privileged and Docker-interacting commands **interactively in an interactive shell session** (with interactive `sudo` or an authorized user).
- **Rule:** Do not attempt to alter user group memberships, edit `/etc/sudoers`, or weaken permissions.

---

## 2. Environment & Inventory Verification Phase

Before executing any data mutation, directory changes, or service stops, the operator must verify the exact project naming and directory paths.

### 2.1 Inventory Parameter Matrix
Confirm the following parameters match the host environment:

| Parameter | Required Value | Purpose |
| :--- | :--- | :--- |
| **Project Name** | `voice-fleet-home` | Compose project namespace (`-p voice-fleet-home`) |
| **Existing Source Directory** | `/home/waks/projects/voice` | Current live deployment checkout |
| **Current Baseline Snapshot** | `dcc59c9` | Commit corresponding to VF-002 agent configurations |
| **Target Upstream Revision** | `23c633e16dc5c9a9ed27f643852a5b1977c3b793` | Current tested upstream revision (includes VF-003, VF-009, VF-005) |
| **Named DB Volume** | `voice-fleet-home_db_data` | Persistent PostgreSQL data volume |
| **Staging Release Directory** | `/home/waks/projects/voice-releases/23c633e` | Isolated directory for target revision |
| **Backup Storage Directory** | `/home/waks/backups/voice-fleet` | Restrictively secured backup destination |

### 2.2 Host Verification Commands
Run interactively as the system owner on the laptop:

```bash
# Verify current checkout location and git revision
cd /home/waks/projects/voice
pwd
git rev-parse HEAD
# Ensure HEAD starts with dcc59c9...

# Verify running Compose services and project name using sudo
sudo docker compose -p voice-fleet-home ps

# Verify the persistent volume exists and matches voice-fleet-home_db_data
sudo docker volume ls --filter name=voice-fleet-home_db_data

# Verify application readiness before any changes
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/health/ready
# Expected: 200
```
> [!CAUTION]
> If the git commit is not `dcc59c9`, if the project name differs, or if `/health/ready` does not return `200`, halt execution immediately and investigate. Do not proceed with migration.

---

## 3. Database Backup & Independent Verification

To guarantee zero data loss, create a restricted PostgreSQL custom-format backup and verify it by restoring into an ephemeral disposable database before making any code or migration changes.

### 3.1 Create Secure Backup Directory
```bash
# Create backup storage directory with restrictive permissions
mkdir -p /home/waks/backups/voice-fleet
chmod 700 /home/waks/backups/voice-fleet
BACKUP_FILE="/home/waks/backups/voice-fleet/voice_fleet_home_pre_upgrade_$(date +%Y%m%d_%H%M%S).dump"
```

### 3.2 Execute Restricted Custom-Format Backup
Extract the database backup in PostgreSQL custom format (`-Fc`), which allows selective inspection and restoration with `pg_restore`:

```bash
# Run pg_dump within the running db container of project voice-fleet-home
sudo docker compose -p voice-fleet-home exec -T db \
  pg_dump -U voice_fleet -d voice_fleet -Fc > "${BACKUP_FILE}"

# Secure file permissions immediately
chmod 600 "${BACKUP_FILE}"

# Verify backup file size is non-zero
ls -lh "${BACKUP_FILE}"
```

### 3.3 Verify Backup in Disposable Database
To confirm backup integrity without risking live data:
1. Create a temporary disposable database inside the existing PostgreSQL container.
2. Restore the backup dump into the disposable database.
3. Compare schema and aggregate counts without logging personal user data or credentials.
4. Drop the disposable database immediately.

```bash
DISPOSABLE_DB="vf_verify_$(date +%s)"

# 1. Create temporary disposable database
sudo docker compose -p voice-fleet-home exec -T db \
  psql -U voice_fleet -d postgres -c "CREATE DATABASE ${DISPOSABLE_DB};"

# 2. Restore dump into the disposable database
sudo docker compose -p voice-fleet-home exec -i db \
  pg_restore -U voice_fleet -d "${DISPOSABLE_DB}" --no-owner --role=voice_fleet < "${BACKUP_FILE}"

# 3. Compare table list and synthetic aggregate row counts between live DB and verified DB
echo "--- Comparing live DB and disposable DB table list ---"
sudo docker compose -p voice-fleet-home exec -T db \
  psql -U voice_fleet -d voice_fleet -t -A -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;" > /tmp/tables_live.txt

sudo docker compose -p voice-fleet-home exec -T db \
  psql -U voice_fleet -d "${DISPOSABLE_DB}" -t -A -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;" > /tmp/tables_disposable.txt

diff -u /tmp/tables_live.txt /tmp/tables_disposable.txt
# If diff is empty, schema table structures match.

echo "--- Comparing aggregate row counts ---"
sudo docker compose -p voice-fleet-home exec -T db \
  psql -U voice_fleet -d voice_fleet -t -A -c \
  "SELECT 'users', count(*) FROM users UNION ALL SELECT 'agents', count(*) FROM agents UNION ALL SELECT 'agent_versions', count(*) FROM agent_versions UNION ALL SELECT 'deployment_bindings', count(*) FROM deployment_bindings UNION ALL SELECT 'alembic_version', count(*) FROM alembic_version;" > /tmp/counts_live.txt

sudo docker compose -p voice-fleet-home exec -T db \
  psql -U voice_fleet -d "${DISPOSABLE_DB}" -t -A -c \
  "SELECT 'users', count(*) FROM users UNION ALL SELECT 'agents', count(*) FROM agents UNION ALL SELECT 'agent_versions', count(*) FROM agent_versions UNION ALL SELECT 'deployment_bindings', count(*) FROM deployment_bindings UNION ALL SELECT 'alembic_version', count(*) FROM alembic_version;" > /tmp/counts_disposable.txt

diff -u /tmp/counts_live.txt /tmp/counts_disposable.txt
# Ensure count diff is completely empty.

# Clean up verification text files
rm -f /tmp/tables_live.txt /tmp/tables_disposable.txt /tmp/counts_live.txt /tmp/counts_disposable.txt

# 4. Cleanly drop the temporary disposable database
sudo docker compose -p voice-fleet-home exec -T db \
  psql -U voice_fleet -d postgres -c "DROP DATABASE ${DISPOSABLE_DB};"
```
> [!NOTE]
> The queries above select only table names and aggregate row counts (`count(*)`). They do not output names, emails, hashes, tokens, or prompt contents, ensuring strict confidentiality.

---

## 4. Staging the Target Release

The upgrade uses a separate release directory to ensure that the existing checkout `/home/waks/projects/voice` remains untouched and can serve as an immediate rollback reference.

### 4.1 Clone / Fetch Target Revision
```bash
# Define release paths
RELEASE_DIR="/home/waks/projects/voice-releases/23c633e"
mkdir -p /home/waks/projects/voice-releases

# Fetch target revision into release directory from git upstream
if [ ! -d "${RELEASE_DIR}" ]; then
  git clone /home/waks/projects/voice "${RELEASE_DIR}"
fi

cd "${RELEASE_DIR}"
git fetch origin
git checkout 23c633e16dc5c9a9ed27f643852a5b1977c3b793
git status
```

### 4.2 Preserve Existing Configuration Files
Preserve the existing `.env` and any local Compose overrides (e.g., `compose.override.yaml`) by copying them directly from the old directory without echoing or inspecting their contents:

```bash
# Copy .env and local override without printing content
cp /home/waks/projects/voice/.env "${RELEASE_DIR}/.env"
chmod 600 "${RELEASE_DIR}/.env"

if [ -f /home/waks/projects/voice/compose.override.yaml ]; then
  cp /home/waks/projects/voice/compose.override.yaml "${RELEASE_DIR}/compose.override.yaml"
fi
```

### 4.3 Build Staged Container Images
Build the container images in the staged directory ahead of time to minimize downtime during the maintenance window:
```bash
cd "${RELEASE_DIR}"
sudo docker compose -p voice-fleet-home build
```

---

## 5. Upgrade & Forward Migration Execution

### 5.1 Understanding Forward Migrations (0002 through 0007)
The baseline snapshot `dcc59c9` was at Alembic revision `0002_agent_configurations`. Target revision `23c633e16dc5c9a9ed27f643852a5b1977c3b793` advances schema through the following sequential migrations:

1. **`0003_voice_sessions`:**
   - Adds `voice_sessions` and `session_events` tables.
   - Pins immutable agent version foreign keys, session status, lifecycle timestamps, metrics, and error fields.
   - Leaves existing users, login sessions, agents, and configuration versions untouched.
2. **`0004_operator_console`:**
   - Adds `channel` column to sessions (defaults to `browser`) and `source` column to events.
   - Adds indexes for operator console queries, `session_diagnostics` table, and per-user `operator_views` table.
   - Adds `room_cleanup_pending` boolean to handle graceful cleanup retries.
3. **`0005_outbound_test`:**
   - Adds `outbound_destination_masked` and `outbound_provider_call_id` to voice sessions.
   - Restricts channel values to `browser` or `phone`. Existing browser sessions remain valid.
4. **`0006_phone_numbers`:**
   - Adds `phone_numbers` table for SIP trunk and inbound routing metadata.
   - Adds `direction` (`browser`, `inbound`, `outbound`) and optional `phone_number_id` foreign key to `voice_sessions`.
   - Backfills existing sessions without rewriting history.
5. **`0007_phone_route_lifecycle`:**
   - Adds `status` enum column (`active`, `deprovisioning`, `retired`) to `phone_numbers`.
   - Backfills existing phone number records to `active`.
   - API `/health/ready` check validates that the schema is at revision `0007`.

### 5.2 Step-by-Step Maintenance Execution
Perform these steps interactively during a designated maintenance window:

```bash
# 1. Stop web and api traffic from the old deployment to prevent concurrent transactions
cd /home/waks/projects/voice
sudo docker compose -p voice-fleet-home stop web api worker

# 2. Switch to staged release directory
cd /home/waks/projects/voice-releases/23c633e

# 3. Apply Alembic migrations to head (revision 0007) using one-shot container
sudo docker compose -p voice-fleet-home run --rm api alembic upgrade head

# 4. Bring up the full updated stack
sudo docker compose -p voice-fleet-home up -d

# 5. Check container process status
sudo docker compose -p voice-fleet-home ps
```

### 5.3 Post-Migration System Behavior Checks
Confirm the expected runtime behaviors:

- **Database Preservation Checks (Aggregate Only):**
  Verify that existing accounts, agents, versions, and bindings were preserved without inspecting private data:
  ```bash
  sudo docker compose -p voice-fleet-home exec -T db \
    psql -U voice_fleet -d voice_fleet -c \
    "SELECT version_num FROM alembic_version;"
  # Expected: 0007_phone_route_lifecycle

  sudo docker compose -p voice-fleet-home exec -T db \
    psql -U voice_fleet -d voice_fleet -c \
    "SELECT count(*) AS total_users FROM users; SELECT count(*) AS total_agents FROM agents; SELECT count(*) AS total_versions FROM agent_versions;"
  ```
- **Loopback Origin & Readiness Check:**
  The API binds to `127.0.0.1` and verifies `APP_ORIGIN` (default `http://localhost:8080`).
  ```bash
  curl -i http://127.0.0.1:8080/health/ready
  # Expected: HTTP/1.1 200 OK
  ```
  If migrations are incomplete or database connection fails, the endpoint returns `503 Service Unavailable`.

- **Explicitly Unconfigured Worker Behavior:**
  When `LIVEKIT_URL`, `LIVEKIT_API_KEY`, or `LIVEKIT_API_SECRET` are not set in `.env`, the worker container exits intentionally with:
  `Voice Fleet worker unavailable: LiveKit is not configured.`
  This is expected on home installations that do not run an active LiveKit server. Check worker logs to confirm clean startup handling:
  ```bash
  sudo docker compose -p voice-fleet-home logs worker
  ```

---

## 6. Rollback Strategy

> [!WARNING]
> Reverting code files alone after forward migrations have been applied is **not** a valid rollback procedure.

### 6.1 Rollback Principle
Downward Alembic migrations (e.g., `0007 -> 0006 -> ... -> 0002`) are restrictive:
- Revisions `0007` and `0006` refuse to downgrade if phone routes or inbound sessions exist.
- Downward migration removes session event history, diagnostics, operator views, and voice tables.
- An automatic database downgrade on a live system risks data corruption.

Therefore, safe rollback is strictly defined as:
**Paired reinstatement of the old code/images (`dcc59c9`) together with restoring the pre-upgrade PostgreSQL backup created in Section 3.**

### 6.2 Rollback Procedure
If the upgrade fails health checks or owner manual verification:

```bash
# 1. Stop all services in the release directory
cd /home/waks/projects/voice-releases/23c633e
sudo docker compose -p voice-fleet-home stop

# 2. Start only the database service to perform restore
sudo docker compose -p voice-fleet-home up -d db
sudo docker compose -p voice-fleet-home exec -T db pg_isready -U voice_fleet -d voice_fleet

# 3. Restore the pre-upgrade backup into voice_fleet database
# Terminate existing connections and recreate the database
sudo docker compose -p voice-fleet-home exec -T db \
  psql -U voice_fleet -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='voice_fleet' AND pid <> pg_backend_pid();"

sudo docker compose -p voice-fleet-home exec -T db \
  psql -U voice_fleet -d postgres -c "DROP DATABASE voice_fleet; CREATE DATABASE voice_fleet OWNER voice_fleet;"

# Restore custom-format dump
sudo docker compose -p voice-fleet-home exec -i db \
  pg_restore -U voice_fleet -d voice_fleet --no-owner --role=voice_fleet < "${BACKUP_FILE}"

# Verify restored schema version
sudo docker compose -p voice-fleet-home exec -T db \
  psql -U voice_fleet -d voice_fleet -c "SELECT version_num FROM alembic_version;"
# Expected: 0002_agent_configurations

# 4. Return to old project checkout and restart containers with old images
cd /home/waks/projects/voice
sudo docker compose -p voice-fleet-home up -d

# 5. Verify readiness on the restored old release
curl -i http://127.0.0.1:8080/health/ready
# Expected: HTTP/1.1 200 OK
```

---

## 7. Repository Checks & Manual Acceptance Steps

### 7.1 Executable Check Commands (Code Repository)
These commands are executed in the local repository workspace to verify code standards prior to handoff:

```powershell
# Python linting and code formatting
uv run --frozen --all-packages ruff check .
uv run --frozen --all-packages ruff format --check .

# Python typecheck
uv run --frozen --all-packages mypy apps/api/src apps/voice-worker/src tests

# Python unit test suite
uv run --frozen --all-packages pytest tests/unit

# Web lint, typecheck, and production build
npm run lint
npm run typecheck
npm run build
```

### 7.2 Manual Owner Acceptance Criteria (On Deployed Host)
The system owner must manually verify the upgraded installation in the browser (e.g. at `http://localhost:8080`):

1. **Admin Authentication:**
   - Sign in using an existing administrator account created prior to the upgrade.
   - Confirm successful authentication and session cookie issuance (`set-cookie` with `SameSite=Lax`, `HttpOnly`).
   - Confirm unauthenticated requests to `/api/auth/me` return 401.
2. **Draft, Publish, and Activate Workflow:**
   - Navigate to the Agent Editor in the dashboard.
   - Modify an existing agent draft or create a new test draft configuration.
   - Publish a new immutable version snapshot (e.g. v2). Confirm the revision increments and cannot be modified in place.
   - Activate the new version binding on the `local` environment.
   - Verify that the active version indicator updates immediately.
3. **Restart Persistence:**
   - Stop and restart the Compose services using `sudo docker compose -p voice-fleet-home restart`.
   - Confirm `/health/ready` returns 200 after restart.
   - Refresh the dashboard in the browser; verify that the active session and newly activated agent binding persist without data loss.

---

## 8. Current Handoff Status & Non-Claims

> [!IMPORTANT]
> **Explicit Non-Claims:**
> - Neither this runbook nor this preparation task claims that the home upgrade, live database backup, disposable restore verification, schema migration 0002–0007, or owner manual acceptance have been executed on the target host.
> - Host execution is blocked until the system owner executes the privileged commands interactively in accordance with Section 1 and Section 2.
