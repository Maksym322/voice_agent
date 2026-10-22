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
