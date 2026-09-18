"""Integration tests for ShyamRuntime with Provider Registry - S4."""

import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.providers.events import ProviderRegisteredEvent
from shyam.providers.model import Provider


@pytest.mark.asyncio
async def test_runtime_owns_provider_registry_and_propagates_events(tmp_path) -> None:
    """Runtime owns ProviderRegistry and emits domain events correctly during operation."""
    settings = ShyamSettings(
        data_directory=tmp_path / "shyam_data",
        runtime_name="provider-test-node",
        discovery_enabled=False,
    )

    async with ShyamRuntime(settings=settings) as runtime:
        assert hasattr(runtime, "providers")
        assert runtime.providers.count == 0

        # Capture provider events on runtime event bus
        captured_events = []

        async def on_provider_registered(event: ProviderRegisteredEvent) -> None:
            captured_events.append(event)

        await runtime.events.subscribe(ProviderRegisteredEvent, on_provider_registered)

        # Register synthetic provider
        prov = Provider(
            provider_id="local.fs",
            name="Local Filesystem Provider",
            version="1.0.0",
            capabilities=("file.read", "file.write"),
            availability=AvailabilityStatus.AVAILABLE,
        )
        await runtime.providers.register(prov)

        assert runtime.providers.count == 1
        assert runtime.providers.contains("local.fs")
        assert len(captured_events) == 1
        assert captured_events[0].provider_id == "local.fs"
        assert captured_events[0].provider.capabilities == ("file.read", "file.write")

        # Query provider by capability via runtime's provider registry
        readers = runtime.providers.find_by_capability("file.read")
        assert len(readers) == 1
        assert readers[0].provider_id == "local.fs"
