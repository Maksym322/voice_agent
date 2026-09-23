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
    ],
)
def test_invalid_config_is_rejected(config: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        parse_config(config)
