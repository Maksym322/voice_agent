"""Authentication and authorization through real HTTP and PostgreSQL."""

from datetime import timedelta
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from voice_fleet_api.models import LoginSession, User
from voice_fleet_api.security import hash_password, now_utc

ORIGIN = {"Origin": "http://localhost:8080"}
PASSWORD = "a synthetic long password"


def create_user(database: sessionmaker[Session], email: str, role: str) -> None:
    with database.begin() as db:
        db.add(
            User(
                email=email, password_hash=hash_password(PASSWORD), role=role, created_at=now_utc()
            )
        )


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers=ORIGIN, json={"email": email, "password": password}
    )
    assert response.status_code == 200
    return cast(dict[str, str], response.json())


def test_migration_readiness_and_anonymous_access(client: TestClient) -> None:
    assert client.get("/health/ready").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/admin/health").status_code == 401
    client.cookies.set("vf_session", "invalid")
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_and_origin_create_no_session(
    client: TestClient, database: sessionmaker[Session]
) -> None:
    create_user(database, "admin@example.com", "admin")
    wrong = client.post(
        "/api/auth/login", headers=ORIGIN, json={"email": "admin@example.com", "password": "wrong"}
    )
    assert wrong.status_code == 401
    assert "vf_session" not in wrong.cookies
    denied = client.post(
        "/api/auth/login",
        headers={"Origin": "https://evil.example"},
        json={"email": "admin@example.com", "password": PASSWORD},
    )
    assert denied.status_code == 403
    with database() as db:
        assert db.scalar(select(LoginSession.id)) is None


def test_login_roles_csrf_logout_and_cookie_replay(
    client: TestClient, database: sessionmaker[Session]
) -> None:
    for role in ("admin", "operator", "viewer"):
        create_user(database, f"{role}@example.com", role)

    for role in ("operator", "viewer"):
        client.cookies.clear()
        identity = login(client, f"{role}@example.com")
        assert identity["role"] == role
        assert client.get("/api/auth/me").status_code == 200
        assert client.get("/api/admin/health", headers={"X-Role": "admin"}).status_code == 403
        assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 403
        assert client.get("/api/auth/me").status_code == 200

    client.cookies.clear()
    admin = login(client, "admin@example.com")
    assert client.get("/api/admin/health").status_code == 200
    old_cookie = client.cookies.get("vf_session")
    assert old_cookie
    token = client.get("/api/auth/me").json()["csrf_token"]
    assert token == admin["csrf_token"]
    assert (
        client.post("/api/auth/logout", headers={**ORIGIN, "X-CSRF-Token": token}).status_code
        == 204
    )
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("vf_session", old_cookie)
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client: TestClient, database: sessionmaker[Session]) -> None:
    create_user(database, "admin@example.com", "admin")
    login(client, "admin@example.com")
    with database.begin() as db:
        session = db.scalar(select(LoginSession))
        assert session is not None
        session.expires_at = now_utc() - timedelta(seconds=1)
    assert client.get("/api/auth/me").status_code == 401
