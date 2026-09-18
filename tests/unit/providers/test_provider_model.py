"""Unit tests for Shyam Provider model - S4."""

import pytest
from pydantic import ValidationError

from shyam.capabilities.model import AvailabilityStatus
from shyam.providers.model import Provider


class TestProviderModel:
    """Tests for Provider dataclass / Pydantic model validation."""

    def test_create_valid_provider_minimal(self) -> None:
        """Create a minimal valid provider with defaults."""
        prov = Provider(
            provider_id="local.filesystem",
            name="Local Filesystem",
        )
        assert prov.provider_id == "local.filesystem"
        assert prov.name == "Local Filesystem"
        assert prov.version == "1.0.0"
        assert prov.description == ""
        assert prov.capabilities == ()
        assert prov.metadata == {}
        assert prov.availability == AvailabilityStatus.REGISTERED

    def test_create_valid_provider_full(self) -> None:
        """Create a fully-specified provider."""
        prov = Provider(
            provider_id="system.terminal",
            name="System Terminal",
            version="2.1.0",
            description="Executes CLI commands locally",
            capabilities=("terminal.execute", "terminal.spawn"),
            metadata={"shell": "powershell", "sandboxed": False},
            availability=AvailabilityStatus.AVAILABLE,
        )
        assert prov.provider_id == "system.terminal"
        assert prov.name == "System Terminal"
        assert prov.version == "2.1.0"
        assert prov.description == "Executes CLI commands locally"
        assert prov.capabilities == ("terminal.execute", "terminal.spawn")
        assert prov.metadata == {"shell": "powershell", "sandboxed": False}
        assert prov.availability == AvailabilityStatus.AVAILABLE

    def test_provider_immutability(self) -> None:
        """Provider models must be frozen / immutable."""
        prov = Provider(
            provider_id="local.filesystem",
            name="Local Filesystem",
        )
        with pytest.raises(ValidationError):
            prov.name = "Modified Name"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "valid_id",
        [
            "a.b",
            "file.read",
            "local.filesystem.v1",
            "system_tool.exec_cmd",
            "zarya.ui.inspector",
        ],
    )
    def test_valid_provider_ids(self, valid_id: str) -> None:
        """Namespaced valid provider identifiers must be accepted."""
        prov = Provider(provider_id=valid_id, name="Test")
        assert prov.provider_id == valid_id

    @pytest.mark.parametrize(
        "invalid_id",
        [
            "",
            "singleword",
            "invalid-hyphen.name",
            "123.starts_with_number",
            ".leading_dot",
            "trailing_dot.",
            "spaces not.allowed",
            "has..double_dots",
        ],
    )
    def test_invalid_provider_ids(self, invalid_id: str) -> None:
        """Invalid provider IDs must raise ValidationError."""
        with pytest.raises(ValidationError):
            Provider(provider_id=invalid_id, name="Test")

    @pytest.mark.parametrize(
        "valid_ver",
        ["1", "1.0", "1.0.0", "0.1.0", "10.20.30"],
    )
    def test_valid_versions(self, valid_ver: str) -> None:
        """Valid version formats must pass validation."""
        prov = Provider(
            provider_id="local.tool",
            name="Test",
            version=valid_ver,
        )
        assert prov.version == valid_ver

    @pytest.mark.parametrize(
        "invalid_ver",
        ["", "1.0.0.0", "v1.0", "1.0.alpha", "-1.0", "1.-2.0"],
    )
    def test_invalid_versions(self, invalid_ver: str) -> None:
        """Invalid version strings must raise ValidationError."""
        with pytest.raises(ValidationError):
            Provider(
                provider_id="local.tool",
                name="Test",
                version=invalid_ver,
            )
