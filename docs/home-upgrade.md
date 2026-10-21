# Home Voice Fleet upgrade preparation

This is a **reviewable, unexecuted operator procedure**, not evidence of a completed
upgrade. Keep one Bash session for its variables and execute one numbered phase at
a time. A failed command means stop and investigate; do not paste the whole document
as an unattended deployment script. No live voice, SIP or paid API test belongs here.

## Facts and prerequisites

- Existing snapshot: documented `dcc59c9`, at `/home/waks/projects/voice`.
  It is an extracted archive **without `.git`**, not a Git checkout.
- Target code: `23c633e16dc5c9a9ed27f643852a5b1977c3b793` from
  `Maksym322/voice_agent`, branch `vf-003-voice-playground`.
  Its historical hosted CI run36487364284 passed; this does not prove a home upgrade.
- Expected Compose project `voice-fleet-home`, DB volume `voice-fleet-home_db_data`,
  baseline schema `0002_agent_configurations`; verify all three on the actual host.
- The home installation uses **both** `compose.yaml` and `compose.home.yaml`.
  Preserve the home override and original ignored `.env` in their existing directory.
  Reference them explicitly; do not print, duplicate or commit their secret contents.
- Observed 2026-10-21: readiness200; Docker socket root:docker0660; waks is not
  in docker group; `sudo -n true` says a password is required. Privileged Docker
  inventory, backup, restore and migrations have not run in this preparation task.
  The owner must execute Docker commands with interactive sudo. No group, sudoers,
  router, SSH or public-port changes are required by this procedure.

Provider configuration and manual voice acceptance remain separate. The current
worker implements Deepgram/Cartesia plus OpenAI or Gemini selected in the published
agent version. Antigravity coding authorization does not supply runtime API keys.
Do not change existing immutable published agent configurations as an upgrade step.

## 1. Establish explicit paths and inspect the actual installation

Run on the laptop as waks. Review any private home override locally; it must still
be suitable when combined with the staged target's base Compose file. Never run
`docker compose config` without `--quiet`, since expanded output contains secrets.

```bash
set -Eeuo pipefail
umask 077
PROJECT=voice-fleet-home
OLD=/home/waks/projects/voice
ENV_FILE="$OLD/.env"
HOME_FILE="$OLD/compose.home.yaml"
TARGET=23c633e16dc5c9a9ed27f643852a5b1977c3b793
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN="/home/waks/backups/voice-fleet/$STAMP"
RELEASE="/home/waks/projects/voice-releases/$TARGET"
test -f "$ENV_FILE" && test -f "$HOME_FILE"
mkdir -p /home/waks/backups/voice-fleet /home/waks/projects/voice-releases
mkdir "$RUN"
chmod 700 "$RUN"
oldc() {
  sudo docker compose --project-directory "$OLD" -p "$PROJECT" \
    --env-file "$ENV_FILE" -f "$OLD/compose.yaml" -f "$HOME_FILE" "$@"
}
oldc config --quiet
oldc ps -a
DB_CONTAINER=$(oldc ps -q db)
test -n "$DB_CONTAINER" && test "$(printf '%s\n' "$DB_CONTAINER" | wc -l)" -eq 1
sudo docker inspect --format '{{json .Mounts}}' "$DB_CONTAINER"
# STOP unless the mount at /var/lib/postgresql/data is the named volume
# voice-fleet-home_db_data, and the running project is the expected installation.
oldc exec -T db psql -X -v ON_ERROR_STOP=1 -U voice_fleet -d voice_fleet \
  -Atc 'SELECT version_num FROM alembic_version;'
# STOP unless the revision is 0002_agent_configurations.
curl --fail --silent --show-error http://127.0.0.1:8080/health/ready
```

The separately staged `~/voice-upgrade/inventory.py` can check the exact volume
and return only service states, schema and aggregate counts. It makes no changes.
No existing admin account is assumed: if none exists, first-admin creation is a
separate interactive owner action from README, never a fabricated acceptance pass.

## 2. Preserve the old executable images before target builds reuse their tags

The source directory alone cannot roll back Compose image tags. Pin and save the
actual old images while their containers still identify them. Stop if any required
container/image cannot be identified; do not guess or rebuild a substitute here.

```bash
printf 'services:\n' > "$RUN/rollback-images.yaml"
for service in api web worker migrate; do
  container=$(oldc ps -a -q "$service")
  test -n "$container" && test "$(printf '%s\n' "$container" | wc -l)" -eq 1
  image=$(sudo docker inspect --format '{{.Image}}' "$container")
  tag="vf-home-rollback-$STAMP-$service:local"
  tag=${tag,,}
  sudo docker image tag "$image" "$tag"
  printf '  %s:\n    image: %s\n    pull_policy: never\n' "$service" "$tag" \
    >> "$RUN/rollback-images.yaml"
  printf '%s %s %s\n' "$service" "$image" "$tag" >> "$RUN/old-images.txt"
done
mapfile -t OLD_TAGS < <(awk '{print $3}' "$RUN/old-images.txt")
sudo docker image save "${OLD_TAGS[@]}" > "$RUN/old-images.tar.part"
test -s "$RUN/old-images.tar.part"
mv "$RUN/old-images.tar.part" "$RUN/old-images.tar"
sha256sum "$RUN/old-images.tar" > "$RUN/old-images.tar.sha256"
```

These files contain no env values, but keep the backup directory private. Retain
the old source, home override and pinned image archive with the DB backup. Image
save success/checksum is not a full restore rehearsal; that still requires an
isolated environment before a production rollback can be claimed verified.

## 3. Stage and build target code without overwriting the running directory

`~/src/voice` is the separate Git checkout. Do not clone the extracted live directory.
A fresh release directory prevents overwriting an earlier attempt or local files.

```bash
git -C /home/waks/src/voice fetch origin
git -C /home/waks/src/voice cat-file -e "$TARGET^{commit}"
mkdir "$RELEASE"
git -C /home/waks/src/voice archive "$TARGET" | tar -x -C "$RELEASE"
printf '%s\n' "$TARGET" > "$RELEASE/.voice-release-commit"
newc() {
  sudo docker compose --project-directory "$RELEASE" -p "$PROJECT" \
    --env-file "$ENV_FILE" -f "$RELEASE/compose.yaml" -f "$HOME_FILE" "$@"
}
newc config --quiet
newc build migrate api web
```

The private `.env` and the home override remain in `$OLD`; they are not copied.
`config --quiet` validates interpolation/configuration, not provider access,
network reachability, account ownership or live audio. Keep the worker stopped
through this provider-neutral update, even if runtime keys already exist.

## 4. Freeze application writes, back up, and verify a disposable restore

Schedule downtime with the owner. No user/agent edits may occur between backup,
verification and migration. Stop writers **before** dumping/counting; otherwise
live writes invalidate comparisons and any zero-loss assumption. All checks below
must pass before migration. A failure can leave the old app stopped; investigate
and use its pinned old images to resume only if no forward migration occurred.

```bash
oldc stop web api worker
BACKUP="$RUN/pre-upgrade.dump"
oldc exec -T db pg_dump -U voice_fleet -d voice_fleet -Fc > "$BACKUP.part"
test -s "$BACKUP.part"
oldc exec -T db pg_restore --list < "$BACKUP.part" > "$RUN/backup.toc"
mv "$BACKUP.part" "$BACKUP"
sha256sum "$BACKUP" > "$RUN/pre-upgrade.dump.sha256"
VERIFY_DB="vf_upgrade_verify_${STAMP,,}"
oldc exec -T db createdb -U voice_fleet -O voice_fleet "$VERIFY_DB"
oldc exec -T db pg_restore --exit-on-error --no-owner -U voice_fleet \
  -d "$VERIFY_DB" < "$BACKUP"

# Schema dumps include columns, constraints, indexes and migration metadata.
# Remove only pg_dump's random psql restrict/unrestrict guard keys for comparison.
for database in voice_fleet "$VERIFY_DB"; do
  oldc exec -T db pg_dump -U voice_fleet -d "$database" --schema-only \
    --no-owner --no-privileges | sed -E '/^\\(un)?restrict /d' \
    > "$RUN/schema-$database.sql"
  oldc exec -T db psql -X -v ON_ERROR_STOP=1 -U voice_fleet -d "$database" -Atc \
    "SELECT 'users',count(*) FROM users UNION ALL SELECT 'agents',count(*) FROM agents UNION ALL SELECT 'agent_versions',count(*) FROM agent_versions UNION ALL SELECT 'deployment_bindings',count(*) FROM deployment_bindings;" \
    > "$RUN/counts-$database.txt"
  oldc exec -T db psql -X -v ON_ERROR_STOP=1 -U voice_fleet -d "$database" \
    -Atc 'SELECT version_num FROM alembic_version;' > "$RUN/revision-$database.txt"
done
diff -q "$RUN/schema-voice_fleet.sql" "$RUN/schema-$VERIFY_DB.sql"
diff -q "$RUN/counts-voice_fleet.txt" "$RUN/counts-$VERIFY_DB.txt"
diff -q "$RUN/revision-voice_fleet.txt" "$RUN/revision-$VERIFY_DB.txt"
# Only the exact disposable DB created above is removed; the real volume is retained.
[[ "$VERIFY_DB" == vf_upgrade_verify_* ]]
oldc exec -T db dropdb -U voice_fleet "$VERIFY_DB"
printf 'Backup restored successfully into a disposable DB; schema/counts matched.\n'
```

Mode077 applies while files are created, including partial dumps. A dump file,
nonzero size or table-name list alone is insufficient evidence of recoverability.
Do not print table rows, account details, transcripts or dump contents. The schema
and aggregate comparison is not an application-level restore rehearsal or proof
of live provider compatibility. Do not proceed on a mismatch.

## 5. Apply forward migrations and start the local web/API services

The old baseline should already be0002. The target adds0003 voice sessions,
0004 console/diagnostics,0005 phone metadata,0006 number routes and0007 route
lifecycle. See `docs/migrations.md`; do not run a schema downgrade.

```bash
newc run --rm --no-deps migrate
newc exec -T db psql -X -v ON_ERROR_STOP=1 -U voice_fleet -d voice_fleet \
  -Atc 'SELECT version_num FROM alembic_version;'
# Expected: 0007_phone_route_lifecycle; STOP on any other value.
newc up -d --no-build api web
newc ps -a
curl --fail --silent --show-error http://127.0.0.1:8080/health/ready
# Wait for startup before concluding failure; never bypass a failed readiness check.
newc exec -T db psql -X -v ON_ERROR_STOP=1 -U voice_fleet -d voice_fleet -Atc \
  "SELECT 'users',count(*) FROM users UNION ALL SELECT 'agents',count(*) FROM agents UNION ALL SELECT 'agent_versions',count(*) FROM agent_versions UNION ALL SELECT 'deployment_bindings',count(*) FROM deployment_bindings;" \
  > "$RUN/counts-after-upgrade.txt"
diff -q "$RUN/counts-voice_fleet.txt" "$RUN/counts-after-upgrade.txt"
```

The host web/DB ports stay loopback through the explicit base+home configuration.
The API listens inside its container; do not expose it publicly. Use the existing
SSH forwarding and browser origin `http://localhost:8080`. No router port is opened.
The worker is intentionally not started, so claim neither online status nor working
audio. Without LiveKit settings its documented startup message is
`Voice Fleet worker unavailable: LiveKit is not configured.` Starting a configured
worker and live acceptance need a separate controlled step and agreed service quota.

After aggregates pass, the owner verifies existing admin login/logout; unauthorized
`/api/auth/me` returns401; existing agents/versions/bindings are present; a test draft
can be published and activated; and `newc restart api web` preserves those results
after readiness recovers. Use test content, never provider calls. Accounts or existing
agent versions must not be edited silently to manufacture an acceptance result.

## 6. Recovery branch: paired database restore and pinned old images

This branch is **manual, unexecuted recovery guidance**, not an automatic rollback.
Keep maintenance in effect and preserve any post-upgrade DB before switching.
A backup restores state as of its snapshot; later writes need separate reconciliation.
Do not claim code-only rollback or zero data loss. First verify checksums and that
`$RUN`, `$BACKUP` and the old-image manifest belong to this exact upgrade attempt.
If the Bash session/variables were lost, stop and reconstruct them from the private
manifest; do not pick the newest backup blindly.

```bash
sha256sum --check "$RUN/pre-upgrade.dump.sha256"
sha256sum --check "$RUN/old-images.tar.sha256"
newc stop web api worker
sudo docker image load --input "$RUN/old-images.tar"
RECOVER_DB="vf_upgrade_recover_${STAMP,,}"
FAILED_DB="vf_upgrade_preserved_${STAMP,,}"
oldc exec -T db createdb -U voice_fleet -O voice_fleet "$RECOVER_DB"
oldc exec -T db pg_restore --exit-on-error --no-owner -U voice_fleet \
  -d "$RECOVER_DB" < "$BACKUP"
oldc exec -T db psql -X -v ON_ERROR_STOP=1 -U voice_fleet -d "$RECOVER_DB" \
  -Atc 'SELECT version_num FROM alembic_version;'
# STOP unless restored revision is 0002_agent_configurations.
# Recheck its schema/aggregate counts using phase4 before switching databases.
# Each ALTER executes separately; never combine DROP/CREATE into a psql transaction.
oldc exec -T db psql -X -v ON_ERROR_STOP=1 -U voice_fleet -d postgres -Atc \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='voice_fleet' AND pid<>pg_backend_pid();" \
  > "$RUN/recovery-disconnects.txt"
oldc exec -T db psql -X -v ON_ERROR_STOP=1 -U voice_fleet -d postgres -c \
  "ALTER DATABASE voice_fleet RENAME TO $FAILED_DB;"
oldc exec -T db psql -X -v ON_ERROR_STOP=1 -U voice_fleet -d postgres -c \
  "ALTER DATABASE $RECOVER_DB RENAME TO voice_fleet;"
oldc -f "$RUN/rollback-images.yaml" up -d --no-build api web
curl --fail --silent --show-error http://127.0.0.1:8080/health/ready
```

Both databases and the real named volume are retained. If the second rename fails,
keep services stopped and have an operator reconcile the names; do not retry blindly.
No `down --volumes`, volume pruning, database deletion, automatic downgrade or
worker/provider restart is part of this recovery branch. Remove preserved databases
or backups only as a separate owner-controlled retention action.

## Repository checks and actual acceptance status

The declared `.fleet/project.json` runs existing Python lint, scoped format, types
and unit checks with a synthetic DATABASE_URL for unit collection; no API key is
required. Web checks remain `npm run lint`, `npm run typecheck`, `npm run build`.
Disposable PostgreSQL integration/startup checks are documented in README; they are
separate from this live installation procedure and must not target its database.
Passing these source checks does not execute or validate this shell runbook against
the laptop. Home backup, restore, image recovery, migration, admin login and owner
acceptance are all **unexecuted** in this preparation task.
