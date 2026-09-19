"""Integration tests for ShyamRuntime and LocalProviderFabric - S5."""

from pathlib import Path

import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime


@pytest.mark.asyncio
async def test_runtime_starts_with_local_providers(tmp_path: Path) -> None:
    settings = ShyamSettings(
        data_directory=tmp_path / "data",
        discovery_enabled=False,
    )
    runtime = ShyamRuntime(settings=settings)

    assert runtime.providers.count == 0

    async with runtime:
        assert runtime.is_running
        assert runtime.providers.count == 1
        assert runtime.providers.contains("local.filesystem")

        assert runtime.capabilities.contains("file.read")
        assert runtime.capabilities.contains("file.write")
        assert runtime.capabilities.contains("file.list")

        providers_with_read = runtime.providers.find_by_capability("file.read")
        assert len(providers_with_read) == 1
        assert providers_with_read[0].provider_id == "local.filesystem"
        assert providers_with_read[0].availability == AvailabilityStatus.AVAILABLE

    assert not runtime.is_running
    assert runtime.provider_fabric.provider_count == 0
