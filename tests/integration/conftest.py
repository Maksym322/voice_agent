"""Run integration tests only against an explicitly named disposable database."""

import os
from collections.abc import Iterator
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://localhost:5432/voice_fleet_test_unavailable"
)
os.environ.setdefault("APP_ORIGIN", "http://localhost:8080")
if TEST_URL:
    parsed = urlparse(TEST_URL)
    name = parsed.path.lstrip("/")
    if not name.startswith("voice_fleet_test"):
        raise RuntimeError("TEST_DATABASE_URL must name a voice_fleet_test* database")
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("TEST_DATABASE_URL must point to local disposable PostgreSQL")
    os.environ["DATABASE_URL"] = TEST_URL
    os.environ["APP_ORIGIN"] = "http://localhost:8080"
    os.environ["ENVIRONMENT"] = "local"


@pytest.fixture(scope="session")
def database() -> Iterator[sessionmaker[Session]]:
    if not TEST_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(TEST_URL)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash, role, created_at) "
                "VALUES (gen_random_uuid(), 'migration-sentinel@example.com', "
                "'unused', 'viewer', now()) ON CONFLICT (email) DO NOTHING"
            )
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT count(*) FROM users WHERE email='migration-sentinel@example.com'")
        ).scalar_one()
        assert found == 1
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(database: sessionmaker[Session]) -> Iterator[TestClient]:
    from voice_fleet_api.db import get_db
    from voice_fleet_api.main import app

    engine = database.kw["bind"]
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE login_sessions, users"))

    def test_db() -> Iterator[Session]:
        with database() as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
