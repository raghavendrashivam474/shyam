"""Flux → Shyam Model Mapper (S7).

Translates Flux Gateway contract models into Shyam's Provider and
Capability representations. Keeps Flux internals out of Shyam core.
"""

from __future__ import annotations

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.providers.flux.models import (
    FluxIdentityResponse,
    FluxNodeState,
    FluxStatusResponse,
)
from shyam.providers.model import Provider

# ── Constants ────────────────────────────────────────────────────

PROVIDER_ID_FLUX = "flux.connectivity"

EXPECTED_PROTOCOL_VERSION = "1.0"

# Semantic capabilities exposed by Flux to Shyam.
# Classified per brief §14:
#   A = independently invokable capability
#   B = provider metadata (not a capability)
#   C = provider status (not a capability)
#   D = implementation detail (not a capability)
#
# Only A-class items become Shyam capabilities.

FLUX_CAPABILITY_DEFINITIONS: tuple[Capability, ...] = (
    Capability(
        capability_id="connectivity.peer_discovery",
        name="Peer Discovery",
        version="1.0.0",
        description="Discover Flux peers on the local network.",
        availability=AvailabilityStatus.AVAILABLE,
    ),
    Capability(
        capability_id="connectivity.peer_resolution",
        name="Peer Resolution",
        version="1.0.0",
        description="Resolve a Flux peer by PeerId to connectivity details.",
        availability=AvailabilityStatus.AVAILABLE,
    ),
    Capability(
        capability_id="connectivity.session",
        name="Connectivity Session",
        version="1.0.0",
        description="Establish a connectivity session to a Flux peer.",
        availability=AvailabilityStatus.AVAILABLE,
    ),
    Capability(
        capability_id="connectivity.transfer",
        name="Artifact Transfer",
        version="1.0.0",
        description="Transfer an artifact to a Flux peer.",
        availability=AvailabilityStatus.AVAILABLE,
    ),
    Capability(
        capability_id="connectivity.transfer_resume",
        name="Resumable Transfer",
        version="1.0.0",
        description="Resume an interrupted artifact transfer.",
        availability=AvailabilityStatus.AVAILABLE,
    ),
)

# Items intentionally NOT registered as capabilities:
#   connectivity.multi_path  → B (provider metadata)
#   connectivity.health      → C (provider status)
#   flux.tcp / flux.quic     → D (implementation detail)


# ── Mapping functions ────────────────────────────────────────────


def map_flux_state_to_availability(
    state: FluxNodeState,
) -> AvailabilityStatus:
    """Map Flux node state to Shyam AvailabilityStatus.

    Note: Shyam's AvailabilityStatus has no DEGRADED member.
    A degraded Flux node is mapped to UNAVAILABLE to prevent
    Shyam from routing operations to a partially-functional provider.
    """
    mapping = {
        FluxNodeState.RUNNING: AvailabilityStatus.AVAILABLE,
        FluxNodeState.LISTENING: AvailabilityStatus.AVAILABLE,
        FluxNodeState.DEGRADED: AvailabilityStatus.UNAVAILABLE,
        FluxNodeState.INITIALIZING: AvailabilityStatus.UNAVAILABLE,
        FluxNodeState.STOPPED: AvailabilityStatus.UNAVAILABLE,
    }
    return mapping.get(state, AvailabilityStatus.UNAVAILABLE)


def map_to_shyam_provider(
    identity: FluxIdentityResponse,
    status: FluxStatusResponse,
) -> Provider:
    """Build a frozen Shyam Provider descriptor from Flux responses."""
    availability = map_flux_state_to_availability(status.state)
    cap_ids = tuple(c.capability_id for c in FLUX_CAPABILITY_DEFINITIONS)

    return Provider(
        provider_id=PROVIDER_ID_FLUX,
        name="Flux Connectivity",
        version=identity.version,
        description=(
            f"Aryntra Flux v{identity.version} — adaptive multi-path P2P connectivity and transfer."
        ),
        capabilities=cap_ids,
        metadata={
            "flux_peer_id": identity.peer_id,
            "flux_protocol_version": identity.protocol_version,
            "flux_discovered_peers": status.discovered_peer_count,
            "flux_active_paths": status.active_path_count,
        },
        availability=availability,
    )
