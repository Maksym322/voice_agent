"""Deployment settings. Client agent configuration belongs to VF-002."""

from functools import lru_cache
from ipaddress import ip_network
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(min_length=1)
    app_origin: str = Field(min_length=1)
    environment: Literal["local", "production"] = "local"
    session_lifetime_minutes: int = Field(default=480, ge=5, le=10080)
    session_secure_cookie: bool = False
    livekit_url: str | None = None
    livekit_browser_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None
    playground_max_seconds: int = Field(default=600, ge=30, le=14400)
    outbound_sip_trunk_id: str | None = None
    outbound_test_destination: str | None = Field(default=None, pattern=r"^\+380\d{9}$")
    outbound_test_max_seconds: int = Field(default=180, ge=30, le=600)
    inbound_sip_allowed_addresses: str | None = None
    console_brand_name: str = Field(default="Voice Fleet", min_length=1, max_length=60)
    console_accent_color: str = Field(default="#0b5960", pattern=r"^#[0-9a-fA-F]{6}$")
    console_default_groups: str = "pending,active,error,ended"
    console_visible_modules: str = "overview,board,history,agents,numbers,logs,settings"

    @field_validator("outbound_test_destination", mode="before")
    @classmethod
    def empty_destination_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if self.inbound_sip_allowed_addresses:
            for address in self.inbound_sip_allowed_addresses.split(","):
                network = ip_network(address.strip(), strict=False)
                if network.prefixlen == 0:
                    raise ValueError(
                        "INBOUND_SIP_ALLOWED_ADDRESSES cannot allow the whole internet"
                    )
        groups = self.console_default_groups.split(",")
        if len(groups) != 4 or set(groups) != {"pending", "active", "error", "ended"}:
            raise ValueError("CONSOLE_DEFAULT_GROUPS must contain each canonical status once")
        modules = self.console_visible_modules.split(",")
        allowed = {"overview", "board", "history", "agents", "numbers", "logs", "settings"}
        if (
            len(modules) != len(set(modules))
            or not set(modules) <= allowed
            or "overview" not in modules
        ):
            raise ValueError("CONSOLE_VISIBLE_MODULES must include overview and only real modules")
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
