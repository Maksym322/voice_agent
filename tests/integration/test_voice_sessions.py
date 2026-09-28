"""Synthetic room substitutes verify HTTP authorization and pinned sessions."""

import asyncio
from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from test_agents import headers
from test_auth import create_user, login
from voice_fleet_api.agent_schema import AgentConfig
from voice_fleet_api.config import Settings, get_settings
from voice_fleet_api.main import app, sweep_expired_sessions
from voice_fleet_api.models import VoiceSession
from voice_fleet_api.security import now_utc
from voice_fleet_worker import worker


@pytest.mark.parametrize("model", ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite"])
def test_google_llm_uses_its_own_key(monkeypatch: pytest.MonkeyPatch, model: str) -> None:
    monkeypatch.setenv("DEEPGRAM_API_KEY", "synthetic-deepgram")
    monkeypatch.setenv("CARTESIA_API_KEY", "synthetic-cartesia")
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-google")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = AgentConfig.model_validate(
        {
            "instructions": "Help callers",
            "voice": {"llm_provider": "google", "llm_model": model},
        }
    )

    async def construct() -> None:
        session = worker.make_session(config)
        await session.aclose()

    asyncio.run(construct())
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        worker.require_provider_key("GOOGLE_API_KEY", "env:OPENAI_API_KEY")


def test_worker_usage_is_bounded_and_sanitized() -> None:
    class SyntheticUsage:
        def model_dump(self) -> dict[str, object]:
            return {
                "type": "llm_usage",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "input_tokens": 12,
                "output_tokens": 4,
                "audio_duration": float("nan"),
                "api_key": "synthetic-secret",
            }

    safe = worker.safe_usage([SyntheticUsage()])
    assert safe == [
        {
            "type": "llm_usage",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "input_tokens": 12,
            "output_tokens": 4,
        }
    ]
    assert "synthetic-secret" not in str(safe)


def synthetic_settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://localhost/voice_fleet_test_unavailable",
        app_origin="http://localhost:8080",
        livekit_url="ws://synthetic-livekit:7880",
        livekit_browser_url="ws://localhost:7880",
        livekit_api_key="synthetic-key",
        livekit_api_secret="synthetic-secret-at-least-32-characters",
        playground_max_seconds=600,
    )


@pytest.fixture
def room_substitute(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    calls: list[str] = []
    settings = synthetic_settings()
    app.dependency_overrides[get_settings] = lambda: settings

    def open_room(_settings: Settings, room: str, _session_id: UUID) -> None:
        calls.append(f"open:{room}")

    def delete_room(_settings: Settings, room: str) -> None:
        calls.append(f"delete:{room}")

    monkeypatch.setattr("voice_fleet_api.main.open_room", open_room)
    monkeypatch.setattr("voice_fleet_api.main.delete_room", delete_room)
    yield calls
    app.dependency_overrides.pop(get_settings, None)


def publish_and_bind(client: TestClient, csrf: str) -> tuple[str, str]:
    created = client.post(
        "/api/agents",
        headers=headers(csrf),
        json={"name": "Synthetic agent", "config": {"instructions": "Welcome"}},
    )
    assert created.status_code == 201
    agent_id = created.json()["id"]
    published = client.post(f"/api/agents/{agent_id}/publish", headers=headers(csrf, 1))
    assert published.status_code == 201
    version_id = published.json()["id"]
    bound = client.put(
        f"/api/agents/{agent_id}/bindings/local",
        headers=headers(csrf),
        json={"version_id": version_id, "expected_revision": 0},
    )
    assert bound.status_code == 200
    return agent_id, version_id


def test_start_requires_authorization_and_pins_version(
    client: TestClient, database: sessionmaker[Session], room_substitute: list[str]
) -> None:
    create_user(database, "operator@example.com", "operator")
    create_user(database, "viewer@example.com", "viewer")
    operator = login(client, "operator@example.com")
    agent_id, version_id = publish_and_bind(client, operator["csrf_token"])
    path = f"/api/agents/{agent_id}/sessions"
    assert client.post(path).status_code == 403
    started = client.post(path, headers=headers(operator["csrf_token"]))
    assert started.status_code == 201
    first = started.json()
    assert first["version_id"] == version_id
    assert first["url"] == "ws://localhost:7880"
    assert first["token"]
    assert room_substitute[0].startswith("open:vf-")
    assert client.post(path, headers=headers(operator["csrf_token"])).status_code == 409
    with database() as db:
        row = db.scalar(select(VoiceSession).where(VoiceSession.id == UUID(first["id"])))
        assert row is not None and str(row.version_id) == version_id
        assert (row.deadline_at - row.created_at).total_seconds() == 600

    edited = client.put(
        f"/api/agents/{agent_id}/draft",
        headers=headers(operator["csrf_token"], 2),
        json={"name": "Synthetic agent", "config": {"instructions": "New version"}},
    )
    assert edited.status_code == 200
    published = client.post(
        f"/api/agents/{agent_id}/publish", headers=headers(operator["csrf_token"], 3)
    )
    second_version = published.json()["id"]
    assert (
        client.put(
            f"/api/agents/{agent_id}/bindings/local",
            headers=headers(operator["csrf_token"]),
            json={"version_id": second_version, "expected_revision": 1},
        ).status_code
        == 200
    )
    assert client.get(f"/api/sessions/{first['id']}").json()["version_id"] == version_id
    assert client.post(f"/api/sessions/{first['id']}/end").status_code == 403
    ended = client.post(f"/api/sessions/{first['id']}/end", headers=headers(operator["csrf_token"]))
    assert ended.status_code == 200
    assert ended.json()["status"] == "ended"
    assert room_substitute[-1].startswith("delete:vf-")
    next_session = client.post(path, headers=headers(operator["csrf_token"]))
    assert next_session.status_code == 201
    assert next_session.json()["version_id"] == second_version
    client.cookies.clear()
    viewer = login(client, "viewer@example.com")
    assert client.post(path, headers=headers(viewer["csrf_token"])).status_code == 403
    assert client.get(f"/api/sessions/{first['id']}").status_code == 403


def test_room_start_failure_is_recorded_without_issuing_token(
    client: TestClient,
    database: sessionmaker[Session],
    room_substitute: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user(database, "operator@example.com", "operator")
    operator = login(client, "operator@example.com")
    agent_id, _ = publish_and_bind(client, operator["csrf_token"])

    def fail_open(_settings: Settings, _room: str, _id: UUID) -> None:
        raise ConnectionError("synthetic media outage")

    monkeypatch.setattr("voice_fleet_api.main.open_room", fail_open)
    response = client.post(
        f"/api/agents/{agent_id}/sessions", headers=headers(operator["csrf_token"])
    )
    assert response.status_code == 503
    assert "token" not in response.text
    with database() as db:
        row = db.scalar(select(VoiceSession))
        assert row is not None and row.status == "error"
        assert row.error_code == "livekit_unavailable"


def test_expired_room_is_closed_by_server(
    client: TestClient,
    database: sessionmaker[Session],
    room_substitute: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user(database, "operator@example.com", "operator")
    operator = login(client, "operator@example.com")
    agent_id, _ = publish_and_bind(client, operator["csrf_token"])
    response = client.post(
        f"/api/agents/{agent_id}/sessions", headers=headers(operator["csrf_token"])
    )
    assert response.status_code == 201
    voice_id = UUID(response.json()["id"])
    with database.begin() as db:
        voice = db.get(VoiceSession, voice_id)
        assert voice is not None
        voice.deadline_at = now_utc() - timedelta(seconds=1)
    monkeypatch.setattr("voice_fleet_api.main.SessionLocal", database)
    sweep_expired_sessions(synthetic_settings())
    assert room_substitute[-1].startswith("delete:vf-")
    assert client.get(f"/api/sessions/{voice_id}").json()["end_reason"] == "duration_limit"

    second = client.post(
        f"/api/agents/{agent_id}/sessions", headers=headers(operator["csrf_token"])
    )
    assert second.status_code == 201
    second_id = UUID(second.json()["id"])
    with database.begin() as db:
        voice = db.get(VoiceSession, second_id)
        assert voice is not None
        voice.created_at = now_utc() - timedelta(seconds=61)
    sweep_expired_sessions(synthetic_settings())
    timed_out = client.get(f"/api/sessions/{second_id}").json()
    assert timed_out["status"] == "error"
    assert timed_out["error_code"] == "worker_timeout"


def test_worker_uses_pinned_version_and_records_lifecycle(
    client: TestClient,
    database: sessionmaker[Session],
    room_substitute: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user(database, "operator@example.com", "operator")
    operator = login(client, "operator@example.com")
    agent_id, _ = publish_and_bind(client, operator["csrf_token"])
    started = client.post(
        f"/api/agents/{agent_id}/sessions", headers=headers(operator["csrf_token"])
    ).json()
    monkeypatch.setattr(worker, "SessionLocal", database)
    voice_id = UUID(started["id"])
    room = f"vf-{voice_id}"
    pinned = worker.load_pinned(voice_id, room)
    assert pinned.instructions == "Welcome"
    with pytest.raises(ValueError, match="pending room"):
        worker.load_pinned(voice_id, "another-room")
    worker.mark_active(voice_id)
    worker.record_event(
        voice_id,
        "transcript",
        speaker="caller",
        text="Hello",
        details={"final": True},
    )
    worker.record_event(
        voice_id,
        "transcript",
        speaker="agent",
        text="Welcome",
        details={"final": True, "interrupted": False},
        metrics={"last_e2e_latency_ms": 340},
    )
    worker.mark_finished(voice_id, reason="connection_closed")
    detail = client.get(f"/api/sessions/{voice_id}").json()
    events = client.get(f"/api/sessions/{voice_id}/events").json()
    assert detail["status"] == "ended"
    assert detail["metrics"]["last_e2e_latency_ms"] == 340
    assert [event["kind"] for event in events] == ["connected", "transcript", "transcript", "ended"]
    assert events[2]["speaker"] == "agent"
    with pytest.raises(ValueError, match="pending room"):
        worker.load_pinned(voice_id, room)


def test_logout_closes_room_before_revoking_authentication(
    client: TestClient, database: sessionmaker[Session], room_substitute: list[str]
) -> None:
    create_user(database, "operator@example.com", "operator")
    operator = login(client, "operator@example.com")
    agent_id, _ = publish_and_bind(client, operator["csrf_token"])
    started = client.post(
        f"/api/agents/{agent_id}/sessions", headers=headers(operator["csrf_token"])
    ).json()
    assert (
        client.post("/api/auth/logout", headers=headers(operator["csrf_token"])).status_code == 204
    )
    assert room_substitute[-1].startswith("delete:vf-")
    with database() as db:
        row = db.get(VoiceSession, UUID(started["id"]))
        assert row is not None and row.status == "ended" and row.end_reason == "sign_out"
    assert client.get(f"/api/sessions/{started['id']}").status_code == 401


def test_outbound_test_is_admin_only_pinned_and_destination_limited(
    client: TestClient,
    database: sessionmaker[Session],
    room_substitute: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user(database, "admin@example.com", "admin")
    create_user(database, "operator@example.com", "operator")
    admin = login(client, "admin@example.com")
    agent_id, version_id = publish_and_bind(client, admin["csrf_token"])
    settings = synthetic_settings().model_copy(
        update={
            "outbound_sip_trunk_id": "ST-synthetic",
            "outbound_test_destination": "+380501234567",
            "outbound_test_max_seconds": 180,
        }
    )
    app.dependency_overrides[get_settings] = lambda: settings
    calls: list[str] = []

    def dial(_settings: Settings, room: str, _session_id: UUID) -> str:
        calls.append(room)
        return "synthetic-provider-call"

    monkeypatch.setattr("voice_fleet_api.main.dial_outbound", dial)
    path = f"/api/agents/{agent_id}/outbound-test"
    assert client.post(path).status_code == 403
    client.cookies.clear()
    operator = login(client, "operator@example.com")
    assert client.post(path, headers=headers(operator["csrf_token"])).status_code == 403
    client.cookies.clear()
    admin = login(client, "admin@example.com")
    started = client.post(path, headers=headers(admin["csrf_token"]))
    assert started.status_code == 201
    assert started.json()["channel"] == "phone"
    assert started.json()["version_id"] == version_id
    assert started.json()["destination_masked"] == "••••4567"
    assert "501234567" not in started.text
    assert len(calls) == 1
    assert client.post(path, headers=headers(admin["csrf_token"])).status_code == 409
    with database() as db:
        row = db.get(VoiceSession, UUID(started.json()["id"]))
        assert row is not None
        assert row.provider_call_id == "synthetic-provider-call"
        assert row.destination_last4 == "4567"
        assert (row.deadline_at - row.created_at).total_seconds() == 180
    ended = client.post(
        f"/api/sessions/{started.json()['id']}/end", headers=headers(admin["csrf_token"])
    )
    assert ended.status_code == 200
    assert room_substitute[-1].startswith("delete:vf-")


def test_failed_outbound_test_records_error_and_closes_room(
    client: TestClient,
    database: sessionmaker[Session],
    room_substitute: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user(database, "admin@example.com", "admin")
    admin = login(client, "admin@example.com")
    agent_id, _ = publish_and_bind(client, admin["csrf_token"])
    settings = synthetic_settings().model_copy(
        update={
            "outbound_sip_trunk_id": "ST-synthetic",
            "outbound_test_destination": "+380501234567",
        }
    )
    app.dependency_overrides[get_settings] = lambda: settings

    def fail_dial(_settings: Settings, _room: str, _session_id: UUID) -> str:
        raise ConnectionError("synthetic private carrier diagnostic")

    monkeypatch.setattr("voice_fleet_api.main.dial_outbound", fail_dial)
    response = client.post(
        f"/api/agents/{agent_id}/outbound-test", headers=headers(admin["csrf_token"])
    )
    assert response.status_code == 503
    assert "synthetic private carrier diagnostic" not in response.text
    assert room_substitute[-1].startswith("delete:vf-")
    with database() as db:
        row = db.scalar(select(VoiceSession))
        assert row is not None and row.status == "error"
        assert row.error_code == "outbound_call_failed"
        assert row.room_cleanup_pending is False
