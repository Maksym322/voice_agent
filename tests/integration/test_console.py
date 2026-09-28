"""Synthetic console contract checks against disposable PostgreSQL."""

from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from test_agents import headers
from test_auth import create_user, login
from test_voice_sessions import publish_and_bind, synthetic_settings
from voice_fleet_api.config import Settings, get_settings
from voice_fleet_api.main import app, purge_retained_sessions, sweep_expired_sessions
from voice_fleet_api.models import VoiceSession
from voice_fleet_worker import worker


@pytest.fixture
def room_substitute(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    calls: list[str] = []
    app.dependency_overrides[get_settings] = synthetic_settings

    def open_room(_settings: Settings, room: str, _session_id: UUID) -> None:
        calls.append(f"open:{room}")

    def delete_room(_settings: Settings, room: str) -> None:
        calls.append(f"delete:{room}")

    monkeypatch.setattr("voice_fleet_api.main.open_room", open_room)
    monkeypatch.setattr("voice_fleet_api.main.delete_room", delete_room)
    yield calls
    app.dependency_overrides.pop(get_settings, None)


def test_two_sessions_one_agent_have_distinct_cards_and_access(
    client: TestClient,
    database: sessionmaker[Session],
    room_substitute: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user(database, "one@example.com", "operator")
    create_user(database, "two@example.com", "operator")
    create_user(database, "admin@example.com", "admin")
    create_user(database, "viewer@example.com", "viewer")
    one = login(client, "one@example.com")
    agent_id, _ = publish_and_bind(client, one["csrf_token"])
    path = f"/api/agents/{agent_id}/sessions"
    first = client.post(path, headers=headers(one["csrf_token"])).json()
    two = login(client, "two@example.com")
    second = client.post(path, headers=headers(two["csrf_token"])).json()
    assert first["id"] != second["id"]
    assert first["agent_id"] == second["agent_id"]
    own = client.get("/api/console/sessions?scope=board").json()["items"]
    assert [item["id"] for item in own] == [second["id"]]
    assert client.get(f"/api/sessions/{first['id']}").status_code == 404

    monkeypatch.setattr(worker, "SessionLocal", database)
    worker.mark_active(UUID(first["id"]))
    worker.record_event(UUID(first["id"]), "transcript", speaker="caller", text="First only")
    worker.mark_finished(
        UUID(first["id"]), error_code="provider_unavailable", reason="provider_error"
    )
    assert client.get(f"/api/sessions/{first['id']}/events").status_code == 404
    assert client.get(f"/api/console/logs?session_id={first['id']}").json()["items"] == []

    admin = login(client, "admin@example.com")
    board = client.get("/api/console/sessions?scope=board").json()["items"]
    assert {item["id"] for item in board} == {first["id"], second["id"]}
    assert {item["status"] for item in board} == {"error", "pending"}
    assert (
        client.get(f"/api/console/sessions?scope=history&session_id={first['id']}").json()["items"][
            0
        ]["id"]
        == first["id"]
    )
    logs = client.get(f"/api/console/logs?session_id={first['id']}&severity=error").json()["items"]
    assert len(logs) == 1 and logs[0]["code"] == "provider_unavailable"
    assert "First only" not in str(logs)
    assert client.get("/api/console/sessions?scope=history&status=invalid").status_code == 422
    assert client.get("/api/console/sessions?cursor=bad").status_code == 422

    viewer = login(client, "viewer@example.com")
    assert client.get("/api/console/sessions").status_code == 403
    assert client.get("/api/console/logs").status_code == 403
    assert client.get("/api/console/view").status_code == 403
    assert (
        client.put("/api/console/view", headers=headers(viewer["csrf_token"]), json={}).status_code
        == 403
    )
    assert admin["role"] == "admin"


def test_history_cursor_and_private_saved_view(
    client: TestClient, database: sessionmaker[Session], room_substitute: list[str]
) -> None:
    create_user(database, "one@example.com", "operator")
    create_user(database, "two@example.com", "operator")
    one = login(client, "one@example.com")
    agent_id, _ = publish_and_bind(client, one["csrf_token"])
    for _ in range(3):
        started = client.post(
            f"/api/agents/{agent_id}/sessions", headers=headers(one["csrf_token"])
        ).json()
        client.post(f"/api/sessions/{started['id']}/end", headers=headers(one["csrf_token"]))
    page = client.get("/api/console/sessions?scope=history&limit=2").json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    next_page = client.get(
        f"/api/console/sessions?scope=history&limit=2&cursor={page['next_cursor']}"
    ).json()
    assert len(next_page["items"]) == 1
    assert {item["id"] for item in page["items"]}.isdisjoint(
        {item["id"] for item in next_page["items"]}
    )
    view = client.get("/api/console/view").json()
    view["group_order"] = ["active", "pending", "ended", "error"]
    assert client.put("/api/console/view", json=view).status_code == 403
    saved = client.put("/api/console/view", headers=headers(one["csrf_token"]), json=view)
    assert saved.status_code == 200
    assert client.get("/api/console/view").json()["group_order"] == view["group_order"]
    login(client, "two@example.com")
    assert client.get("/api/console/view").json()["group_order"] != view["group_order"]


def test_retention_removes_session_and_diagnostics(
    client: TestClient,
    database: sessionmaker[Session],
    room_substitute: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user(database, "one@example.com", "operator")
    one = login(client, "one@example.com")
    created = client.post(
        "/api/agents",
        headers=headers(one["csrf_token"]),
        json={"name": "Zero retention", "config": {"instructions": "Hello", "retention_days": 0}},
    ).json()
    published = client.post(
        f"/api/agents/{created['id']}/publish", headers=headers(one["csrf_token"], 1)
    ).json()
    client.put(
        f"/api/agents/{created['id']}/bindings/local",
        headers=headers(one["csrf_token"]),
        json={"version_id": published["id"], "expected_revision": 0},
    )
    started = client.post(
        f"/api/agents/{created['id']}/sessions", headers=headers(one["csrf_token"])
    ).json()
    monkeypatch.setattr(worker, "SessionLocal", database)
    worker.mark_finished(
        UUID(started["id"]), error_code="provider_unavailable", reason="provider_error"
    )
    monkeypatch.setattr("voice_fleet_api.main.SessionLocal", database)
    sweep_expired_sessions(synthetic_settings())
    assert room_substitute[-1].startswith("delete:vf-")
    purge_retained_sessions()
    with database() as db:
        assert db.scalar(select(VoiceSession).where(VoiceSession.id == UUID(started["id"]))) is None
    assert client.get(f"/api/sessions/{started['id']}").status_code == 404
    assert client.get(f"/api/console/logs?session_id={started['id']}").json()["items"] == []
