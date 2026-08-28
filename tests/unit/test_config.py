"""Unit tests for configuration contract and validation (§DS-06)."""

from pathlib import Path
import pytest
from pydantic import ValidationError
from scraper.config import Settings, get_default_version


def test_default_version_from_metadata():
    """Verify app_version reads dynamically from metadata or fallback."""
    version = get_default_version()
    assert isinstance(version, str)
    assert len(version) > 0


def test_production_mode_rejects_default_secret():
    """Verify production environment fails fast if dev-secret or empty key is used (§DS-06)."""
    with pytest.raises(ValidationError, match="forbids default or empty API_KEY"):
        Settings(app_env="production", api_key="dev-secret")

    with pytest.raises(ValidationError, match="forbids default or empty API_KEY"):
        Settings(app_env="production", api_key="")

    # Valid production key passes
    prod_settings = Settings(
        app_env="production", api_key="super-secure-production-key-12345"
    )
    assert prod_settings.app_env == "production"
    assert prod_settings.api_key == "super-secure-production-key-12345"


def test_env_example_loads_and_maps_every_variable():
    """Verify every configuration item in .env.example maps to a typed Settings field (§DS-06)."""
    env_example_path = Path(".env.example")
    assert env_example_path.exists(), ".env.example must exist"

    lines = env_example_path.read_text(encoding="utf-8").splitlines()
    parsed_env = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            parsed_env[key.strip()] = val.strip()

    # Verify that Settings initializes cleanly with all parsed values from .env.example
    settings_instance = Settings(
        **{k.lower(): v for k, v in parsed_env.items() if v != ""}
    )
    assert settings_instance.api_host == "0.0.0.0"
    assert settings_instance.api_port == 8080
    assert settings_instance.orchestration_backend == "axiom"


@pytest.mark.parametrize(
    "field, invalid_val",
    [
        ("api_port", 0),
        ("api_port", 70000),
        ("max_download_size_mb", 0),
        ("max_download_size_mb", 5000),
        ("browser_max_concurrency", 0),
        ("browser_timeout_seconds", 0.0),
        ("rate_limit_rps", 0.0),
        ("rate_limit_burst", 0),
    ],
)
def test_bounded_ranges_rejected(field, invalid_val):
    """Verify out-of-range limits are rejected by Pydantic validation."""
    with pytest.raises(ValidationError):
        Settings(**{field: invalid_val})
