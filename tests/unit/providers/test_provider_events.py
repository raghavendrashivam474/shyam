"""Unit tests for Shyam Provider events - S4."""

from shyam.capabilities.model import AvailabilityStatus
from shyam.providers.events import (
    ProviderRegisteredEvent,
    ProviderUnregisteredEvent,
    ProviderUpdatedEvent,
)
from shyam.providers.model import Provider


class TestProviderEvents:
    """Tests for Provider domain events."""

    def test_provider_registered_event(self) -> None:
        """ProviderRegisteredEvent serializes provider specification."""
        prov = Provider(
            provider_id="local.filesystem",
            name="Local Filesystem",
            capabilities=("file.read", "file.write"),
        )
        evt = ProviderRegisteredEvent(
            provider_id=prov.provider_id,
            provider=prov,
        )
        assert evt.provider_id == "local.filesystem"
        assert evt.provider.name == "Local Filesystem"
        assert evt.provider.capabilities == ("file.read", "file.write")

    def test_provider_updated_event(self) -> None:
        """ProviderUpdatedEvent captures updated provider and previous status."""
        prov = Provider(
            provider_id="local.filesystem",
            name="Local Filesystem",
            availability=AvailabilityStatus.AVAILABLE,
        )
        evt = ProviderUpdatedEvent(
            provider_id=prov.provider_id,
            provider=prov,
            previous_availability="registered",
        )
        assert evt.provider_id == "local.filesystem"
        assert evt.provider.availability == AvailabilityStatus.AVAILABLE
        assert evt.previous_availability == "registered"

    def test_provider_unregistered_event(self) -> None:
        """ProviderUnregisteredEvent captures provider ID."""
        evt = ProviderUnregisteredEvent(provider_id="local.filesystem")
        assert evt.provider_id == "local.filesystem"
