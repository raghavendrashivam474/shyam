"""Unit tests for Shyam Capability domain model."""

import pytest
from pydantic import ValidationError

from shyam.capabilities.model import AvailabilityStatus, Capability


class TestCapabilityModel:
    """Tests for the Capability domain model."""

    def test_valid_capability_creation(self) -> None:
        """Verify capability creation with valid namespaced ID and defaults."""
        cap = Capability(
            capability_id="file.read",
            name="Read File",
        )
        assert cap.capability_id == "file.read"
        assert cap.name == "Read File"
        assert cap.version == "1.0.0"
        assert cap.description == ""
        assert cap.metadata == {}
        assert cap.availability == AvailabilityStatus.REGISTERED

    def test_full_capability_creation(self) -> None:
        """Verify capability creation with all explicit fields."""
        cap = Capability(
            capability_id="system.screen.capture",
            name="Screen Capture",
            version="2.1.0",
            description="Captures active display monitor",
            metadata={"fps": 60, "format": "png"},
            availability=AvailabilityStatus.AVAILABLE,
        )
        assert cap.capability_id == "system.screen.capture"
        assert cap.version == "2.1.0"
        assert cap.metadata["fps"] == 60
        assert cap.availability == AvailabilityStatus.AVAILABLE

    def test_immutability(self) -> None:
        """Capability models must be frozen."""
        cap = Capability(capability_id="file.read", name="Read")
        with pytest.raises(ValidationError):
            cap.name = "Modified"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "invalid_id",
        [
            "",
            "file",
            "file.",
            ".read",
            "file..read",
            "file read",
            "file-read",
            "123.file",
        ],
    )
    def test_invalid_capability_id_rejected(self, invalid_id: str) -> None:
        """Invalid capability IDs must raise ValidationError."""
        with pytest.raises(ValidationError):
            Capability(capability_id=invalid_id, name="Invalid")

    @pytest.mark.parametrize(
        "valid_version",
        ["1", "1.0", "1.0.0", "0.2.1", "10.20.30"],
    )
    def test_valid_version_strings(self, valid_version: str) -> None:
        """Valid version formats should be accepted."""
        cap = Capability(
            capability_id="test.cap",
            name="Test",
            version=valid_version,
        )
        assert cap.version == valid_version

    @pytest.mark.parametrize(
        "invalid_version",
        ["", "v1.0.0", "1.0.0.0", "beta", "1.a.0", "-1.0.0"],
    )
    def test_invalid_version_rejected(self, invalid_version: str) -> None:
        """Invalid version formats must raise ValidationError."""
        with pytest.raises(ValidationError):
            Capability(
                capability_id="test.cap",
                name="Test",
                version=invalid_version,
            )
