# Voice Fleet

Self-hosted voice-agent platform for one organization per independent installation.
VF-001 provides the API and sign-in dashboard. VF-002 adds agent drafts,
immutable published versions, and environment bindings. VF-003 adds browser
voice sessions and a registered worker. VF-009 adds the operator console for
real sessions, history, diagnostics, and saved views. Live audio acceptance
requires a configured LiveKit server and provider credentials. VF-005 has a
bounded outbound phone-test slice and number-scoped inbound routing code.
Carrier delivery and real phone acceptance remain pending.

## Local start

Prerequisites: Docker Engine with Compose. On Windows use `docker.exe`; the
unqualified `docker` command on the original development machine was shadowed by
an unrelated empty file. No Python, Node, provider keys, or paid APIs are required
to run the Compose application.

1. Copy `.env.example` to ignored `.env`. Choose a new, unique password. Set
   `POSTGRES_PASSWORD` and put the same password in `DATABASE_URL`; URL-encode
   special characters in the URL. Keep `APP_ORIGIN=http://localhost:8080` unless
   changing `WEB_PORT` too. Empty values are rejected. Never commit `.env`.
2. Start Docker Engine, then run:

   ```powershell
   docker.exe compose build
   docker.exe compose up -d
   docker.exe compose ps
   ```

   Compose starts PostgreSQL, applies the versioned migration, then starts the
   API and dashboard. The worker registers only when LiveKit is configured; it
   exits with a clear unavailable message otherwise. A failed migration
   prevents API startup.
   Open http://localhost:8080 and check http://localhost:8080/health/ready.
3. Create the first administrator interactively. There is no default account:

   ```powershell
   docker.exe compose run --rm api python -m voice_fleet_api.admin create-user --role admin
   ```

   Enter the email and a new password of at least 12 characters at the prompts.
   Passwords are stored as Argon2 hashes. Then sign in in the browser.
4. To stop without deleting data, run `docker.exe compose down`. To rerun the
   migration manually, use `docker.exe compose run --rm api alembic upgrade head`.
   A second run should succeed without changing users.

On Linux/macOS, use `docker` in place of `docker.exe`. The default ports are
8080 for the dashboard/API and 5433 for PostgreSQL, both bound to localhost.
Change `WEB_PORT` and `APP_ORIGIN` together. See [authentication](docs/authentication.md),
[migrations](docs/migrations.md), [testing](docs/testing.md), and the
[operator console contract](docs/operator-console.md). The Numbers page stays
empty until an admin configures a real owned number and LiveKit inbound route.
For a paid voice smoke test, see the [live setup and cost guide](docs/live-setup-and-cost.md).

## Development checks

The pinned development tools are Python 3.12.10, uv 0.9.8, and Node 24.11.1.
Install dependencies with `uv sync --locked --all-packages --group dev` and
`npm ci`. Browser checks also need `npx playwright install chromium`.
From the repository root:

```powershell
uv run --frozen --all-packages ruff check .
uv run --frozen --all-packages ruff format --check .
uv run --frozen --all-packages mypy apps/api/src apps/voice-worker/src tests
uv run --frozen --all-packages pytest tests/unit
npm run lint
npm run typecheck
npm run build
```

Database integration tests need a **disposable** PostgreSQL database whose name
begins `voice_fleet_test`. Set `TEST_DATABASE_URL` to its host-reachable URL
and run `uv run --frozen --all-packages pytest tests/integration`. The tests
refuse any other database name and clear their test tables. Do not point them at
the normal installation. `uv run --frozen --all-packages python scripts/check_integration.py`
creates its own disposable database when you do not have one. `npm run test:e2e` and
`uv run --frozen --all-packages python scripts/check_startup.py` each create
and remove their own uniquely named disposable Compose stack. They require
Docker Engine; the browser command also requires Chromium. Regular checks use
synthetic users and no paid APIs.

The GitHub Actions workflow runs these checks on pushes and pull requests when
a GitHub repository is connected. A local pass does not establish a hosted CI pass.

## Project status

VF-001 is ready for owner acceptance; see its
[acceptance record](docs/vf-001-acceptance.md). VF-002 implementation is ready
for manual acceptance; see [its record](docs/vf-002-acceptance.md). VF-003 code
and VF-009 console code passed local automated checks in this isolated branch;
see their [acceptance records](docs/vf-003-acceptance.md) and
[console record](docs/vf-009-acceptance.md). The worker uses a provisional
direct-provider pipeline. The owner confirmed an audible response and both
transcripts. Interruption, network loss, and two-installation branding still
require manual checks and the provider,
language, budget, and LiveKit hosting decisions. See the
[session contract](docs/sessions.md). Product scope and open decisions remain
in [product](docs/product.md), [architecture](docs/architecture.md), and
[decisions](docs/decisions.md). The GitHub remote is connected and VF-001 CI passed on the foundation branch. Deployment is not connected.
Choose a license before a public release.
