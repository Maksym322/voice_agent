"""Registered LiveKit voice worker for pinned browser sessions."""

import asyncio
import json
import logging
import math
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext
from livekit.plugins import cartesia, deepgram, google, openai
from sqlalchemy import select
from voice_fleet_api.agent_schema import AgentConfig
from voice_fleet_api.config import get_settings
from voice_fleet_api.db import SessionLocal
from voice_fleet_api.livekit_gateway import WORKER_NAME, delete_room
from voice_fleet_api.models import (
    AgentVersion,
    DeploymentBinding,
    PhoneNumber,
    SessionDiagnostic,
    SessionEvent,
    VoiceSession,
)

logger = logging.getLogger(__name__)
server = AgentServer()


def load_pinned(session_id: UUID, room_name: str) -> AgentConfig:
    """Never trust dispatch metadata as configuration or authority."""
    with SessionLocal() as db:
        voice = db.scalar(select(VoiceSession).where(VoiceSession.id == session_id))
        if (
            voice is None
            or voice.room_name != room_name
            or voice.status != "pending"
            or voice.deadline_at <= datetime.now(UTC)
        ):
            raise ValueError("Dispatch does not identify a pending room")
        version = db.get(AgentVersion, voice.version_id)
        if version is None or version.agent_id != voice.agent_id:
            raise ValueError("Pinned version is unavailable")
        return AgentConfig.model_validate(version.snapshot)


def session_channel(session_id: UUID) -> str:
    with SessionLocal() as db:
        voice = db.get(VoiceSession, session_id)
        if voice is None:
            raise ValueError("Session is unavailable")
        return voice.channel


def create_inbound_session(
    number_id: UUID, room_name: str
) -> tuple[UUID, AgentConfig, str, str, str]:
    """Resolve the current route once; each call pins its own published version."""
    settings = get_settings()
    with SessionLocal.begin() as db:
        number = db.get(PhoneNumber, number_id, with_for_update=True)
        if (
            number is None
            or number.status != "active"
            or not room_name.startswith(f"vf-in-{number_id}-")
        ):
            raise ValueError("Inbound dispatch does not match a configured number")
        binding = db.scalar(
            select(DeploymentBinding).where(
                DeploymentBinding.agent_id == number.route_agent_id,
                DeploymentBinding.environment == settings.environment,
            )
        )
        if binding is None:
            raise ValueError("Inbound route has no active agent")
        version = db.get(AgentVersion, binding.version_id)
        if version is None or version.agent_id != number.route_agent_id:
            raise ValueError("Inbound route has no published version")
        config = AgentConfig.model_validate(version.snapshot)
        started = datetime.now(UTC)
        session_id = uuid4()
        db.add(
            VoiceSession(
                id=session_id,
                agent_id=number.route_agent_id,
                version_id=version.id,
                started_by=None,
                room_name=room_name,
                channel="phone",
                direction="inbound",
                phone_number_id=number_id,
                status="pending",
                created_at=started,
                deadline_at=started
                + timedelta(
                    seconds=min(config.session_limit_seconds, settings.playground_max_seconds)
                ),
                metrics={},
            )
        )
        db.flush()
        db.add(
            SessionEvent(
                session_id=session_id,
                kind="inbound_dispatched",
                source="voice-worker",
                details={"phone_number_id": str(number_id)},
                created_at=started,
            )
        )
        return session_id, config, number.sip_trunk_id, number.dispatch_rule_id, number.e164


def record_inbound_caller(session_id: UUID, participant: object) -> None:
    attributes = getattr(participant, "attributes", {})
    with SessionLocal.begin() as db:
        voice = db.get(VoiceSession, session_id, with_for_update=True)
        if voice is None or voice.status != "pending":
            raise ValueError("Inbound session is closed")
        call_id = attributes.get("sip.callID") or attributes.get("sip.callIDFull")
        caller = attributes.get("sip.phoneNumber")
        voice.provider_call_id = str(call_id)[:128] if call_id else None
        if caller:
            voice.destination_last4 = str(caller)[-4:]


def is_expected_sip_participant(
    participant: object,
    session_id: UUID,
    direction: str,
    inbound_expected: tuple[str, str, str] | None,
) -> bool:
    if getattr(participant, "kind", None) != rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        return False
    if direction == "outbound":
        return getattr(participant, "identity", None) == f"sip-{session_id}"
    if direction != "inbound" or inbound_expected is None:
        return False
    attributes = getattr(participant, "attributes", {})
    trunk_id, rule_id, e164 = inbound_expected
    return (
        attributes.get("sip.trunkID") == trunk_id
        and attributes.get("sip.ruleID") == rule_id
        and attributes.get("sip.trunkPhoneNumber") == e164
    )


def record_event(
    session_id: UUID,
    kind: str,
    *,
    speaker: str | None = None,
    text: str | None = None,
    details: dict[str, object] | None = None,
    metrics: dict[str, object] | None = None,
) -> None:
    """Write bounded product events; full diagnostics stay in structured stdout."""
    with SessionLocal.begin() as db:
        voice = db.get(VoiceSession, session_id, with_for_update=True)
        if voice is None or voice.status not in ("pending", "active"):
            return
        if metrics:
            voice.metrics = {**voice.metrics, **metrics}
        db.add(
            SessionEvent(
                session_id=session_id,
                kind=kind,
                source="voice-worker",
                speaker=speaker,
                text=text[:20000] if text else None,
                details=details or {},
                created_at=datetime.now(UTC),
            )
        )


def mark_active(session_id: UUID) -> None:
    with SessionLocal.begin() as db:
        voice = db.get(VoiceSession, session_id, with_for_update=True)
        if voice is None or voice.status != "pending":
            raise ValueError("Session closed before the worker was ready")
        voice.status = "active"
        voice.connected_at = datetime.now(UTC)
        db.add(
            SessionEvent(
                session_id=session_id,
                kind="connected",
                source="voice-worker",
                details={"source": "voice-worker"},
                created_at=voice.connected_at,
            )
        )


def mark_finished(session_id: UUID, *, error_code: str | None = None, reason: str) -> None:
    with SessionLocal.begin() as db:
        voice = db.get(VoiceSession, session_id, with_for_update=True)
        if voice is None or voice.status not in ("pending", "active"):
            return
        voice.status = "error" if error_code else "ended"
        voice.error_code = error_code
        voice.end_reason = reason
        voice.ended_at = datetime.now(UTC)
        voice.room_cleanup_pending = True
        db.add(
            SessionEvent(
                session_id=session_id,
                kind="error" if error_code else "ended",
                source="voice-worker",
                details={"reason": reason, **({"code": error_code} if error_code else {})},
                created_at=voice.ended_at,
            )
        )
        if error_code:
            db.add(
                SessionDiagnostic(
                    session_id=session_id,
                    severity="error",
                    component="voice-worker",
                    code=error_code,
                    message="Voice provider or worker failed; room cleanup was requested.",
                    created_at=voice.ended_at,
                )
            )


def mark_room_cleaned(session_id: UUID) -> None:
    with SessionLocal.begin() as db:
        voice = db.get(VoiceSession, session_id, with_for_update=True)
        if voice is not None:
            voice.room_cleanup_pending = False


def safe_usage(model_usage: object) -> list[dict[str, object]]:
    if not isinstance(model_usage, list):
        return []
    fields = (
        "input_tokens",
        "output_tokens",
        "input_cached_tokens",
        "characters_count",
        "audio_duration",
        "session_duration",
    )
    models: list[dict[str, object]] = []
    for item in model_usage[:10]:
        if not hasattr(item, "model_dump"):
            continue
        raw = item.model_dump()
        numeric = {
            key: value
            for key in fields
            if isinstance((value := raw.get(key)), int | float)
            and math.isfinite(value)
            and value >= 0
        }
        models.append(
            {
                "type": str(raw.get("type", ""))[:32],
                "provider": str(raw.get("provider", ""))[:64],
                "model": str(raw.get("model", ""))[:128],
                **numeric,
            }
        )
    return models


def response_latency(
    item_metrics: object, final_transcript_at: float | None
) -> tuple[str, int] | None:
    """Prefer LiveKit's speech-end latency, otherwise measure from final STT text."""
    if not isinstance(item_metrics, dict):
        return None
    direct = item_metrics.get("e2e_latency")
    if isinstance(direct, int | float) and not isinstance(direct, bool):
        if math.isfinite(direct) and direct >= 0:
            return "e2e_latency_ms", round(direct * 1000)
    started = item_metrics.get("started_speaking_at")
    if (
        isinstance(started, int | float)
        and not isinstance(started, bool)
        and final_transcript_at is not None
        and math.isfinite(started)
        and math.isfinite(final_transcript_at)
        and started >= final_transcript_at > 0
    ):
        return "stt_final_to_audio_start_ms", round((started - final_transcript_at) * 1000)
    return None


def require_provider_key(name: str, reference: str | None) -> str:
    """Resolve only the explicit provider key reference, never arbitrary config text."""
    expected = f"env:{name}"
    if reference is not None and reference != expected:
        raise ValueError(f"Only {expected} is supported for this provider")
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} is not configured")
    return value


def make_session(config: AgentConfig) -> AgentSession[None]:
    refs = config.provider_references
    language = config.locale.split("-")[0]
    llm: google.LLM | openai.LLM
    if config.voice.llm_provider == "google":
        llm = google.LLM(
            model=config.voice.llm_model,
            api_key=require_provider_key("GOOGLE_API_KEY", refs.get("llm_api_key")),
        )
    else:
        llm = openai.LLM(
            model=config.voice.llm_model,
            api_key=require_provider_key("OPENAI_API_KEY", refs.get("llm_api_key")),
        )
    return AgentSession(
        stt=deepgram.STT(
            model=config.voice.stt_model,
            language=language,
            api_key=require_provider_key("DEEPGRAM_API_KEY", refs.get("stt_api_key")),
        ),
        llm=llm,
        tts=cartesia.TTS(
            model=config.voice.tts_model,
            voice=config.voice.tts_voice,
            language=language,
            word_timestamps=language in ("en", "de", "es", "fr"),
            api_key=require_provider_key("CARTESIA_API_KEY", refs.get("tts_api_key")),
        ),
    )


@server.rtc_session(agent_name=WORKER_NAME)
async def voice_session(ctx: JobContext) -> None:
    session_id = UUID(int=0)
    voice: AgentSession[None] | None = None
    finished = asyncio.Event()
    failure: str | None = None
    last_interim_at = 0.0
    last_final_transcript_at: float | None = None
    browser_seen: set[str] = set()
    channel = "browser"
    direction = "browser"
    inbound_expected: tuple[str, str, str] | None = None
    phone_identity: str | None = None
    pipeline_ready = False
    phone_connected = False

    try:
        metadata = json.loads(ctx.job.metadata)
        if not isinstance(metadata, dict):
            raise ValueError("Invalid dispatch metadata")
        if "phone_number_id" in metadata:
            number_id = UUID(str(metadata["phone_number_id"]))
            session_id, config, trunk_id, rule_id, e164 = await asyncio.to_thread(
                create_inbound_session, number_id, ctx.job.room.name
            )
            inbound_expected = (trunk_id, rule_id, e164)
            channel = "phone"
            direction = "inbound"
        else:
            session_id = UUID(str(metadata["session_id"]))
            config = await asyncio.to_thread(load_pinned, session_id, ctx.job.room.name)
            channel = await asyncio.to_thread(session_channel, session_id)
            direction = "outbound" if channel == "phone" else "browser"
        voice = make_session(config)

        @voice.on("user_input_transcribed")
        def on_user_transcript(event: object) -> None:
            nonlocal last_final_transcript_at, last_interim_at
            transcript = str(getattr(event, "transcript", ""))
            is_final = bool(getattr(event, "is_final", False))
            created = float(getattr(event, "created_at", 0.0))
            if not transcript or (not is_final and created - last_interim_at < 1.0):
                return
            if not is_final:
                last_interim_at = created
            else:
                last_final_transcript_at = created if created > 0 else time.time()
            record_event(
                session_id,
                "transcript",
                speaker="caller",
                text=transcript,
                details={"final": is_final, "source": "stt"},
            )

        @voice.on("conversation_item_added")
        def on_conversation_item(event: object) -> None:
            item = getattr(event, "item", None)
            if getattr(item, "role", None) != "assistant":
                return
            spoken = getattr(item, "text_content", None)
            if not isinstance(spoken, str) or not spoken:
                return
            interrupted = bool(getattr(item, "interrupted", False))
            item_metrics = getattr(item, "metrics", {})
            latency = response_latency(item_metrics, last_final_transcript_at)
            record_event(
                session_id,
                "transcript",
                speaker="agent",
                text=spoken,
                details={"final": True, "interrupted": interrupted, "source": "playback"},
                metrics={f"last_{latency[0]}": latency[1]} if latency is not None else None,
            )
            if latency is not None:
                record_event(
                    session_id,
                    "metric",
                    details={"name": latency[0], "value": latency[1], "unit": "ms"},
                )
            if interrupted:
                record_event(session_id, "interruption", details={"source": "voice-worker"})

        @voice.on("session_usage_updated")
        def on_usage(event: object) -> None:
            usage = getattr(getattr(event, "usage", None), "model_usage", None)
            models = safe_usage(usage)
            if models:
                record_event(
                    session_id,
                    "metric",
                    details={"name": "usage_updated"},
                    metrics={"usage": models},
                )

        @voice.on("error")
        def on_error(event: object) -> None:
            nonlocal failure
            failure = "provider_unavailable"
            source = getattr(getattr(event, "source", None), "provider", "voice-pipeline")
            logger.error(
                "Voice provider failed", extra={"session_id": str(session_id), "source": source}
            )
            finished.set()

        @voice.on("close")
        def on_close(event: object) -> None:
            nonlocal failure
            reason = str(getattr(event, "reason", ""))
            if "error" in reason.lower() or getattr(event, "error", None) is not None:
                failure = "provider_unavailable"
            finished.set()

        def on_participant_connected(participant: object) -> None:
            nonlocal phone_connected, phone_identity, failure
            identity = str(getattr(participant, "identity", ""))
            if (
                channel == "phone"
                and direction == "inbound"
                and phone_identity is None
                and getattr(participant, "kind", None) == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
            ):
                phone_identity = identity
            if identity.startswith("browser-") and identity not in browser_seen:
                browser_seen.add(identity)
                record_event(session_id, "browser_connected", details={"source": "browser"})
            if channel == "phone" and pipeline_ready and not phone_connected:
                if direction == "outbound" and identity != f"sip-{session_id}":
                    return
                if not is_expected_sip_participant(
                    participant, session_id, direction, inbound_expected
                ):
                    failure = "invalid_sip_route"
                    finished.set()
                    return
                phone_connected = True
                phone_identity = identity
                try:
                    if direction == "inbound":
                        record_inbound_caller(session_id, participant)
                    mark_active(session_id)
                    record_event(session_id, "phone_connected", details={"direction": direction})
                    assert voice is not None
                    voice.generate_reply(
                        instructions=(
                            "Greet the caller briefly in the configured language. "
                            "Ask how you can help."
                        )
                    )
                except Exception:
                    failure = "worker_startup_error"
                    finished.set()

        def on_participant_disconnected(participant: object) -> None:
            identity = str(getattr(participant, "identity", ""))
            if identity.startswith("browser-"):
                record_event(session_id, "disconnected", details={"source": "browser"})
                finished.set()
            if channel == "phone" and identity == phone_identity:
                record_event(session_id, "disconnected", details={"source": "phone"})
                finished.set()

        ctx.room.on("participant_connected", on_participant_connected)
        ctx.room.on("participant_disconnected", on_participant_disconnected)
        await ctx.connect()
        await voice.start(
            agent=Agent(instructions=config.instructions), room=ctx.room, record=False
        )
        if channel == "browser":
            await asyncio.to_thread(mark_active, session_id)
        pipeline_ready = True
        for participant in ctx.room.remote_participants.values():
            on_participant_connected(participant)
        logger.info("Voice session active", extra={"session_id": str(session_id)})
        await finished.wait()
    except Exception as exc:
        failure = failure or "worker_startup_error"
        logger.error(
            "Voice session failed: %s",
            type(exc).__name__,
            extra={"session_id": str(session_id)},
        )
    finally:
        if voice is not None:
            try:
                await voice.aclose()
            except Exception as exc:
                logger.error(
                    "Voice pipeline close failed: %s",
                    type(exc).__name__,
                    extra={"session_id": str(session_id)},
                )
        if session_id.int != 0:
            try:
                await asyncio.to_thread(
                    mark_finished,
                    session_id,
                    error_code=failure,
                    reason="provider_error" if failure else "connection_closed",
                )
            except Exception as exc:
                logger.error(
                    "Voice session finalization failed: %s",
                    type(exc).__name__,
                    extra={"session_id": str(session_id)},
                )
        try:
            await asyncio.to_thread(delete_room, get_settings(), ctx.job.room.name)
            if session_id.int != 0:
                await asyncio.to_thread(mark_room_cleaned, session_id)
        except Exception as exc:
            logger.error(
                "Voice room cleanup failed: %s",
                type(exc).__name__,
                extra={"session_id": str(session_id)},
            )
