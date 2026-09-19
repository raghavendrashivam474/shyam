"""Unit tests for Flux → Shyam mapper."""

from shyam.capabilities.model import AvailabilityStatus
from shyam.providers.flux.mapper import (
    FLUX_CAPABILITY_DEFINITIONS,
    PROVIDER_ID_FLUX,
    map_flux_state_to_availability,
    map_to_shyam_provider,
)
from shyam.providers.flux.models import (
    FluxIdentityResponse,
    FluxNodeState,
    FluxStatusResponse,
)


def test_map_flux_state_to_availability() -> None:
    assert map_flux_state_to_availability(FluxNodeState.RUNNING) == AvailabilityStatus.AVAILABLE
    assert map_flux_state_to_availability(FluxNodeState.LISTENING) == AvailabilityStatus.AVAILABLE

    # Shyam has no DEGRADED status; degraded Flux maps to UNAVAILABLE
    assert (
        map_flux_state_to_availability(FluxNodeState.DEGRADED) == AvailabilityStatus.UNAVAILABLE
    )
    assert (
        map_flux_state_to_availability(FluxNodeState.INITIALIZING)
        == AvailabilityStatus.UNAVAILABLE
    )
    assert (
        map_flux_state_to_availability(FluxNodeState.STOPPED) == AvailabilityStatus.UNAVAILABLE
    )


def test_map_to_shyam_provider() -> None:
    identity = FluxIdentityResponse(
        peer_id="550e8400-e29b-41d4-a716-446655440000",
        version="2.3.0",
        protocol_version="1.0",
    )
    status = FluxStatusResponse(
        state=FluxNodeState.RUNNING,
        peer_id="550e8400-e29b-41d4-a716-446655440000",
        discovered_peer_count=2,
        active_path_count=4,
        active_transfer_count=0,
    )

    provider = map_to_shyam_provider(identity, status)
    assert provider.provider_id == PROVIDER_ID_FLUX
    assert provider.version == "2.3.0"
    assert provider.availability == AvailabilityStatus.AVAILABLE
    assert "connectivity.peer_discovery" in provider.capabilities
    assert "connectivity.transfer" in provider.capabilities
    assert provider.metadata["flux_peer_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert provider.metadata["flux_discovered_peers"] == 2
    assert provider.metadata["flux_active_paths"] == 4


def test_flux_capabilities_contract() -> None:
    """Ensure all registered capabilities conform to Shyam standards."""
    assert len(FLUX_CAPABILITY_DEFINITIONS) == 5
    for cap in FLUX_CAPABILITY_DEFINITIONS:
        assert cap.capability_id.startswith("connectivity.")
        assert cap.availability == AvailabilityStatus.AVAILABLE
        assert cap.name
        assert cap.description
