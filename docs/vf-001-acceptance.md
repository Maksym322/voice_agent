# VF-001 acceptance record

Date: 2026-09-23. Product repository:
`C:\Users\Maks\Desktop\prada\voice`, branch `vf-001-foundation`.
HEAD does not exist yet. The original documentation and the implementation are
untracked, so there is no committed baseline or clean Git checkout to compare.
No commit, push, PR, hosted CI run, publication, or deployment was performed.

## Changes and rationale

Added pinned Python and npm workspaces, API and web applications, a labeled
worker scaffold, Alembic migration, Compose deployment, interactive account
bootstrap, local test commands, isolated Docker checks, and CI workflow.
Authentication uses server-stored opaque sessions, Argon2 password hashes,
server-enforced roles, SameSite/HttpOnly cookies, origin checks, and a CSRF
token for sign-out. The environment template has no password. Real voice,
telephony, agent configuration, and integrations remain later tasks.

## Criteria

| Criterion | Evidence | Status |
| --- | --- | --- |
| AC-1 documented clean start | Isolated Compose build/start, API readiness, browser sign-in, and restart passed. A literal clean Git checkout is unavailable before the initial commit. | Local behavior passed; clean checkout pending |
| AC-2 migration | PostgreSQL integration suite applied revision 0001 twice and preserved a sentinel row. Startup check observed 503 readiness and nonzero Alembic execution when the isolated DB was stopped. | Passed locally |
| AC-3 unauthenticated protection | Integration suite returned 401 for missing, invalid, expired, and revoked sessions; Chromium direct navigation showed sign-in. | Passed locally |
| AC-4 no default production password | The empty `.env.example` values caused Compose config to fail; the startup check found no usable account before explicit bootstrap; unit test verified hashing. | Passed locally |
| AC-5 CI checks | Workflow runs locked setup, Python/web lint and types, unit/integration/browser tests, and isolated startup. Corresponding local checks passed. The GitHub remote is connected; hosted execution awaits the first push. | Local checks passed; hosted CI unexecuted |
| AC-6 sign-in/out and replay | Chromium and API startup checks signed in, signed out, and rejected the old cookie. | Passed locally; owner manual check pending |
| AC-7 roles | PostgreSQL integration tests verified admin/operator/viewer and direct forged role header behavior. | Passed locally |
| AC-8 worker and persistence | Startup check read the explicit worker scaffold log and signed in after service restart without deleting the database volume. | Passed locally |
| AC-9 CSRF and wrong login | Integration tests rejected logout without CSRF; wrong password created no session. Chromium displayed an error for wrong login. | Passed locally |

## Checks

All commands ran from the product repository. The local JSON check reports are
stored under the development plugin's `artifacts/` directory and use synthetic
data. They are not part of the product repository.

| Command | Actual result |
| --- | --- |
| `uv sync --locked --all-packages --group dev`, `npm ci` | Passed |
| `uv run --frozen --all-packages ruff check .` | Passed, exit 0 after formatting fix |
| `uv run --frozen --all-packages ruff format --check .` | Passed, exit 0 after formatting fix |
| `uv run --frozen --all-packages mypy apps/api/src apps/voice-worker/src tests` | Passed, exit 0 |
| `uv run --frozen --all-packages pytest tests/unit` | 5 passed, exit 0 |
| `uv run --frozen --all-packages python scripts/check_integration.py` | 4 passed, exit 0 |
| `npm run lint`, `npm run typecheck`, `npm run build` | Passed, exit 0 each |
| `npm run test:e2e` | 1 Chromium test passed, exit 0 |
| `uv run --frozen --all-packages python scripts/check_startup.py` | Passed, exit 0; clean start, migration failure, auth, worker, restart |
| `docker compose config --quiet` with synthetic filled values | Passed, exit 0 |
| `docker compose config --quiet` with `.env.example` | Rejected missing password/URL as expected, exit 1 |
| Hosted GitHub Actions | Unexecuted: awaiting the first push |
| Owner sign-in/sign-out acceptance | Sign-in confirmed by owner; sign-out pending |

Earlier startup attempts failed on invalid synthetic email, piped interactive
`getpass` input, and a case-sensitive test header lookup. The code and checks
were corrected; the final isolated startup and browser runs passed. Initial
Ruff checks found formatting issues; final lint and format checks passed.
An additional review found that bootstrap accepted malformed email addresses
which the login API rejected; both now use the same validator, with a unit test.
The integration suite emitted a Starlette deprecation warning for its current
`httpx` test adapter; it did not affect the test outcome.

## Contracts, configuration, and migrations

The HTTP routes, statuses, roles, cookies, and CSRF behavior are in
`docs/authentication.md`. Environment setup is in `README.md` and
`.env.example`. Revision `0001_foundation` and its failure behavior are in
`docs/migrations.md`. Direct dependencies and containers use exact version
tags; transitive Python and npm packages are locked in `uv.lock` and
`package-lock.json`. Official SDK references are linked from `docs/testing.md`.
The selected stack and local-account method are implementation choices for
VF-001; owner confirmation of the open architecture decision remains pending.

## Manual acceptance

1. Start from a reviewed checkout with Docker Engine running. Follow README:
   fill ignored `.env` with a unique local password, then build and start
   Compose. Confirm `/health/ready` returns 200.
2. Create an admin through the interactive command. Sign in to the dashboard,
   confirm the displayed identity, sign out, and verify direct dashboard access
   asks for sign-in. Reusing the old session cookie must return 401.
3. Try a wrong password and direct anonymous `/api/auth/me` request; expect
   denial. Create synthetic operator/viewer users and verify both receive 403
   from `/api/admin/health`, while admin receives 200.
4. Inspect the worker scaffold log. Restart services without deleting volumes
   and confirm the admin can still sign in. Stop with `docker compose down`.
   Delete volumes only for a specifically disposable test installation.

Code implementation: ready for owner acceptance. Human acceptance: pending.
The GitHub-hosted CI and literal clean-checkout checks remain pending the first
push. No API/provider keys are needed for VF-001.
