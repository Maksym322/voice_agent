"""Versioned, secret-free agent configuration contract."""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REFERENCE = re.compile(r"^(env|secret):[A-Za-z][A-Za-z0-9_/-]*$")
FORBIDDEN = re.compile(r"(^|_)(secret|password|token|api_key|credential|private_key)(_|$)", re.I)
SENSITIVE_VALUE = re.compile(
    r"(?i)(sk-[a-z0-9]{16,}|bearer\s+\S+|-----BEGIN .*PRIVATE KEY-----|"
    r"(?:api[_ -]?key|password|token|secret)\s*[:=]\s*\S+)"
)


class VoiceConfig(BaseModel):
    """Supported direct-provider preset, pinned in each published snapshot."""

    model_config = ConfigDict(extra="forbid")

    stt_provider: str = Field(default="deepgram", pattern="^deepgram$")
    stt_model: str = Field(default="nova-3", pattern="^nova-3$")
    llm_provider: Literal["openai", "google"] = "openai"
    llm_model: str = "gpt-4o-mini"
    tts_provider: str = Field(default="cartesia", pattern="^cartesia$")
    tts_model: str = Field(default="sonic-3", pattern="^sonic-3$")
    tts_voice: str = Field(
        default="f786b574-daa5-4673-aa0c-cbe3e8534c02", pattern=r"^[0-9a-f-]{36}$"
    )

    @model_validator(mode="after")
    def validate_llm_pair(self) -> "VoiceConfig":
        supported = {
            "openai": ("gpt-4o-mini",),
            "google": ("gemini-2.5-flash-lite", "gemini-3.5-flash-lite"),
        }
        if self.llm_model not in supported[self.llm_provider]:
            raise ValueError(
                f"voice.llm_model must be one of {', '.join(supported[self.llm_provider])} "
                f"for {self.llm_provider}"
            )
        return self


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1, le=1)
    instructions: str = Field(min_length=1, max_length=20000)
    locale: str = Field(default="en-US", pattern=r"^[a-z]{2,3}-[A-Z]{2}$")
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    provider_references: dict[str, str] = Field(default_factory=dict)
    tool_allowlist: list[str] = Field(default_factory=list, max_length=100)
    enabled_modules: list[str] = Field(default_factory=list, max_length=100)
    branding: dict[str, str] = Field(default_factory=dict)
    session_limit_seconds: int = Field(default=1800, ge=30, le=14400)
    retention_days: int = Field(default=30, ge=0, le=3650)

    @model_validator(mode="after")
    def validate_references(self) -> "AgentConfig":
        if SENSITIVE_VALUE.search(self.instructions):
            raise ValueError("instructions: credential-like values are forbidden")
        for key, value in self.provider_references.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", key) or not REFERENCE.fullmatch(value):
                raise ValueError(f"provider_references.{key}: use an env: or secret: reference")
        for name in (*self.tool_allowlist, *self.enabled_modules):
            if not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
                raise ValueError(f"Invalid module or tool name: {name}")
        for key, value in self.branding.items():
            if FORBIDDEN.search(key):
                raise ValueError(f"branding.{key}: secret fields are forbidden")
            if SENSITIVE_VALUE.search(value):
                raise ValueError(f"branding.{key}: credential-like values are forbidden")
        return self


def parse_config(value: Any) -> dict[str, Any]:
    return AgentConfig.model_validate(value).model_dump(mode="json")
