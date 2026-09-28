"""Secret-free agent configuration validation."""

import pytest
from pydantic import ValidationError
from voice_fleet_api.agent_schema import parse_config


def test_valid_config_normalizes_defaults() -> None:
    config = parse_config(
        {
            "schema_version": 1,
            "instructions": "Help callers",
            "provider_references": {"llm": "env:LLM_KEY"},
        }
    )
    assert config["timezone"] == "UTC"
    assert config["provider_references"] == {"llm": "env:LLM_KEY"}
    assert config["voice"]["stt_model"] == "nova-3"


@pytest.mark.parametrize("model", ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite"])
def test_google_llm_choice_is_validated_without_a_raw_key(model: str) -> None:
    config = parse_config(
        {
            "instructions": "Help callers",
            "voice": {"llm_provider": "google", "llm_model": model},
            "provider_references": {"llm_api_key": "env:GOOGLE_API_KEY"},
        }
    )
    assert config["voice"]["llm_model"] == model
    assert "GOOGLE_API_KEY" not in str(config["voice"])


@pytest.mark.parametrize(
    "config",
    [
        {"instructions": ""},
        {"schema_version": 2, "instructions": "Hello"},
        {"instructions": "Hello", "provider_references": {"llm": "raw-secret"}},
        {"instructions": "Hello", "api_key": "bad"},
        {"instructions": "Hello", "branding": {"api_key": "bad"}},
        {"instructions": "API key: abc123"},
        {"instructions": "Hello", "branding": {"title": "Bearer abc123"}},
        {"instructions": "Hello", "voice": {"llm_model": "unapproved-model"}},
        {"instructions": "Hello", "voice": {"llm_provider": "google"}},
        {"instructions": "Hello", "voice": {"llm_provider": "google", "llm_model": "gpt-4o-mini"}},
    ],
)
def test_invalid_config_is_rejected(config: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        parse_config(config)
