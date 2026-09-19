"""Integration tests for Shyam Runtime ↔ Flux Provider integration (S7)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.core.config import ShyamSettings
from shyam.core.lifecycle import LifecycleState
from shyam.core.runtime import ShyamRuntime
from shyam.providers.flux.mapper import PROVIDER_ID_FLUX


def _mock_http_response(status: int = 200, json_data: dict | None = None) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status = status
    body = json.dumps(json_data or {}).encode("utf-8")
    mock_resp.read.return_value = body
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


@pytest.mark.asyncio
async def test_runtime_starts_successfully_when_flux_is_offline(tmp_path) -> None:
    """If Flux Gateway is offline, Shyam starts standalone without crashing."""
    settings = ShyamSettings(
        data_directory=tmp_path,
        zarya_enabled=False,
        flux_enabled=True,
        flux_url="http://127.0.0.1:9999/flux/v1",  # Unreachable
        discovery_enabled=False,
    )
    runtime = ShyamRuntime(settings=settings)
    await runtime.start()

    try:
        assert runtime.status == LifecycleState.RUNNING
        assert not runtime.providers.contains(PROVIDER_ID_FLUX)
        # Local introspection capability remains functional
        assert runtime.capabilities.contains("shyam.runtime.inspect")
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_registers_flux_and_capabilities_when_online(tmp_path) -> None:
    """When Flux Gateway is reachable, runtime registers provider and 5 capabilities."""
    settings = ShyamSettings(
        data_directory=tmp_path,
        zarya_enabled=False,
        flux_enabled=True,
        discovery_enabled=False,
    )
    runtime = ShyamRuntime(settings=settings)

    identity_payload = {
        "peer_id": "550e8400-e29b-41d4-a716-446655440000",
        "version": "2.3.0",
        "protocol_version": "1.0",
    }
    status_payload = {
        "state": "running",
        "peer_id": "550e8400-e29b-41d4-a716-446655440000",
        "discovered_peer_count": 2,
        "active_path_count": 3,
        "active_transfer_count": 0,
    }

    def mock_urlopen(req, timeout=10.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/identity" in url:
            return _mock_http_response(200, identity_payload)
        if "/status" in url:
            return _mock_http_response(200, status_payload)
        return _mock_http_response(404, {"error": "not found"})

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        await runtime.start()

    try:
        assert runtime.status == LifecycleState.RUNNING
        assert runtime.providers.contains(PROVIDER_ID_FLUX)

        provider = runtime.providers.get(PROVIDER_ID_FLUX)
        assert provider is not None
        assert provider.version == "2.3.0"
        assert provider.availability == AvailabilityStatus.AVAILABLE

        # Verify all 5 semantic capabilities were registered into runtime
        assert runtime.capabilities.contains("connectivity.peer_discovery")
        assert runtime.capabilities.contains("connectivity.peer_resolution")
        assert runtime.capabilities.contains("connectivity.session")
        assert runtime.capabilities.contains("connectivity.transfer")
        assert runtime.capabilities.contains("connectivity.transfer_resume")
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_skips_flux_when_disabled(tmp_path) -> None:
    """When flux_enabled=False, runtime bypasses Flux connection entirely."""
    settings = ShyamSettings(
        data_directory=tmp_path,
        zarya_enabled=False,
        flux_enabled=False,
        discovery_enabled=False,
    )
    runtime = ShyamRuntime(settings=settings)
    await runtime.start()

    try:
        assert runtime.status == LifecycleState.RUNNING
        assert not runtime.providers.contains(PROVIDER_ID_FLUX)
    finally:
        await runtime.stop()
