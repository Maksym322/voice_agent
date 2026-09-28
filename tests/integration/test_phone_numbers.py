"""Synthetic provider checks for number authorization, routing, and per-call pinning."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from test_agents import headers
from test_auth import create_user, login
from test_voice_sessions import publish_and_bind, synthetic_settings
from voice_fleet_api.config import get_settings
from voice_fleet_api.main import app
from voice_fleet_api.models import VoiceSession
from voice_fleet_worker import worker


def test_inbound_number_route_and_distinct_session_ids(
    client: TestClient,
    database: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = synthetic_settings().model_copy(
        update={"inbound_sip_allowed_addresses": "192.0.2.0/24"}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(
        "voice_fleet_api.main.provision_inbound", lambda *_args: ("ST-one", "SDR-one")
    )
    monkeypatch.setattr(worker, "SessionLocal", database)
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    try:
        create_user(database, "number-admin@example.com", "admin")
        create_user(database, "number-operator@example.com", "operator")
        admin = login(client, "number-admin@example.com")
        agent_id, version_id = publish_and_bind(client, admin["csrf_token"])
        body = {
            "e164": "+15551234567",
            "provider": "synthetic_carrier",
            "route_agent_id": agent_id,
        }
        assert client.post("/api/phone-numbers", json=body).status_code == 403
        created = client.post("/api/phone-numbers", headers=headers(admin["csrf_token"]), json=body)
        assert created.status_code == 201
        number = created.json()
        assert number["e164_masked"] == "••••4567"
        assert number["carrier_verified"] is False
        assert "sip_trunk_id" not in number
        assert len(client.get("/api/phone-numbers").json()) == 1
        room_one = f"vf-in-{number['id']}-first"
        room_two = f"vf-in-{number['id']}-second"
        first_id, _, trunk_id, rule_id, e164 = worker.create_inbound_session(
            UUID(number["id"]), room_one
        )
        second_id, _, _, _, _ = worker.create_inbound_session(UUID(number["id"]), room_two)
        assert first_id != second_id
        assert (trunk_id, rule_id, e164) == ("ST-one", "SDR-one", "+15551234567")
        with database() as db:
            first = db.get(VoiceSession, first_id)
            second = db.get(VoiceSession, second_id)
            assert first is not None and second is not None
            assert first.version_id == second.version_id == UUID(version_id)
            assert first.started_by is None and second.started_by is None
            assert first.direction == second.direction == "inbound"
        changed = client.put(
            f"/api/phone-numbers/{number['id']}/route",
            headers=headers(admin["csrf_token"]),
            json={"route_agent_id": agent_id, "expected_revision": 1},
        )
        assert changed.status_code == 200
        assert changed.json()["revision"] == 2
        assert (
            client.put(
                f"/api/phone-numbers/{number['id']}/route",
                headers=headers(admin["csrf_token"]),
                json={"route_agent_id": agent_id, "expected_revision": 1},
            ).status_code
            == 409
        )
        login(client, "number-operator@example.com")
        assert client.get("/api/phone-numbers").status_code == 403
        assert client.get(f"/api/sessions/{first_id}").status_code == 404
    finally:
        app.dependency_overrides.pop(get_settings, None)
