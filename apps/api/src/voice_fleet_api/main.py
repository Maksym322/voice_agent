"""Voice Fleet HTTP API."""

import asyncio
import base64
import binascii
import hmac
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import and_, func, or_, select, text, tuple_
from sqlalchemy.orm import Session

from voice_fleet_api.agent_schema import AgentConfig, parse_config
from voice_fleet_api.config import Settings, get_settings
from voice_fleet_api.db import SessionLocal, get_db
from voice_fleet_api.livekit_gateway import (
    browser_token,
    delete_room,
    dial_outbound,
    open_room,
    provision_inbound,
    remove_inbound,
    require_livekit,
)
from voice_fleet_api.models import (
    Agent,
    AgentVersion,
    AuditEvent,
    DeploymentBinding,
    LoginSession,
    OperatorView,
    PhoneNumber,
    SessionDiagnostic,
    SessionEvent,
    User,
    VoiceSession,
)
from voice_fleet_api.security import (
    digest,
    expiry,
    new_token,
    normalize_email,
    now_utc,
    verify_password,
)

COOKIE_NAME = "vf_session"
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class Identity(BaseModel):
    id: str
    email: str
    role: str
    csrf_token: str | None = None


logger = logging.getLogger(__name__)


def sweep_expired_sessions(settings: Settings) -> None:
    if not all(
        (
            settings.livekit_url,
            settings.livekit_browser_url,
            settings.livekit_api_key,
            settings.livekit_api_secret,
        )
    ):
        return
    with SessionLocal() as db:
        current = now_utc()
        expired = db.scalars(
            select(VoiceSession)
            .where(
                or_(
                    VoiceSession.room_cleanup_pending.is_(True),
                    and_(
                        VoiceSession.status.in_(("pending", "active")),
                        or_(
                            VoiceSession.deadline_at <= current,
                            and_(
                                VoiceSession.status == "pending",
                                VoiceSession.created_at <= current - timedelta(seconds=60),
                            ),
                        ),
                    ),
                ),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for voice in expired:
            try:
                delete_room(settings, voice.room_name)
            except Exception:
                logger.exception("Could not close expired voice room %s", voice.id)
                continue
            if voice.room_cleanup_pending and voice.status in ("error", "ended"):
                voice.room_cleanup_pending = False
                continue
            ended = now_utc()
            timed_out = voice.status == "pending" and voice.deadline_at > current
            reason = "startup_error" if timed_out else "duration_limit"
            voice.status = "error" if timed_out else "ended"
            voice.end_reason = reason
            if timed_out:
                voice.error_code = "worker_timeout"
            voice.ended_at = ended
            db.add(
                SessionEvent(
                    session_id=voice.id,
                    kind="error" if timed_out else "ended",
                    details={"reason": reason},
                    created_at=ended,
                )
            )
            if timed_out:
                db.add(
                    SessionDiagnostic(
                        session_id=voice.id,
                        severity="error",
                        component="voice-worker",
                        code="worker_timeout",
                        message="The voice worker did not start before the timeout.",
                        created_at=ended,
                    )
                )
        db.commit()


async def sweep_loop() -> None:
    ticks = 0
    while True:
        try:
            await asyncio.to_thread(sweep_expired_sessions, get_settings())
            if ticks % 720 == 0:
                await asyncio.to_thread(purge_retained_sessions)
            ticks += 1
        except Exception:
            logger.exception("Voice session sweep failed")
        await asyncio.sleep(5)


def purge_retained_sessions() -> None:
    """Delete terminal sessions and their events at the pinned retention deadline."""
    current = now_utc()
    with SessionLocal.begin() as db:
        rows = db.execute(
            select(VoiceSession, AgentVersion.snapshot)
            .join(AgentVersion, VoiceSession.version_id == AgentVersion.id)
            .where(
                VoiceSession.status.in_(("ended", "error")),
                VoiceSession.ended_at.is_not(None),
                VoiceSession.room_cleanup_pending.is_(False),
            )
            .with_for_update(of=VoiceSession, skip_locked=True)
        )
        for voice, snapshot in rows:
            days = AgentConfig.model_validate(snapshot).retention_days
            if voice.ended_at is not None and voice.ended_at + timedelta(days=days) <= current:
                db.delete(voice)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(sweep_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Voice Fleet API", version="0.1.0", lifespan=lifespan)


def check_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if origin != settings.app_origin:
        raise HTTPException(403, "Origin denied")


def current_session(request: Request, db: Db) -> LoginSession:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Authentication required")
    session = db.scalar(
        select(LoginSession).where(
            LoginSession.token_hash == digest(token),
            LoginSession.revoked_at.is_(None),
            LoginSession.expires_at > now_utc(),
        )
    )
    if session is None:
        raise HTTPException(401, "Authentication required")
    return session


CurrentSession = Annotated[LoginSession, Depends(current_session)]


def require_csrf(request: Request, session: CurrentSession, settings: Config) -> LoginSession:
    check_origin(request, settings)
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied or not hmac.compare_digest(supplied, session.csrf_token):
        raise HTTPException(403, "CSRF token required")
    return session


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness(db: Db) -> dict[str, str]:
    try:
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "Database or migrations unavailable") from exc
    if revision != "0007_phone_route_lifecycle":
        raise HTTPException(503, "Database migration required")
    return {"status": "ready"}


@app.post("/api/auth/login", response_model=Identity)
def login(
    body: LoginBody, request: Request, response: Response, db: Db, settings: Config
) -> Identity:
    check_origin(request, settings)
    user = db.scalar(select(User).where(User.email == normalize_email(body.email)))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = new_token()
    csrf = new_token()
    db.add(
        LoginSession(
            user_id=user.id,
            token_hash=digest(token),
            csrf_token=csrf,
            expires_at=expiry(settings),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.session_secure_cookie,
        samesite="lax",
        max_age=settings.session_lifetime_minutes * 60,
        path="/",
    )
    return Identity(id=str(user.id), email=user.email, role=user.role, csrf_token=csrf)


@app.post("/api/auth/logout", status_code=204)
def logout(
    response: Response,
    db: Db,
    settings: Config,
    session: Annotated[LoginSession, Depends(require_csrf)],
) -> None:
    active = db.scalars(
        select(VoiceSession)
        .where(
            VoiceSession.started_by == session.user_id,
            VoiceSession.status.in_(("pending", "active")),
        )
        .with_for_update()
    ).all()
    for voice in active:
        try:
            delete_room(settings, voice.room_name)
        except Exception as exc:
            raise HTTPException(503, "Could not close an active voice room") from exc
        voice.status = "ended"
        voice.end_reason = "sign_out"
        voice.ended_at = now_utc()
        db.add(
            SessionEvent(
                session_id=voice.id,
                kind="ended",
                details={"reason": "sign_out"},
                created_at=voice.ended_at,
            )
        )
    session.revoked_at = datetime.now(UTC)
    db.commit()
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, secure=settings.session_secure_cookie, samesite="lax"
    )


@app.get("/api/auth/me", response_model=Identity)
def me(session: CurrentSession) -> Identity:
    user = session.user
    return Identity(
        id=str(user.id), email=user.email, role=user.role, csrf_token=session.csrf_token
    )


@app.get("/api/admin/health")
def admin_health(session: CurrentSession) -> dict[str, str]:
    if session.user.role != "admin":
        raise HTTPException(403, "Admin role required")
    return {"status": "ok"}


class AgentInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: AgentConfig


class ActivationInput(BaseModel):
    version_id: UUID
    expected_revision: int = Field(ge=0)


def can_edit(session: LoginSession) -> None:
    if session.user.role not in ("admin", "operator"):
        raise HTTPException(403, "Admin or operator role required")


def get_agent(db: Session, agent_id: UUID, lock: bool = False) -> Agent:
    query = select(Agent).where(Agent.id == agent_id)
    if lock:
        query = query.with_for_update()
    agent = db.scalar(query)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    return agent


def audit(
    db: Session, session: LoginSession, agent_id: UUID, action: str, details: dict[str, object]
) -> None:
    db.add(
        AuditEvent(
            actor_id=session.user_id,
            agent_id=agent_id,
            action=action,
            details=details,
            created_at=now_utc(),
        )
    )


def agent_view(agent: Agent, current_sessions: int = 0) -> dict[str, object]:
    return {
        "id": str(agent.id),
        "name": agent.name,
        "revision": agent.revision,
        "config": agent.draft,
        "current_sessions": current_sessions,
    }


@app.get("/api/agents")
def list_agents(db: Db, session: CurrentSession) -> list[dict[str, object]]:
    counts: dict[UUID, int] = {
        agent_id: count
        for agent_id, count in db.execute(
            select(VoiceSession.agent_id, func.count())
            .where(VoiceSession.status.in_(("pending", "active")))
            .group_by(VoiceSession.agent_id)
        )
    }
    return [
        agent_view(agent, counts.get(agent.id, 0))
        for agent in db.scalars(select(Agent).order_by(Agent.name)).all()
    ]


@app.post("/api/agents", status_code=201)
def create_agent(
    body: AgentInput, db: Db, session: Annotated[LoginSession, Depends(require_csrf)]
) -> dict[str, object]:
    can_edit(session)
    agent = Agent(name=body.name, draft=parse_config(body.config), revision=1)
    db.add(agent)
    db.flush()
    audit(db, session, agent.id, "created", {"revision": 1})
    db.commit()
    return agent_view(agent)


@app.get("/api/agents/{agent_id}")
def read_agent(agent_id: UUID, db: Db, session: CurrentSession) -> dict[str, object]:
    agent = get_agent(db, agent_id)
    current = db.scalar(
        select(func.count())
        .select_from(VoiceSession)
        .where(
            VoiceSession.agent_id == agent_id,
            VoiceSession.status.in_(("pending", "active")),
        )
    )
    return agent_view(agent, current or 0)


@app.put("/api/agents/{agent_id}/draft")
def update_draft(
    agent_id: UUID,
    body: AgentInput,
    request: Request,
    db: Db,
    session: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    can_edit(session)
    agent = get_agent(db, agent_id, lock=True)
    if request.headers.get("if-match") != str(agent.revision):
        raise HTTPException(409, f"Draft changed; current revision is {agent.revision}")
    agent.name = body.name
    agent.draft = parse_config(body.config)
    agent.revision += 1
    audit(db, session, agent.id, "draft_updated", {"revision": agent.revision})
    db.commit()
    return agent_view(agent)


@app.post("/api/agents/{agent_id}/import")
def import_draft(
    agent_id: UUID,
    body: AgentConfig,
    request: Request,
    db: Db,
    session: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    can_edit(session)
    agent = get_agent(db, agent_id, lock=True)
    if request.headers.get("if-match") != str(agent.revision):
        raise HTTPException(409, f"Draft changed; current revision is {agent.revision}")
    agent.draft = parse_config(body)
    agent.revision += 1
    audit(db, session, agent.id, "imported", {"revision": agent.revision})
    db.commit()
    return agent_view(agent)


@app.post("/api/agents/{agent_id}/publish", status_code=201)
def publish(
    agent_id: UUID,
    request: Request,
    db: Db,
    session: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    can_edit(session)
    agent = get_agent(db, agent_id, lock=True)
    if request.headers.get("if-match") != str(agent.revision):
        raise HTTPException(409, f"Draft changed; current revision is {agent.revision}")
    snapshot = parse_config(agent.draft)
    number = (
        db.scalar(select(func.max(AgentVersion.number)).where(AgentVersion.agent_id == agent.id))
        or 0
    ) + 1
    version = AgentVersion(
        agent_id=agent.id,
        number=number,
        snapshot=snapshot,
        published_at=now_utc(),
        published_by=session.user_id,
    )
    db.add(version)
    db.flush()
    agent.revision += 1
    audit(db, session, agent.id, "published", {"version_id": str(version.id), "number": number})
    db.commit()
    return {
        "id": str(version.id),
        "number": number,
        "snapshot": snapshot,
        "revision": agent.revision,
    }


@app.get("/api/agents/{agent_id}/versions")
def list_versions(agent_id: UUID, db: Db, session: CurrentSession) -> list[dict[str, object]]:
    get_agent(db, agent_id)
    versions = db.scalars(
        select(AgentVersion).where(AgentVersion.agent_id == agent_id).order_by(AgentVersion.number)
    ).all()
    return [
        {"id": str(v.id), "number": v.number, "published_at": v.published_at.isoformat()}
        for v in versions
    ]


@app.get("/api/agents/{agent_id}/versions/{version_id}/export")
def export_version(
    agent_id: UUID, version_id: UUID, db: Db, session: CurrentSession
) -> dict[str, object]:
    version = db.scalar(
        select(AgentVersion).where(AgentVersion.id == version_id, AgentVersion.agent_id == agent_id)
    )
    if version is None:
        raise HTTPException(404, "Version not found")
    return parse_config(version.snapshot)


@app.get("/api/agents/{agent_id}/bindings")
def list_bindings(agent_id: UUID, db: Db, session: CurrentSession) -> list[dict[str, object]]:
    get_agent(db, agent_id)
    bindings = db.scalars(
        select(DeploymentBinding).where(DeploymentBinding.agent_id == agent_id)
    ).all()
    return [
        {"environment": b.environment, "version_id": str(b.version_id), "revision": b.revision}
        for b in bindings
    ]


@app.put("/api/agents/{agent_id}/bindings/{environment}")
def activate(
    agent_id: UUID,
    environment: str,
    body: ActivationInput,
    db: Db,
    session: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    can_edit(session)
    if environment not in ("local", "staging", "production"):
        raise HTTPException(422, "Environment must be local, staging, or production")
    get_agent(db, agent_id, lock=True)
    version = db.scalar(
        select(AgentVersion).where(
            AgentVersion.id == body.version_id, AgentVersion.agent_id == agent_id
        )
    )
    if version is None or version.snapshot.get("schema_version") != 1:
        raise HTTPException(422, "Version is missing or incompatible with schema version 1")
    binding = db.scalar(
        select(DeploymentBinding).where(
            DeploymentBinding.agent_id == agent_id, DeploymentBinding.environment == environment
        )
    )
    current = binding.revision if binding else 0
    if body.expected_revision != current:
        raise HTTPException(409, f"Binding changed; current revision is {current}")
    prior = str(binding.version_id) if binding else None
    if binding:
        binding.version_id = version.id
        binding.revision += 1
    else:
        binding = DeploymentBinding(
            agent_id=agent_id, environment=environment, version_id=version.id, revision=1
        )
        db.add(binding)
    audit(
        db,
        session,
        agent_id,
        "activated",
        {"environment": environment, "version_id": str(version.id), "previous_version_id": prior},
    )
    db.commit()
    return {"environment": environment, "version_id": str(version.id), "revision": binding.revision}


@app.get("/api/agents/{agent_id}/audit")
def list_audit(agent_id: UUID, db: Db, session: CurrentSession) -> list[dict[str, object]]:
    get_agent(db, agent_id)
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.agent_id == agent_id)
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ).all()
    return [
        {
            "action": e.action,
            "actor_id": str(e.actor_id),
            "details": e.details,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


def can_use_playground(session: LoginSession) -> None:
    if session.user.role not in ("admin", "operator"):
        raise HTTPException(403, "Admin or operator role required")


def get_voice_session(
    db: Session, voice_id: UUID, login: LoginSession, *, lock: bool = False
) -> VoiceSession:
    can_use_playground(login)
    query = select(VoiceSession).where(VoiceSession.id == voice_id)
    if lock:
        query = query.with_for_update()
    voice = db.scalar(query)
    if voice is None or (login.user.role != "admin" and voice.started_by != login.user_id):
        raise HTTPException(404, "Voice session not found")
    return voice


def voice_view(voice: VoiceSession) -> dict[str, object]:
    return {
        "id": str(voice.id),
        "agent_id": str(voice.agent_id),
        "version_id": str(voice.version_id),
        "channel": voice.channel,
        "direction": voice.direction,
        "phone_number_id": str(voice.phone_number_id) if voice.phone_number_id else None,
        "destination_masked": f"••••{voice.destination_last4}" if voice.destination_last4 else None,
        "provider_call_id": voice.provider_call_id,
        "status": voice.status,
        "created_at": voice.created_at.isoformat(),
        "connected_at": voice.connected_at.isoformat() if voice.connected_at else None,
        "ended_at": voice.ended_at.isoformat() if voice.ended_at else None,
        "deadline_at": voice.deadline_at.isoformat(),
        "end_reason": voice.end_reason,
        "error_code": voice.error_code,
        "room_cleanup_pending": voice.room_cleanup_pending,
        "metrics": voice.metrics,
    }


@app.post("/api/agents/{agent_id}/sessions", status_code=201)
def start_voice_session(
    agent_id: UUID,
    db: Db,
    settings: Config,
    login: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    can_use_playground(login)
    try:
        _, browser_url, _, _ = require_livekit(settings)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    # Serialize starts for one user so the per-user live session cap cannot race.
    db.scalar(select(User).where(User.id == login.user_id).with_for_update())
    existing = db.scalar(
        select(VoiceSession.id).where(
            VoiceSession.started_by == login.user_id,
            VoiceSession.status.in_(("pending", "active")),
            VoiceSession.deadline_at > now_utc(),
        )
    )
    if existing is not None:
        raise HTTPException(409, "End the current voice session before starting another")
    binding = db.scalar(
        select(DeploymentBinding).where(
            DeploymentBinding.agent_id == agent_id,
            DeploymentBinding.environment == settings.environment,
        )
    )
    if binding is None:
        raise HTTPException(409, "Agent has no active version in this environment")
    version = db.scalar(
        select(AgentVersion).where(
            AgentVersion.id == binding.version_id, AgentVersion.agent_id == agent_id
        )
    )
    if version is None:
        raise HTTPException(409, "Active version is unavailable")
    config = AgentConfig.model_validate(version.snapshot)
    started = now_utc()
    voice_id = uuid4()
    voice = VoiceSession(
        id=voice_id,
        agent_id=agent_id,
        version_id=version.id,
        started_by=login.user_id,
        room_name=f"vf-{voice_id}",
        status="pending",
        created_at=started,
        deadline_at=started
        + timedelta(seconds=min(config.session_limit_seconds, settings.playground_max_seconds)),
        metrics={},
    )
    db.add(voice)
    db.commit()
    try:
        token = browser_token(settings, voice.room_name, login.user_id, voice.id)
        open_room(settings, voice.room_name, voice.id)
    except Exception as exc:
        voice.status = "error"
        voice.error_code = "livekit_unavailable"
        voice.end_reason = "startup_error"
        voice.ended_at = now_utc()
        db.add(
            SessionEvent(
                session_id=voice.id,
                kind="error",
                details={"reason": "startup_error", "code": "livekit_unavailable"},
                created_at=voice.ended_at,
            )
        )
        db.add(
            SessionDiagnostic(
                session_id=voice.id,
                severity="error",
                component="livekit-api",
                code="livekit_unavailable",
                message="Room creation or worker dispatch failed.",
                created_at=voice.ended_at,
            )
        )
        db.commit()
        raise HTTPException(503, "Voice service is unavailable") from exc
    return {**voice_view(voice), "url": browser_url, "token": token}


@app.post("/api/agents/{agent_id}/outbound-test", status_code=201)
def start_outbound_test(
    agent_id: UUID,
    db: Db,
    settings: Config,
    login: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    """Dial only the installation's configured test number, on an admin click."""
    if login.user.role != "admin":
        raise HTTPException(403, "Admin role required")
    if not settings.outbound_sip_trunk_id or not settings.outbound_test_destination:
        raise HTTPException(503, "Outbound phone test is not configured")
    try:
        require_livekit(settings)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    # Serialize outbound starts across admins in this independent installation.
    db.execute(text("SELECT pg_advisory_xact_lock(5566005)"))
    active_phone = db.scalar(
        select(VoiceSession.id).where(
            VoiceSession.channel == "phone", VoiceSession.status.in_(("pending", "active"))
        )
    )
    if active_phone is not None:
        raise HTTPException(409, "Another phone test is in progress")
    binding = db.scalar(
        select(DeploymentBinding).where(
            DeploymentBinding.agent_id == agent_id,
            DeploymentBinding.environment == settings.environment,
        )
    )
    if binding is None:
        raise HTTPException(409, "Agent has no active version in this environment")
    version = db.scalar(
        select(AgentVersion).where(
            AgentVersion.id == binding.version_id, AgentVersion.agent_id == agent_id
        )
    )
    if version is None:
        raise HTTPException(409, "Active version is unavailable")
    config = AgentConfig.model_validate(version.snapshot)
    started = now_utc()
    voice_id = uuid4()
    voice = VoiceSession(
        id=voice_id,
        agent_id=agent_id,
        version_id=version.id,
        started_by=login.user_id,
        room_name=f"vf-{voice_id}",
        channel="phone",
        direction="outbound",
        destination_last4=settings.outbound_test_destination[-4:],
        status="pending",
        created_at=started,
        deadline_at=started
        + timedelta(
            seconds=min(
                config.session_limit_seconds,
                settings.playground_max_seconds,
                settings.outbound_test_max_seconds,
            )
        ),
        metrics={},
    )
    db.add(voice)
    db.commit()
    try:
        open_room(settings, voice.room_name, voice.id)
        call_id = dial_outbound(settings, voice.room_name, voice.id)
        db.refresh(voice)
        if voice.status == "error":
            raise RuntimeError("Voice worker failed before the call connected")
        voice.provider_call_id = call_id[:128]
        db.add(
            SessionEvent(
                session_id=voice.id,
                kind="phone_answered",
                source="livekit-api",
                details={"direction": "outbound"},
                created_at=now_utc(),
            )
        )
        db.commit()
    except Exception as exc:
        db.refresh(voice)
        if voice.status != "error":
            voice.status = "error"
            voice.error_code = "outbound_call_failed"
            voice.end_reason = "startup_error"
            voice.ended_at = now_utc()
            voice.room_cleanup_pending = True
            db.add(
                SessionEvent(
                    session_id=voice.id,
                    kind="error",
                    details={"reason": "startup_error", "code": "outbound_call_failed"},
                    created_at=voice.ended_at,
                )
            )
            db.add(
                SessionDiagnostic(
                    session_id=voice.id,
                    severity="error",
                    component="livekit-api",
                    code="outbound_call_failed",
                    message="The phone call could not be connected.",
                    created_at=voice.ended_at,
                )
            )
        db.commit()
        try:
            delete_room(settings, voice.room_name)
            voice.room_cleanup_pending = False
            db.commit()
        except Exception:
            logger.exception("Could not close failed outbound room %s", voice.id)
        raise HTTPException(503, "The phone call could not be connected") from exc
    return voice_view(voice)


class AddPhoneNumber(BaseModel):
    e164: str = Field(pattern=r"^\+[1-9][0-9]{6,14}$")
    provider: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_-]+$")
    route_agent_id: UUID


class ChangePhoneRoute(BaseModel):
    route_agent_id: UUID
    expected_revision: int = Field(ge=1)


class PhoneRouteRevision(BaseModel):
    expected_revision: int = Field(ge=1)


class ReactivatePhoneNumber(PhoneRouteRevision):
    provider: str | None = Field(
        default=None, min_length=2, max_length=32, pattern=r"^[a-z0-9_-]+$"
    )


def require_admin(login: LoginSession) -> None:
    if login.user.role != "admin":
        raise HTTPException(403, "Admin role required")


def require_active_agent(db: Session, agent_id: UUID, settings: Settings) -> None:
    binding = db.scalar(
        select(DeploymentBinding.id).where(
            DeploymentBinding.agent_id == agent_id,
            DeploymentBinding.environment == settings.environment,
        )
    )
    if binding is None:
        raise HTTPException(409, "Agent has no active version in this environment")


def phone_number_view(number: PhoneNumber) -> dict[str, object]:
    return {
        "id": str(number.id),
        "e164_masked": f"••••{number.e164[-4:]}",
        "provider": number.provider,
        "route_agent_id": str(number.route_agent_id),
        "status": number.status,
        "revision": number.revision,
        "livekit_configured": number.status == "active",
        "carrier_verified": False,
        "created_at": number.created_at.isoformat(),
    }


@app.get("/api/phone-numbers")
def list_phone_numbers(db: Db, login: CurrentSession) -> list[dict[str, object]]:
    require_admin(login)
    return [
        phone_number_view(number)
        for number in db.scalars(select(PhoneNumber).order_by(PhoneNumber.created_at)).all()
    ]


@app.post("/api/phone-numbers", status_code=201)
def add_phone_number(
    body: AddPhoneNumber,
    db: Db,
    settings: Config,
    login: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    require_admin(login)
    require_active_agent(db, body.route_agent_id, settings)
    try:
        require_livekit(settings)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    db.execute(text("SELECT pg_advisory_xact_lock(5566006)"))
    if db.scalar(select(PhoneNumber.id).where(PhoneNumber.e164 == body.e164)):
        raise HTTPException(409, "Number is already configured")
    number_id = uuid4()
    trunk_id: str | None = None
    rule_id: str | None = None
    try:
        trunk_id, rule_id = provision_inbound(settings, number_id, body.e164)
        current = now_utc()
        number = PhoneNumber(
            id=number_id,
            e164=body.e164,
            provider=body.provider,
            route_agent_id=body.route_agent_id,
            created_by=login.user_id,
            sip_trunk_id=trunk_id,
            dispatch_rule_id=rule_id,
            revision=1,
            created_at=current,
            updated_at=current,
        )
        db.add(number)
        db.add(
            AuditEvent(
                actor_id=login.user_id,
                agent_id=body.route_agent_id,
                action="phone_number_added",
                details={"number_id": str(number_id), "suffix": body.e164[-4:]},
                created_at=current,
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        if trunk_id and rule_id:
            try:
                remove_inbound(settings, trunk_id, rule_id)
            except Exception:
                logger.exception("Could not roll back LiveKit number %s", number_id)
        raise HTTPException(503, "Could not configure inbound routing") from exc
    return phone_number_view(number)


@app.put("/api/phone-numbers/{number_id}/route")
def change_phone_route(
    number_id: UUID,
    body: ChangePhoneRoute,
    db: Db,
    settings: Config,
    login: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    require_admin(login)
    number = db.scalar(select(PhoneNumber).where(PhoneNumber.id == number_id).with_for_update())
    if number is None:
        raise HTTPException(404, "Number not found")
    if number.revision != body.expected_revision:
        raise HTTPException(409, "Number route was changed; reload and try again")
    if number.status == "deprovisioning":
        raise HTTPException(409, "Number route is being deprovisioned")
    require_active_agent(db, body.route_agent_id, settings)
    number.route_agent_id = body.route_agent_id
    number.revision += 1
    number.updated_at = now_utc()
    db.add(
        AuditEvent(
            actor_id=login.user_id,
            agent_id=body.route_agent_id,
            action="phone_route_changed",
            details={"number_id": str(number_id), "revision": number.revision},
            created_at=number.updated_at,
        )
    )
    db.commit()
    return phone_number_view(number)


@app.post("/api/phone-numbers/{number_id}/deactivate")
def deactivate_phone_number(
    number_id: UUID,
    body: PhoneRouteRevision,
    db: Db,
    settings: Config,
    login: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    require_admin(login)
    number = db.scalar(select(PhoneNumber).where(PhoneNumber.id == number_id).with_for_update())
    if number is None:
        raise HTTPException(404, "Number not found")
    if number.revision != body.expected_revision:
        raise HTTPException(409, "Number route was changed; reload and try again")
    if number.status == "retired":
        raise HTTPException(409, "Number route is already inactive")
    if number.status == "active":
        in_call = db.scalar(
            select(VoiceSession.id)
            .where(
                VoiceSession.phone_number_id == number_id,
                VoiceSession.status.in_(("pending", "active")),
            )
            .limit(1)
        )
        if in_call is not None:
            raise HTTPException(409, "Wait for active calls on this number to end")
        number.status = "deprovisioning"
        number.revision += 1
        number.updated_at = now_utc()
        db.add(
            AuditEvent(
                actor_id=login.user_id,
                agent_id=number.route_agent_id,
                action="phone_number_deprovision_started",
                details={"number_id": str(number_id), "revision": number.revision},
                created_at=number.updated_at,
            )
        )
        db.commit()
    try:
        remove_inbound(settings, number.sip_trunk_id, number.dispatch_rule_id)
    except Exception as exc:
        logger.exception("Could not deprovision inbound number %s", number_id)
        raise HTTPException(503, "LiveKit cleanup failed; retry deactivation") from exc
    db.refresh(number, with_for_update=True)
    if number.status == "retired":
        return phone_number_view(number)
    if number.status != "deprovisioning":
        raise HTTPException(409, "Number route changed during cleanup; reload")
    number.status = "retired"
    number.revision += 1
    number.updated_at = now_utc()
    db.add(
        AuditEvent(
            actor_id=login.user_id,
            agent_id=number.route_agent_id,
            action="phone_number_deactivated",
            details={"number_id": str(number_id), "revision": number.revision},
            created_at=number.updated_at,
        )
    )
    db.commit()
    return phone_number_view(number)


@app.post("/api/phone-numbers/{number_id}/reactivate")
def reactivate_phone_number(
    number_id: UUID,
    body: ReactivatePhoneNumber,
    db: Db,
    settings: Config,
    login: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    require_admin(login)
    number = db.scalar(select(PhoneNumber).where(PhoneNumber.id == number_id).with_for_update())
    if number is None:
        raise HTTPException(404, "Number not found")
    if number.revision != body.expected_revision:
        raise HTTPException(409, "Number route was changed; reload and try again")
    if number.status != "retired":
        raise HTTPException(409, "Deactivate the number before reactivating it")
    require_active_agent(db, number.route_agent_id, settings)
    previous_provider = number.provider
    trunk_id: str | None = None
    rule_id: str | None = None
    try:
        trunk_id, rule_id = provision_inbound(settings, number.id, number.e164)
        number.sip_trunk_id = trunk_id
        number.dispatch_rule_id = rule_id
        if body.provider is not None:
            number.provider = body.provider
        number.status = "active"
        number.revision += 1
        number.updated_at = now_utc()
        db.add(
            AuditEvent(
                actor_id=login.user_id,
                agent_id=number.route_agent_id,
                action="phone_number_reactivated",
                details={
                    "number_id": str(number_id),
                    "revision": number.revision,
                    "previous_provider": previous_provider,
                    "provider": number.provider,
                },
                created_at=number.updated_at,
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        if trunk_id and rule_id:
            try:
                remove_inbound(settings, trunk_id, rule_id)
            except Exception:
                logger.exception("Could not roll back reactivated number %s", number_id)
        raise HTTPException(503, "Could not reactivate inbound routing") from exc
    return phone_number_view(number)


@app.get("/api/sessions")
def list_voice_sessions(db: Db, login: CurrentSession) -> list[dict[str, object]]:
    can_use_playground(login)
    query = select(VoiceSession).order_by(VoiceSession.created_at.desc()).limit(100)
    if login.user.role != "admin":
        query = query.where(VoiceSession.started_by == login.user_id)
    return [voice_view(voice) for voice in db.scalars(query).all()]


@app.get("/api/sessions/{voice_id}")
def read_voice_session(voice_id: UUID, db: Db, login: CurrentSession) -> dict[str, object]:
    return voice_view(get_voice_session(db, voice_id, login))


@app.get("/api/sessions/{voice_id}/events")
def list_session_events(voice_id: UUID, db: Db, login: CurrentSession) -> list[dict[str, object]]:
    get_voice_session(db, voice_id, login)
    events = db.scalars(
        select(SessionEvent)
        .where(SessionEvent.session_id == voice_id)
        .order_by(SessionEvent.created_at, SessionEvent.id)
    ).all()
    return [
        {
            "id": str(event.id),
            "kind": event.kind,
            "source": event.source,
            "speaker": event.speaker,
            "text": event.text,
            "details": event.details,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]


@app.post("/api/sessions/{voice_id}/end")
def end_voice_session(
    voice_id: UUID,
    db: Db,
    settings: Config,
    login: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    voice = get_voice_session(db, voice_id, login, lock=True)
    if voice.status in ("ended", "error"):
        return voice_view(voice)
    try:
        delete_room(settings, voice.room_name)
    except Exception as exc:
        raise HTTPException(503, "Could not close the voice room") from exc
    voice.status = "ended"
    voice.end_reason = "user_request"
    voice.ended_at = now_utc()
    db.add(
        SessionEvent(
            session_id=voice.id,
            kind="ended",
            details={"reason": "user_request"},
            created_at=voice.ended_at,
        )
    )
    db.commit()
    return voice_view(voice)


BoardField = Literal["agent", "channel", "duration", "last_activity", "version"]
BoardStatus = Literal["pending", "active", "error", "ended"]


def default_fields() -> list[BoardField]:
    return ["agent", "duration", "last_activity", "version"]


def default_groups() -> list[BoardStatus]:
    return ["pending", "active", "error", "ended"]


class BoardView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    fields: list[BoardField] = Field(default_factory=default_fields, min_length=1, max_length=5)
    group_order: list[BoardStatus] = Field(
        default_factory=default_groups, min_length=4, max_length=4
    )
    show_ended: bool = True
    agent_filter: UUID | None = None

    @model_validator(mode="after")
    def validate_unique(self) -> "BoardView":
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("Board fields must be unique")
        if set(self.group_order) != {"pending", "active", "error", "ended"}:
            raise ValueError("Board groups must contain each canonical status once")
        return self


def default_board_view(settings: Settings) -> BoardView:
    return BoardView.model_validate({"group_order": settings.console_default_groups.split(",")})


def encode_cursor(created_at: datetime, identifier: UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(identifier)], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        date_value, id_value = json.loads(raw)
        parsed = datetime.fromisoformat(date_value)
        if parsed.tzinfo is None:
            raise ValueError("Cursor time must have a timezone")
        return parsed, UUID(id_value)
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, binascii.Error) as exc:
        raise HTTPException(422, "Invalid cursor") from exc


@app.get("/api/console/config")
def console_config(settings: Config, login: CurrentSession) -> dict[str, object]:
    can_use_playground(login)
    return {
        "brand_name": settings.console_brand_name,
        "accent_color": settings.console_accent_color,
        "default_view": default_board_view(settings).model_dump(mode="json"),
        "modules": [
            module
            for module in settings.console_visible_modules.split(",")
            if module != "numbers" or login.user.role == "admin"
        ],
        "outbound_test_available": bool(
            login.user.role == "admin"
            and settings.outbound_sip_trunk_id
            and settings.outbound_test_destination
        ),
        "outbound_test_destination_masked": (
            f"••••{settings.outbound_test_destination[-4:]}"
            if login.user.role == "admin" and settings.outbound_test_destination
            else None
        ),
    }


@app.get("/api/console/view")
def read_board_view(db: Db, settings: Config, login: CurrentSession) -> dict[str, object]:
    can_use_playground(login)
    saved = db.scalar(select(OperatorView).where(OperatorView.user_id == login.user_id))
    view = BoardView.model_validate(saved.config) if saved else default_board_view(settings)
    return view.model_dump(mode="json")


@app.put("/api/console/view")
def save_board_view(
    body: BoardView,
    db: Db,
    login: Annotated[LoginSession, Depends(require_csrf)],
) -> dict[str, object]:
    can_use_playground(login)
    db.scalar(select(User).where(User.id == login.user_id).with_for_update())
    saved = db.scalar(
        select(OperatorView).where(OperatorView.user_id == login.user_id).with_for_update()
    )
    if saved is None:
        saved = OperatorView(user_id=login.user_id, config={}, updated_at=now_utc())
        db.add(saved)
    saved.config = body.model_dump(mode="json")
    saved.updated_at = now_utc()
    db.commit()
    return body.model_dump(mode="json")


@app.get("/api/console/overview")
def console_overview(db: Db, login: CurrentSession) -> dict[str, object]:
    can_use_playground(login)
    query = select(VoiceSession.status, func.count()).group_by(VoiceSession.status)
    if login.user.role != "admin":
        query = query.where(VoiceSession.started_by == login.user_id)
    counts = {status: count for status, count in db.execute(query)}
    return {
        "counts": {
            status: counts.get(status, 0) for status in ("pending", "active", "error", "ended")
        },
        "database": "ready",
        "worker": "unverified",
        "worker_note": "No worker registration or capacity health signal is connected.",
    }


@app.get("/api/console/sessions")
def console_sessions(
    db: Db,
    login: CurrentSession,
    scope: Literal["board", "history"] = "board",
    status: BoardStatus | None = None,
    agent_id: UUID | None = None,
    session_id: UUID | None = None,
    channel: Literal["browser", "phone"] | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    cursor: str | None = Query(default=None, max_length=256),
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict[str, object]:
    can_use_playground(login)
    query = (
        select(VoiceSession, Agent.name, AgentVersion.number)
        .join(Agent, VoiceSession.agent_id == Agent.id)
        .join(AgentVersion, VoiceSession.version_id == AgentVersion.id)
    )
    if login.user.role != "admin":
        query = query.where(VoiceSession.started_by == login.user_id)
    if scope == "history":
        query = query.where(VoiceSession.status.in_(("ended", "error")))
    else:
        recent = now_utc() - timedelta(minutes=5)
        query = query.where(
            or_(
                VoiceSession.status.in_(("pending", "active")),
                and_(VoiceSession.status.in_(("error", "ended")), VoiceSession.ended_at >= recent),
            )
        )
    if status:
        query = query.where(VoiceSession.status == status)
    if agent_id:
        query = query.where(VoiceSession.agent_id == agent_id)
    if session_id:
        query = query.where(VoiceSession.id == session_id)
    if channel:
        query = query.where(VoiceSession.channel == channel)
    if from_at:
        query = query.where(VoiceSession.created_at >= from_at)
    if to_at:
        query = query.where(VoiceSession.created_at <= to_at)
    if cursor:
        query = query.where(
            tuple_(VoiceSession.created_at, VoiceSession.id) < decode_cursor(cursor)
        )
    rows = db.execute(
        query.order_by(VoiceSession.created_at.desc(), VoiceSession.id.desc()).limit(limit + 1)
    ).all()
    items: list[dict[str, object]] = []
    for voice, agent_name, version_number in rows[:limit]:
        last_event = db.scalar(
            select(SessionEvent.created_at)
            .where(SessionEvent.session_id == voice.id)
            .order_by(SessionEvent.created_at.desc(), SessionEvent.id.desc())
            .limit(1)
        )
        items.append(
            {
                **voice_view(voice),
                "agent_name": agent_name,
                "version_number": version_number,
                "last_activity_at": (last_event or voice.created_at).isoformat(),
            }
        )
    next_cursor = (
        encode_cursor(rows[limit - 1][0].created_at, rows[limit - 1][0].id)
        if len(rows) > limit
        else None
    )
    return {"items": items, "next_cursor": next_cursor}


@app.get("/api/console/logs")
def console_logs(
    db: Db,
    login: CurrentSession,
    session_id: UUID | None = None,
    severity: Literal["info", "warning", "error"] | None = None,
    component: str | None = Query(default=None, max_length=32),
    since: datetime | None = None,
    cursor: str | None = Query(default=None, max_length=256),
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict[str, object]:
    can_use_playground(login)
    query = select(SessionDiagnostic).join(
        VoiceSession, SessionDiagnostic.session_id == VoiceSession.id
    )
    if login.user.role != "admin":
        query = query.where(VoiceSession.started_by == login.user_id)
    if session_id:
        query = query.where(SessionDiagnostic.session_id == session_id)
    if severity:
        query = query.where(SessionDiagnostic.severity == severity)
    if component:
        query = query.where(SessionDiagnostic.component == component)
    if since:
        query = query.where(SessionDiagnostic.created_at >= since)
    if cursor:
        query = query.where(
            tuple_(SessionDiagnostic.created_at, SessionDiagnostic.id) < decode_cursor(cursor)
        )
    rows = db.scalars(
        query.order_by(SessionDiagnostic.created_at.desc(), SessionDiagnostic.id.desc()).limit(
            limit + 1
        )
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "session_id": str(row.session_id),
                "severity": row.severity,
                "component": row.component,
                "code": row.code,
                "message": row.message,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows[:limit]
        ],
        "next_cursor": (
            encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id)
            if len(rows) > limit
            else None
        ),
    }
