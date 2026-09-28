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
        assert (
            client.post(
                f"/api/phone-numbers/{number['id']}/deactivate",
                headers=headers(admin["csrf_token"]),
                json={"expected_revision": 2},
            ).status_code
            == 409
        )
        with database.begin() as db:
            first = db.get(VoiceSession, first_id)
            second = db.get(VoiceSession, second_id)
            assert first is not None and second is not None
            first.status = second.status = "ended"

        attempts = 0

        def remove_synthetic(*_args: object) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("synthetic provider outage")

        monkeypatch.setattr("voice_fleet_api.main.remove_inbound", remove_synthetic)
        deactivate_url = f"/api/phone-numbers/{number['id']}/deactivate"
        failed = client.post(
            deactivate_url,
            headers=headers(admin["csrf_token"]),
            json={"expected_revision": 2},
        )
        assert failed.status_code == 503
        deprovisioning = client.get("/api/phone-numbers").json()[0]
        assert deprovisioning["status"] == "deprovisioning"
        assert deprovisioning["livekit_configured"] is False
        with pytest.raises(ValueError, match="configured number"):
            worker.create_inbound_session(UUID(number["id"]), f"vf-in-{number['id']}-blocked")
        retired = client.post(
            deactivate_url,
            headers=headers(admin["csrf_token"]),
            json={"expected_revision": deprovisioning["revision"]},
        )
        assert retired.status_code == 200
        assert retired.json()["status"] == "retired"
        assert attempts == 2
        assert (
            client.post(
                f"/api/phone-numbers/{number['id']}/reactivate",
                headers=headers(admin["csrf_token"]),
                json={"expected_revision": retired.json()["revision"], "provider": "Bad Carrier"},
            ).status_code
            == 422
        )
        reactivated = client.post(
            f"/api/phone-numbers/{number['id']}/reactivate",
            headers=headers(admin["csrf_token"]),
            json={
                "expected_revision": retired.json()["revision"],
                "provider": "synthetic_new_carrier",
            },
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["status"] == "active"
        assert reactivated.json()["provider"] == "synthetic_new_carrier"
        third_id, _, _, _, _ = worker.create_inbound_session(
            UUID(number["id"]), f"vf-in-{number['id']}-third"
        )
        assert third_id not in (first_id, second_id)
        with database() as db:
            first = db.get(VoiceSession, first_id)
            assert first is not None and first.phone_number_id == UUID(number["id"])
        operator = login(client, "number-operator@example.com")
        assert client.get("/api/phone-numbers").status_code == 403
        assert (
            client.post(
                deactivate_url,
                headers=headers(operator["csrf_token"]),
                json={"expected_revision": reactivated.json()["revision"]},
            ).status_code
            == 403
        )
        assert client.get(f"/api/sessions/{first_id}").status_code == 404
    finally:
        app.dependency_overrides.pop(get_settings, None)
