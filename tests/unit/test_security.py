"""Security and deployment setting invariants without external services."""

import pytest
from pydantic import ValidationError
from voice_fleet_api.config import Settings
from voice_fleet_api.security import (
    digest,
    hash_password,
    new_token,
    normalize_email,
    verify_password,
)

DB = "postgresql+psycopg://user:secret@localhost:5432/voice_fleet_test"


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    encoded = hash_password("a long synthetic password")
    assert encoded != "a long synthetic password"
    assert verify_password("a long synthetic password", encoded)
    assert not verify_password("wrong password", encoded)
    with pytest.raises(ValueError, match="12"):
        hash_password("short")


def test_bootstrap_email_matches_login_validation() -> None:
    assert normalize_email(" Admin@Example.COM ") == "admin@example.com"
    with pytest.raises(ValidationError):
        normalize_email("admin@example.test")


def test_session_tokens_are_random_and_digest_only() -> None:
    first, second = new_token(), new_token()
    assert first != second
    assert len(first) >= 32
    assert digest(first) != first
    assert digest(first) != digest(second)


def test_production_requires_https_and_secure_cookie() -> None:
    with pytest.raises(ValidationError, match="Production"):
        Settings(database_url=DB, app_origin="http://localhost:8080", environment="production")
    production = Settings(
        database_url=DB,
        app_origin="https://fleet.example",
        environment="production",
        session_secure_cookie=True,
    )
    assert production.session_secure_cookie


def test_database_placeholder_is_rejected() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        Settings(database_url=DB.replace("secret", "CHANGEME"), app_origin="http://localhost:8080")
