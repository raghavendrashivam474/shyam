"""Runtime Integration Tests for Zarya Provider - S6."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.providers.zarya.client import ZaryaClient
from shyam.providers.zarya.exceptions import ZaryaConnectionError
from shyam.providers.zarya.models import (
    CapabilitiesResponse,
    CapabilityEntry,
    EcosystemStatus,
    IdentityResponse,
    ProtocolResponse,
    StatusResponse,
)


@pytest.mark.asyncio
async def test_runtime_starts_successfully_when_zarya_is_offline(tmp_path) -> None:
    """Sovereignty validation: Shyam must start standalone even if Zarya is unreachable."""
    settings = ShyamSettings(
        environment="testing",
        data_directory=tmp_path / "shyam_data",
        zarya_enabled=True,
        zarya_url="http://127.0.0.1:9999/ecosystem/v1",  # Non-existent endpoint
        discovery_enabled=False,
    )

    # Force connection failure in the provider's client
    with patch.object(ZaryaClient, "_request", side_effect=ZaryaConnectionError("Unreachable")):
        async with ShyamRuntime(settings=settings) as runtime:
            assert runtime.is_running
            # Confirm Zarya provider is marked as disconnected
            assert not runtime.zarya_provider.is_connected
            assert runtime.zarya_provider.descriptor.availability == AvailabilityStatus.UNAVAILABLE

            # Confirm Zarya is NOT registered in the active provider registry
            assert not runtime.providers.contains("zarya.agent")
            assert runtime.providers.get("zarya.agent") is None


@pytest.mark.asyncio
async def test_runtime_registers_zarya_and_capabilities_when_online(tmp_path) -> None:
    """EIP-1 discovery validation: Active Zarya instances are dynamically registered."""
    settings = ShyamSettings(
        environment="testing",
        data_directory=tmp_path / "shyam_data",
        zarya_enabled=True,
        discovery_enabled=False,
    )

    # Set up mocked client responses matching the EIP-1 contract
    mock_client = MagicMock(spec=ZaryaClient)
    mock_client.get_protocol.return_value = ProtocolResponse(
        current="eip-1.0",
        supported=["eip-1.0"],
    )
    mock_client.get_identity.return_value = IdentityResponse(
        instance_id="zarya-integration-inst",
        product="zarya",
        version="0.9.0",
        protocol="eip-1.0",
        platform="windows",
        architecture="AMD64",
    )
    mock_client.get_capabilities.return_value = CapabilitiesResponse(
        protocol="eip-1.0",
        capabilities=[
            CapabilityEntry(
                id="system.health",
                version="1.0",
                description="Test Health Check",
                operations=["check"],
            ),
            CapabilityEntry(
                id="work.execute",
                version="1.0",
                description="Test Work Execute Check",
                operations=["execute"],
            ),
        ],
        allowed_tools=["getWeather", "listFiles"],
    )
    mock_client.get_status.return_value = StatusResponse(
        status=EcosystemStatus.READY,
        active_operations=0,
    )

    # Initialize runtime and inject mocked client into zarya_provider
    runtime = ShyamRuntime(settings=settings)
    runtime.zarya_provider._client = mock_client

    async with runtime:
        assert runtime.is_running
        assert runtime.zarya_provider.is_connected

        # 1. Verify Zarya provider registry entry (synchronous lookup)
        assert runtime.providers.contains("zarya.agent")
        provider = runtime.providers.get("zarya.agent")
        assert provider is not None
        assert provider.provider_id == "zarya.agent"
        assert provider.availability == AvailabilityStatus.AVAILABLE
        assert "zarya.system.health" in provider.capabilities
        assert "zarya.work.execute" in provider.capabilities

        # 2. Verify Zarya capabilities entered the global CapabilityRegistry
        assert runtime.capabilities.contains("zarya.system.health")
        cap_health = runtime.capabilities.get("zarya.system.health")
        assert cap_health is not None
        assert cap_health.capability_id == "zarya.system.health"
        assert cap_health.metadata["source"] == "zarya-eip1"

        assert runtime.capabilities.contains("zarya.work.execute")
        cap_work = runtime.capabilities.get("zarya.work.execute")
        assert cap_work is not None
        assert cap_work.capability_id == "zarya.work.execute"
