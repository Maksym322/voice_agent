"""Voice Fleet HTTP API."""

import hmac
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from voice_fleet_api.agent_schema import AgentConfig, parse_config
from voice_fleet_api.config import Settings, get_settings
from voice_fleet_api.db import get_db
from voice_fleet_api.models import (
    Agent,
    AgentVersion,
    AuditEvent,
    DeploymentBinding,
    LoginSession,
    User,
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


app = FastAPI(title="Voice Fleet API", version="0.1.0")


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
    if revision != "0002_agent_configurations":
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


def agent_view(agent: Agent) -> dict[str, object]:
    return {
        "id": str(agent.id),
        "name": agent.name,
        "revision": agent.revision,
        "config": agent.draft,
    }


@app.get("/api/agents")
def list_agents(db: Db, session: CurrentSession) -> list[dict[str, object]]:
    return [agent_view(agent) for agent in db.scalars(select(Agent).order_by(Agent.name)).all()]


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
    return agent_view(get_agent(db, agent_id))


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
