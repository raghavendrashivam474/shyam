"""Flux Provider Implementation - S7.

Represents a running Flux Gateway instance as a Shyam Provider.
Handles connection, protocol validation, capability advertisement, and
delegation of peer discovery and transfer operations.
"""

from __future__ import annotations

import logging

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.providers.flux.client import FluxClient
from shyam.providers.flux.exceptions import (
    FluxClientError,
    FluxConnectionError,
    FluxProtocolError,
)
from shyam.providers.flux.mapper import (
    EXPECTED_PROTOCOL_VERSION,
    FLUX_CAPABILITY_DEFINITIONS,
    PROVIDER_ID_FLUX,
    map_flux_state_to_availability,
    map_to_shyam_provider,
)
from shyam.providers.flux.models import (
    FluxCancelResponse,
    FluxConnectResponse,
    FluxIdentityResponse,
    FluxPeerInfo,
    FluxStatusResponse,
    FluxTransferResponse,
    FluxTransferStatusResponse,
)
from shyam.providers.model import Provider

logger = logging.getLogger(__name__)


class FluxProvider:
    """Shyam Provider for sovereign Aryntra Flux connectivity.

    Consumes Flux over the Gateway HTTP API (default: http://127.0.0.1:9100/flux/v1).
    Decoupled from Flux source; interacts via the ADR-007 contract.
    """

    def __init__(
        self,
        client: FluxClient | None = None,
        base_url: str = "http://127.0.0.1:9100/flux/v1",
        timeout: float = 10.0,
    ) -> None:
        """Initialize the Flux provider.

        Args:
            client: Optional injected FluxClient for testing.
            base_url: Flux Gateway base URL.
            timeout: Client timeout in seconds.
        """
        self._client = client or FluxClient(
            base_url=base_url,
            timeout=timeout,
        )
        self._identity: FluxIdentityResponse | None = None
        self._status_resp: FluxStatusResponse | None = None
        self._is_connected: bool = False

    @property
    def client(self) -> FluxClient:
        """Return the underlying HTTP protocol client."""
        return self._client

    @property
    def is_connected(self) -> bool:
        """True if successfully connected and protocol validated."""
        return self._is_connected


    @property
    def peer_id(self) -> str | None:
        """Return the Flux peer_id if connected, else None."""
        if self._is_connected and self._identity:
            return self._identity.peer_id
        return None

    @property
    def descriptor(self) -> Provider:
        """Return the frozen Provider model for this Flux instance."""
        if not (self._is_connected and self._identity and self._status_resp):
            return Provider(
                provider_id=PROVIDER_ID_FLUX,
                name="Flux Connectivity (Disconnected)",
                version="0.0.0",
                description="Aryntra Flux provider (not connected)",
                capabilities=(),
                availability=AvailabilityStatus.UNAVAILABLE,
            )

        return map_to_shyam_provider(self._identity, self._status_resp)

    @property
    def capability_definitions(self) -> tuple[Capability, ...]:
        """Tuple of Shyam Capability objects provided by Flux."""
        if not self._is_connected:
            return ()
        return FLUX_CAPABILITY_DEFINITIONS

    def connect(self) -> bool:
        """Connect to Flux Gateway, validate identity and protocol version.

        Returns:
            True if connected and ready, False if unreachable.

        Raises:
            FluxProtocolError: If protocol version is incompatible.
        """
        try:
            self._identity = self._client.get_identity()
            proto_ver = self._identity.protocol_version
            if not proto_ver.startswith(EXPECTED_PROTOCOL_VERSION.split(".")[0]):
                raise FluxProtocolError(
                    f"Incompatible Flux protocol. Expected major "
                    f"'{EXPECTED_PROTOCOL_VERSION}', got '{proto_ver}'"
                )

            self._status_resp = self._client.get_status()
            self._is_connected = True

            logger.info(
                "Connected to Flux peer %s (v%s, state=%s, %d caps)",
                self._identity.peer_id[:8],
                self._identity.version,
                self._status_resp.state.value,
                len(self.capability_definitions),
            )
            return True

        except FluxProtocolError:
            # Protocol mismatch is a hard failure — re-raise so the
            # caller knows the Flux version is incompatible.
            raise

        except (FluxConnectionError, FluxClientError) as e:
            logger.warning("Could not connect to Flux Gateway: %s", e)
            self._is_connected = False
            return False

    def refresh_status(self) -> AvailabilityStatus:
        """Poll latest status from Flux Gateway."""
        if not self._is_connected:
            return AvailabilityStatus.UNAVAILABLE

        try:
            self._status_resp = self._client.get_status()
            return map_flux_state_to_availability(self._status_resp.state)
        except Exception as e:
            logger.warning("Failed to refresh Flux status: %s", e)
            self._is_connected = False
            return AvailabilityStatus.UNAVAILABLE

    # ── High-Level Invokable Operations ──────────────────────────

    def discover_peers(self) -> list[FluxPeerInfo]:
        """Discover peers currently visible to Flux."""
        if not self._is_connected:
            raise FluxConnectionError("FluxProvider is not connected.")
        return self._client.get_peers().peers

    def resolve_peer(self, peer_id: str) -> FluxPeerInfo:
        """Resolve a peer by its Flux PeerId."""
        if not self._is_connected:
            raise FluxConnectionError("FluxProvider is not connected.")
        return self._client.get_peer(peer_id)

    def connect_peer(self, peer_id: str) -> FluxConnectResponse:
        """Establish connectivity to a known peer."""
        if not self._is_connected:
            raise FluxConnectionError("FluxProvider is not connected.")
        return self._client.connect_peer(peer_id)

    def transfer(
        self,
        peer_id: str,
        artifact_path: str,
        artifact_name: str | None = None,
        is_directory: bool = False,
    ) -> FluxTransferResponse:
        """Initiate an artifact transfer via Flux."""
        if not self._is_connected:
            raise FluxConnectionError("FluxProvider is not connected.")
        return self._client.initiate_transfer(
            peer_id=peer_id,
            artifact_path=artifact_path,
            artifact_name=artifact_name,
            is_directory=is_directory,
        )

    def get_transfer_status(
        self,
        transfer_id: str,
    ) -> FluxTransferStatusResponse:
        """Query transfer progress and state."""
        if not self._is_connected:
            raise FluxConnectionError("FluxProvider is not connected.")
        return self._client.get_transfer_status(transfer_id)

    def cancel_transfer(
        self,
        transfer_id: str,
    ) -> FluxCancelResponse:
        """Cancel an in-progress transfer."""
        if not self._is_connected:
            raise FluxConnectionError("FluxProvider is not connected.")
        return self._client.cancel_transfer(transfer_id)
