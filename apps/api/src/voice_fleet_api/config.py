"""Deployment settings. Client agent configuration belongs to VF-002."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(min_length=1)
    app_origin: str = Field(min_length=1)
    environment: Literal["local", "production"] = "local"
    session_lifetime_minutes: int = Field(default=480, ge=5, le=10080)
    session_secure_cookie: bool = False

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if "placeholder" in self.database_url.lower() or "changeme" in self.database_url.lower():
            raise ValueError("DATABASE_URL contains a placeholder")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use PostgreSQL with psycopg")
        if self.environment == "production":
            if not self.session_secure_cookie or not self.app_origin.startswith("https://"):
                raise ValueError("Production requires HTTPS APP_ORIGIN and secure session cookies")
        elif not self.app_origin.startswith("http://localhost:") and not self.app_origin.startswith(
            "http://127.0.0.1:"
        ):
            raise ValueError("Local APP_ORIGIN must be a localhost HTTP origin")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
