"""Unit tests for Shyam runtime configuration."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from shyam.core.config import ShyamSettings


def test_default_settings():
    """Verify default configuration values."""
    settings = ShyamSettings()
    assert settings.environment == "local"
    assert settings.data_directory == Path.home() / ".shyam"
    assert settings.log_level == "INFO"
    assert settings.runtime_name == "shyam-core"


def test_custom_settings():
    """Verify custom configuration initialization."""
    custom_path = Path("/tmp/custom_shyam")
    settings = ShyamSettings(
        environment="testing",
        data_directory=custom_path,
        log_level="DEBUG",
        runtime_name="test-node-1",
    )
    assert settings.environment == "testing"
    assert settings.data_directory == custom_path
    assert settings.log_level == "DEBUG"
    assert settings.runtime_name == "test-node-1"


def test_settings_immutability():
    """Verify settings model is frozen."""
    settings = ShyamSettings()
    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"  # type: ignore[misc]


def test_invalid_log_level():
    """Verify validation failure on invalid log level."""
    with pytest.raises(ValidationError):
        ShyamSettings(log_level="INVALID_LEVEL")  # type: ignore[arg-type]


def test_invalid_environment():
    """Verify validation failure on invalid environment."""
    with pytest.raises(ValidationError):
        ShyamSettings(environment="staging_invalid")  # type: ignore[arg-type]
