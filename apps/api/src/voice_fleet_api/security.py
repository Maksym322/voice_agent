"""Password and session token primitives."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash
from pydantic import EmailStr, TypeAdapter

from voice_fleet_api.config import Settings

password_hash = PasswordHash.recommended()
email_adapter: TypeAdapter[EmailStr] = TypeAdapter(EmailStr)


def normalize_email(value: str) -> str:
    """Use the same email validation policy for bootstrap and API login."""
    return str(email_adapter.validate_python(value.strip())).lower()


def now_utc() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def expiry(settings: Settings) -> datetime:
    return now_utc() + timedelta(minutes=settings.session_lifetime_minutes)
