"""Agent publication, authorization, conflict, and rollback over HTTP/PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from test_auth import create_user, login

ORIGIN = "http://localhost:8080"
CONFIG = {
    "schema_version": 1,
    "instructions": "Welcome",
    "provider_references": {"llm": "env:LLM_KEY"},
}


def headers(csrf: str, revision: int | None = None) -> dict[str, str]:
    result = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    if revision is not None:
        result["If-Match"] = str(revision)
    return result


def test_agent_lifecycle_conflicts_permissions_and_rollback(
    client: TestClient, database: sessionmaker[Session]
) -> None:
    create_user(database, "operator@example.com", "operator")
    create_user(database, "viewer@example.com", "viewer")
    operator = login(client, "operator@example.com")
    csrf = operator["csrf_token"]
    created = client.post(
        "/api/agents", headers=headers(csrf), json={"name": "Reception", "config": CONFIG}
    )
    assert created.status_code == 201
    agent = created.json()
    path = f"/api/agents/{agent['id']}"
    assert (
        client.post(
            "/api/agents",
            headers=headers(csrf),
            json={"name": "Bad", "config": {"instructions": ""}},
        ).status_code
        == 422
    )
    v1 = client.post(f"{path}/publish", headers=headers(csrf, 1))
    assert v1.status_code == 201
    assert (
        client.put(
            f"{path}/draft", headers=headers(csrf, 1), json={"name": "Reception", "config": CONFIG}
        ).status_code
        == 409
    )
    edited = client.put(
        f"{path}/draft",
        headers=headers(csrf, 2),
        json={"name": "Reception", "config": {**CONFIG, "instructions": "Welcome back"}},
    )
    assert edited.status_code == 200
    v2 = client.post(f"{path}/publish", headers=headers(csrf, 3))
    assert v2.status_code == 201
    assert (
        client.post(
            f"{path}/import",
            headers=headers(csrf, 4),
            json={**CONFIG, "provider_references": {"llm": "raw-secret"}},
        ).status_code
        == 422
    )
    imported = client.post(
        f"{path}/import", headers=headers(csrf, 4), json={**CONFIG, "instructions": "Imported"}
    )
    assert imported.status_code == 200
    assert imported.json()["revision"] == 5
    assert client.post(f"{path}/import", headers=headers(csrf, 4), json=CONFIG).status_code == 409
    assert (
        client.put(
            f"{path}/bindings/local",
            headers=headers(csrf),
            json={"version_id": v2.json()["id"], "expected_revision": 0},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"{path}/bindings/local",
            headers=headers(csrf),
            json={"version_id": v1.json()["id"], "expected_revision": 0},
        ).status_code
        == 409
    )
    rollback = client.put(
        f"{path}/bindings/local",
        headers=headers(csrf),
        json={"version_id": v1.json()["id"], "expected_revision": 1},
    )
    assert rollback.status_code == 200
    assert rollback.json()["revision"] == 2
    assert (
        client.get(f"{path}/versions/{v1.json()['id']}/export").json()["instructions"] == "Welcome"
    )
    assert (
        client.get(f"{path}/versions/{v2.json()['id']}/export").json()["instructions"]
        == "Welcome back"
    )
    assert "raw-secret" not in client.get(f"{path}/versions/{v1.json()['id']}/export").text
    assert len(client.get(f"{path}/audit").json()) == 7
    with database() as db:
        with pytest.raises(Exception, match="immutable"):
            db.execute(
                text("UPDATE agent_versions SET snapshot='{}' WHERE id=:id"),
                {"id": v1.json()["id"]},
            )
        db.rollback()
    client.cookies.clear()
    viewer = login(client, "viewer@example.com")
    assert client.get(path).status_code == 200
    assert (
        client.post(f"{path}/publish", headers=headers(viewer["csrf_token"], 4)).status_code == 403
    )
    assert (
        client.put(
            f"{path}/bindings/local",
            headers=headers(viewer["csrf_token"]),
            json={"version_id": v2.json()["id"], "expected_revision": 2},
        ).status_code
        == 403
    )


def test_simultaneous_publication_and_activation(
    client: TestClient, database: sessionmaker[Session]
) -> None:
    create_user(database, "operator@example.com", "operator")
    csrf = login(client, "operator@example.com")["csrf_token"]
    created = client.post(
        "/api/agents", headers=headers(csrf), json={"name": "Concurrent", "config": CONFIG}
    ).json()
    path = f"/api/agents/{created['id']}"

    def publish_once() -> int:
        return int(client.post(f"{path}/publish", headers=headers(csrf, 1)).status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: publish_once(), range(2)))
    assert sorted(statuses) == [201, 409]
    versions = client.get(f"{path}/versions").json()
    assert len(versions) == 1
    version_id = versions[0]["id"]

    def activate_once() -> int:
        return int(
            client.put(
                f"{path}/bindings/local",
                headers=headers(csrf),
                json={"version_id": version_id, "expected_revision": 0},
            ).status_code
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: activate_once(), range(2)))
    assert sorted(statuses) == [200, 409]
    assert client.get(f"{path}/bindings").json()[0]["revision"] == 1
