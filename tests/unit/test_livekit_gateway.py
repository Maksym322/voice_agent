"""Check that browser credentials cannot administer rooms or publish other media."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from livekit import api
from pydantic import ValidationError
from voice_fleet_api import livekit_gateway
from voice_fleet_api.config import Settings
from voice_fleet_api.livekit_gateway import browser_token


def test_browser_token_is_short_lived_and_room_scoped() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/voice_fleet_test_unavailable",
        app_origin="http://localhost:8080",
        livekit_url="ws://localhost:7880",
        livekit_browser_url="ws://localhost:7880",
        livekit_api_key="synthetic-key",
        livekit_api_secret="synthetic-secret-at-least-32-characters",
    )
    assert settings.livekit_api_secret is not None
    claims = jwt.decode(
        browser_token(settings, "vf-one-room", uuid4(), uuid4()),
        settings.livekit_api_secret,
        algorithms=["HS256"],
    )
    assert claims["exp"] - claims["nbf"] == 300
    assert claims["video"] == {
        "roomJoin": True,
        "room": "vf-one-room",
        "canPublish": True,
        "canSubscribe": True,
        "canPublishData": False,
        "canPublishSources": ["microphone"],
    }


def test_outbound_sip_request_uses_only_configured_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/voice_fleet_test_unavailable",
        app_origin="http://localhost:8080",
        livekit_url="ws://localhost:7880",
        livekit_browser_url="ws://localhost:7880",
        livekit_api_key="synthetic-key",
        livekit_api_secret="synthetic-secret-at-least-32-characters",
        outbound_sip_trunk_id="ST-synthetic",
        outbound_test_destination="+380501234567",
        outbound_test_max_seconds=180,
    )
    seen: list[tuple[api.CreateSIPParticipantRequest, float]] = []

    class FakeSip:
        async def create_sip_participant(
            self, request: api.CreateSIPParticipantRequest, *, timeout: float
        ) -> object:
            seen.append((request, timeout))
            return SimpleNamespace(sip_call_id="synthetic-call")

    class FakeLiveKit:
        sip = FakeSip()

        async def __aenter__(self) -> "FakeLiveKit":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(api, "LiveKitAPI", lambda **_kwargs: FakeLiveKit())
    session_id = uuid4()
    result = asyncio.run(livekit_gateway._dial_outbound(settings, "vf-test", session_id))
    assert result == "synthetic-call"
    request, timeout = seen[0]
    assert timeout == 35
    assert request.sip_trunk_id == "ST-synthetic"
    assert request.sip_call_to == "+380501234567"
    assert request.participant_identity == f"sip-{session_id}"
    assert request.wait_until_answered is True
    assert request.ringing_timeout.seconds == 25
    assert request.max_call_duration.seconds == 180


def test_outbound_destination_must_be_ukrainian_e164() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg://localhost/voice_fleet_test_unavailable",
            app_origin="http://localhost:8080",
            outbound_test_destination="+14155550100",
        )


def test_inbound_route_is_scoped_to_one_number_and_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/voice_fleet_test_unavailable",
        app_origin="http://localhost:8080",
        livekit_url="ws://localhost:7880",
        livekit_browser_url="ws://localhost:7880",
        livekit_api_key="synthetic-key",
        livekit_api_secret="synthetic-secret-at-least-32-characters",
        inbound_sip_allowed_addresses="192.0.2.0/24",
    )
    seen: list[object] = []

    class FakeSip:
        async def create_sip_inbound_trunk(self, request: object) -> object:
            seen.append(request)
            return SimpleNamespace(sip_trunk_id="ST-synthetic")

        async def create_sip_dispatch_rule(self, request: object) -> object:
            seen.append(request)
            return SimpleNamespace(sip_dispatch_rule_id="SDR-synthetic")

    class FakeLiveKit:
        sip = FakeSip()

        async def __aenter__(self) -> "FakeLiveKit":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(api, "LiveKitAPI", lambda **_kwargs: FakeLiveKit())
    number_id = uuid4()
    assert asyncio.run(livekit_gateway._provision_inbound(settings, number_id, "+15551234567")) == (
        "ST-synthetic",
        "SDR-synthetic",
    )
    trunk_request = seen[0]
    rule_request = seen[1]
    assert isinstance(trunk_request, api.CreateSIPInboundTrunkRequest)
    assert isinstance(rule_request, api.CreateSIPDispatchRuleRequest)
    trunk = trunk_request.trunk
    rule = rule_request.dispatch_rule
    assert list(trunk.numbers) == ["+15551234567"]
    assert list(trunk.allowed_addresses) == ["192.0.2.0/24"]
    assert list(rule.trunk_ids) == ["ST-synthetic"]
    assert rule.rule.dispatch_rule_individual.room_prefix == f"vf-in-{number_id}-"
    assert json.loads(rule.room_config.agents[0].metadata) == {"phone_number_id": str(number_id)}


def test_inbound_route_requires_carrier_address_allowlist() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/voice_fleet_test_unavailable",
        app_origin="http://localhost:8080",
        livekit_url="ws://localhost:7880",
        livekit_browser_url="ws://localhost:7880",
        livekit_api_key="synthetic-key",
        livekit_api_secret="synthetic-secret-at-least-32-characters",
    )
    with pytest.raises(RuntimeError, match="carrier SIP addresses"):
        asyncio.run(livekit_gateway._provision_inbound(settings, uuid4(), "+15551234567"))


def test_inbound_route_rejects_open_internet_allowlist() -> None:
    with pytest.raises(ValidationError, match="whole internet"):
        Settings(
            database_url="postgresql+psycopg://localhost/voice_fleet_test_unavailable",
            app_origin="http://localhost:8080",
            inbound_sip_allowed_addresses="0.0.0.0/0",
        )


def test_inbound_cleanup_can_retry_after_rule_was_deleted(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/voice_fleet_test_unavailable",
        app_origin="http://localhost:8080",
        livekit_url="ws://localhost:7880",
        livekit_browser_url="ws://localhost:7880",
        livekit_api_key="synthetic-key",
        livekit_api_secret="synthetic-secret-at-least-32-characters",
    )
    removed: list[str] = []

    class FakeSip:
        async def delete_sip_dispatch_rule(self, request: object) -> None:
            removed.append("rule")
            raise api.TwirpError("not_found", "already removed", status=404)

        async def delete_sip_trunk(self, request: object) -> None:
            removed.append("trunk")

    class FakeLiveKit:
        sip = FakeSip()

        async def __aenter__(self) -> "FakeLiveKit":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(api, "LiveKitAPI", lambda **_kwargs: FakeLiveKit())
    asyncio.run(livekit_gateway._remove_inbound(settings, "ST-one", "SDR-one"))
    assert removed == ["rule", "trunk"]
