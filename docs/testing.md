# Стратегія тестів

## VF-001 executable checks

The README lists the exact local commands. CI runs Python Ruff lint/format,
Mypy types, unit and PostgreSQL integration tests; web Biome lint, TypeScript
types and Vite build; real Chromium authentication flow; and isolated Compose
startup/restart. The database suite requires `TEST_DATABASE_URL` naming a
`voice_fleet_test*` database and uses synthetic accounts. The browser and
startup commands create unique Compose projects and remove only their own
volumes. They require Docker Engine; browser tests require Playwright Chromium.
No provider keys or paid API calls are part of regular checks. A hosted CI run
remains pending until GitHub is connected.

The implementation follows the current [FastAPI](https://fastapi.tiangolo.com/),
[SQLAlchemy 2](https://docs.sqlalchemy.org/en/20/orm/session.html),
[Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html),
[uv](https://docs.astral.sh/uv/concepts/projects/sync/),
[Vite 8](https://vite.dev/blog/announcing-vite8), and
[Playwright](https://playwright.dev/docs/intro) documentation.

VF-002 adds schema unit tests and PostgreSQL HTTP integration tests for draft
validation, import, publication, immutable rows, viewer access, stale revisions,
simultaneous publication/activation, and rollback. The integration helper runs
pytest using its current Python environment, so `uv run --frozen --all-packages
python scripts/check_integration.py` still uses the pinned environment.

VF-003 checks use a synthetic LiveKit room substitute in the PostgreSQL HTTP
suite to verify access, version pinning, worker lifecycle/event writes, logout
cleanup, failure records, and duration cleanup without provider charges. A unit
check decodes the signed browser token to verify its exact room and publication
grants. These checks do not validate audio. A bounded live smoke test with
LiveKit Cloud, Deepgram Nova-3, Gemini 3.5 Flash-Lite, Cartesia Sonic 3, and
a synthetic Ukrainian browser microphone verified both transcript sides,
nonzero browser audio, server-side latency, and normal room cleanup. The
provider-error path was also observed live. The owner confirmed an audible
response and both transcript sides. Interruption, network loss, and
duration-limit checks remain in `docs/vf-003-acceptance.md`.

VF-009 adds disposable PostgreSQL checks for two operators using the same
agent, role-filtered board/history/log queries, cursor pagination, private
saved views, and retention deletion. Browser type, lint, and build checks
cover the UI bundle. A real two-browser board flow remains a separate manual
check; one successful live session appeared as a real board card and a failed
session appeared in History and Logs. The console deliberately labels
worker readiness unverified because no worker health/capacity API exists.

VF-005 unit checks construct real pinned LiveKit SIP request protobufs with a
synthetic API client and verify carrier allowlist and participant validation.
Disposable PostgreSQL HTTP checks cover admin/CSRF access, number inventory,
stale route revisions, and two inbound session IDs on one number. Those DB
checks require `TEST_DATABASE_URL`; skipping them does not establish migration
or SIP interoperability. A real inbound/outbound call is a separate billed
manual acceptance step.

1. Unit: валідація, permissions, версії, бізнес-правила.
2. Integration: PostgreSQL, конкурентна активація, idempotency, міграції.
3. UI E2E: створити агента -> опублікувати -> переглянути сесію.
4. Live LLM evals: правильні інструменти, уточнення, підтвердження, помилки.
5. Audio: перебивання, тиша, шум, розрив зв'язку, затримка.
6. Self-hosting: чистий запуск, незалежність двох інсталяцій, оновлення.

CI PR не потребує платних API й реальних клієнтських даних.
Live тести окремі, з лімітом кількості сесій, часу й витрат.
LLM оцінювач доповнює точні assertions, а не визначає факт створення запису.

Кожен звіт містить версії коду, конфігурації, моделей, сценаріїв,
результати, помилки та умови вимірювання.
Текстові тести не підтверджують працездатність аудіоканалу.
Порогові значення latency і task success встановлюємо після baseline,
не вигадуємо до реальних вимірювань.

Ручне приймання: природність, перебивання, зрозумілість помилок і панелі.
Довідка: https://docs.livekit.io/agents/start/testing/
