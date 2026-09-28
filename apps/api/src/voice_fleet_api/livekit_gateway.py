"""Small LiveKit boundary for room control and scoped browser credentials."""

import asyncio
import json
import logging
from datetime import timedelta
from uuid import UUID

from google.protobuf.duration_pb2 import Duration
from livekit import api

from voice_fleet_api.config import Settings

WORKER_NAME = "voice-fleet-playground"
logger = logging.getLogger(__name__)


def require_livekit(settings: Settings) -> tuple[str, str, str, str]:
    values = (
        settings.livekit_url,
        settings.livekit_browser_url,
        settings.livekit_api_key,
        settings.livekit_api_secret,
    )
    if not all(values):
        raise RuntimeError("LiveKit is not configured")
    url, browser_url, key, secret = values
    assert url is not None and browser_url is not None and key is not None and secret is not None
    if not url.startswith(("ws://", "wss://")) or not browser_url.startswith(("ws://", "wss://")):
        raise RuntimeError("LiveKit URLs must use ws:// or wss://")
    if settings.environment == "production" and not browser_url.startswith("wss://"):
        raise RuntimeError("Production browser LiveKit URL must use wss://")
    return url, browser_url, key, secret


async def _open_room(settings: Settings, room: str, session_id: UUID) -> None:
    url, _, key, secret = require_livekit(settings)
    async with api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as client:
        await client.room.create_room(
            api.CreateRoomRequest(name=room, empty_timeout=30, max_participants=2)
        )
        try:
            await client.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=WORKER_NAME,
                    room=room,
                    metadata=json.dumps({"session_id": str(session_id)}),
                )
            )
        except Exception:
            await client.room.delete_room(api.DeleteRoomRequest(room=room))
            raise


def open_room(settings: Settings, room: str, session_id: UUID) -> None:
    asyncio.run(_open_room(settings, room, session_id))


async def _dial_outbound(settings: Settings, room: str, session_id: UUID) -> str:
    url, _, key, secret = require_livekit(settings)
    if not settings.outbound_sip_trunk_id or not settings.outbound_test_destination:
        raise RuntimeError("Outbound test is not configured")
    async with api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as client:
        participant = await client.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=settings.outbound_sip_trunk_id,
                sip_call_to=settings.outbound_test_destination,
                room_name=room,
                participant_identity=f"sip-{session_id}",
                participant_name="Phone caller",
                wait_until_answered=True,
                ringing_timeout=Duration(seconds=25),
                max_call_duration=Duration(seconds=settings.outbound_test_max_seconds),
            ),
            timeout=35,
        )
    return participant.sip_call_id


def dial_outbound(settings: Settings, room: str, session_id: UUID) -> str:
    return asyncio.run(_dial_outbound(settings, room, session_id))


async def _provision_inbound(settings: Settings, number_id: UUID, e164: str) -> tuple[str, str]:
    """Create one number-scoped trunk and one individual-room dispatch rule."""
    url, _, key, secret = require_livekit(settings)
    if not settings.inbound_sip_allowed_addresses:
        raise RuntimeError("Inbound carrier SIP addresses are not configured")
    allowed_addresses = [
        address.strip() for address in settings.inbound_sip_allowed_addresses.split(",")
    ]
    trunk_id: str | None = None
    async with api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as client:
        try:
            trunk = await client.sip.create_sip_inbound_trunk(
                api.CreateSIPInboundTrunkRequest(
                    trunk=api.SIPInboundTrunkInfo(
                        name=f"Voice Fleet {e164}",
                        numbers=[e164],
                        allowed_addresses=allowed_addresses,
                    )
                )
            )
            trunk_id = trunk.sip_trunk_id
            rule = await client.sip.create_sip_dispatch_rule(
                api.CreateSIPDispatchRuleRequest(
                    dispatch_rule=api.SIPDispatchRuleInfo(
                        name=f"Voice Fleet {e164}",
                        trunk_ids=[trunk_id],
                        rule=api.SIPDispatchRule(
                            dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                                room_prefix=f"vf-in-{number_id}-"
                            )
                        ),
                        room_config=api.RoomConfiguration(
                            max_participants=2,
                            agents=[
                                api.RoomAgentDispatch(
                                    agent_name=WORKER_NAME,
                                    metadata=json.dumps({"phone_number_id": str(number_id)}),
                                )
                            ],
                        ),
                    )
                )
            )
            return trunk_id, rule.sip_dispatch_rule_id
        except Exception:
            if trunk_id is not None:
                try:
                    await client.sip.delete_sip_trunk(
                        api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id)
                    )
                except Exception:
                    logger.exception("Could not roll back inbound LiveKit trunk %s", trunk_id)
            raise


def provision_inbound(settings: Settings, number_id: UUID, e164: str) -> tuple[str, str]:
    return asyncio.run(_provision_inbound(settings, number_id, e164))


async def _remove_inbound(settings: Settings, trunk_id: str, rule_id: str) -> None:
    url, _, key, secret = require_livekit(settings)
    async with api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as client:
        await client.sip.delete_sip_dispatch_rule(
            api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
        )
        await client.sip.delete_sip_trunk(api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id))


def remove_inbound(settings: Settings, trunk_id: str, rule_id: str) -> None:
    asyncio.run(_remove_inbound(settings, trunk_id, rule_id))


async def _delete_room(settings: Settings, room: str) -> None:
    url, _, key, secret = require_livekit(settings)
    async with api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as client:
        try:
            await client.room.delete_room(api.DeleteRoomRequest(room=room))
        except api.TwirpError as exc:
            if exc.status != 404:
                raise


def delete_room(settings: Settings, room: str) -> None:
    asyncio.run(_delete_room(settings, room))


def browser_token(settings: Settings, room: str, user_id: UUID, session_id: UUID) -> str:
    _, _, key, secret = require_livekit(settings)
    return (
        api.AccessToken(key, secret)
        .with_identity(f"browser-{user_id}-{session_id}")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish_sources=["microphone"],
                can_subscribe=True,
                can_publish_data=False,
            )
        )
        .with_ttl(timedelta(minutes=5))
        .to_jwt()
    )
