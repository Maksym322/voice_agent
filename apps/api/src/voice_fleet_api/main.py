"""VF-001 HTTP API."""

import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from voice_fleet_api.config import Settings, get_settings
from voice_fleet_api.db import get_db
from voice_fleet_api.models import LoginSession, User
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
    if revision != "0001_foundation":
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
