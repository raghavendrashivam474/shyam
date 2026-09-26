"""Zarya Provider Implementation - S6.

Represents a running Zarya sovereign instance as a Shyam Provider.
Handles connection, protocol validation, capability discovery, and
delegation of permitted tool operations.
"""

from __future__ import annotations

import logging
from typing import Any

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.providers.model import Provider
from shyam.providers.zarya.client import ZaryaClient
from shyam.providers.zarya.exceptions import (
    ZaryaClientError,
    ZaryaConnectionError,
    ZaryaProtocolError,
)
from shyam.providers.zarya.mapper import (
    EXPECTED_PROTOCOL,
    PROVIDER_ID_ZARYA,
    map_capabilities_response,
    map_ecosystem_status_to_availability,
    map_to_shyam_provider,
)
from shyam.providers.zarya.models import (
    CapabilitiesResponse,
    IdentityResponse,
    StatusResponse,
    WorkExecuteResponse,
    ContinuationResponse,
)

logger = logging.getLogger(__name__)


class ZaryaProvider:
    """Shyam Provider for sovereign Zarya instances.

    Consumes Zarya over EIP-1 (HTTP over localhost:8765).
    Decoupled from Zarya source; interacts via the EIP-1 contract.
    """

    def __init__(
        self,
        client: ZaryaClient | None = None,
        base_url: str = "http://127.0.0.1:8765/ecosystem/v1",
        token: str | None = None,
    ) -> None:
        """Initialize the Zarya provider.

        Args:
            client: Optional injected ZaryaClient for testing.
            base_url: Ecosystem base URL.
            token: Ecosystem auth token.
        """
        self._client = client or ZaryaClient(
            base_url=base_url,
            token=token,
        )
        self._identity: IdentityResponse | None = None
        self._capabilities_resp: CapabilitiesResponse | None = None
        self._status_resp: StatusResponse | None = None
        self._discovered_capabilities: list[Capability] = []
        self._is_connected: bool = False

    @property
    def client(self) -> ZaryaClient:
        """Return the underlying HTTP protocol client."""
        return self._client

    @property
    def is_connected(self) -> bool:
        """True if successfully connected and protocol validated."""
        return self._is_connected

    @property
    def descriptor(self) -> Provider:
        """Return the frozen Provider model for this Zarya instance."""
        has_all = (
            self._is_connected
            and self._identity is not None
            and self._capabilities_resp is not None
            and self._status_resp is not None
        )
        if not has_all:
            return Provider(
                provider_id=PROVIDER_ID_ZARYA,
                name="Zarya (Disconnected)",
                version="0.0.0",
                description="Zarya instance (not connected)",
                capabilities=(),
                availability=AvailabilityStatus.UNAVAILABLE,
            )

        return map_to_shyam_provider(
            self._identity,
            self._capabilities_resp,
            self._status_resp,
        )

    @property
    def capability_definitions(self) -> tuple[Capability, ...]:
        """Tuple of Shyam Capability objects discovered from Zarya."""
        return tuple(self._discovered_capabilities)

    def connect(self) -> bool:
        """Connect to Zarya, validate protocol, discover capabilities.

        Returns:
            True if connected and ready, False if unreachable.

        Raises:
            ZaryaProtocolError: If protocol is incompatible.
        """
        try:
            proto = self._client.get_protocol()
            if EXPECTED_PROTOCOL not in proto.supported and proto.current != EXPECTED_PROTOCOL:
                raise ZaryaProtocolError(
                    f"Incompatible protocol. Expected '{EXPECTED_PROTOCOL}', got '{proto.current}'"
                )

            self._identity = self._client.get_identity()
            self._capabilities_resp = self._client.get_capabilities()
            self._discovered_capabilities = map_capabilities_response(
                self._capabilities_resp,
            )
            self._status_resp = self._client.get_status()

            self._is_connected = True
            logger.info(
                "Connected to Zarya %s (v%s, %s, %d caps)",
                self._identity.instance_id[:8],
                self._identity.version,
                self._status_resp.status.value,
                len(self._discovered_capabilities),
            )
            return True

        except (ZaryaConnectionError, ZaryaClientError) as e:
            logger.warning("Could not connect to Zarya: %s", e)
            self._is_connected = False
            return False

    def refresh_status(self) -> AvailabilityStatus:
        """Poll latest status from Zarya."""
        if not self._is_connected:
            return AvailabilityStatus.UNAVAILABLE

        try:
            self._status_resp = self._client.get_status()
            return map_ecosystem_status_to_availability(
                self._status_resp.status,
            )
        except Exception as e:
            logger.warning("Failed to refresh Zarya status: %s", e)
            self._is_connected = False
            return AvailabilityStatus.UNAVAILABLE

    def execute(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
    ) -> WorkExecuteResponse:
        """Execute a permitted tool through Zarya's work pipeline.

        Args:
            tool: Tool name (must be in allowed_tools).
            args: Optional tool arguments.

        Returns:
            WorkExecuteResponse with outcome and result.

        Raises:
            ZaryaToolNotAllowedError: If tool is not allowed.
            ZaryaVerificationError: If verification failed.
            ZaryaClientError: On transport/protocol errors.
        """
        if not self._is_connected:
            raise ZaryaConnectionError(
                "ZaryaProvider is not connected.",
            )

        return self._client.execute_work(tool, args)

    def continue_work(
        self,
        portable_work: dict[str, Any],
        source_device_id: str = "",
        continuity_id: str = "",
        target_url: str | None = None,
    ) -> ContinuationResponse:
        """Invoke Zarya N4 continue_portable_work on this target or a remote target_url.

        Delegates to the underlying ZaryaClient.continue_work().
        If target_url is provided, routes to that target.

        Args:
            portable_work: PortableWork dict from Zarya N3.
            source_device_id: S13 device ID of the source node.
            continuity_id: S16 continuity attempt ID.
            target_url: Optional remote Zarya EIP-1 base URL.

        Returns:
            ContinuationResponse with outcome and execution details.

        Raises:
            ZaryaConnectionError: If not connected and no target_url.
            ZaryaClientError: On transport/protocol errors.
        """
        if target_url:
            from shyam.providers.zarya.client import ZaryaClient
            # Create a target-aware client using the same token
            client = ZaryaClient(
                base_url=target_url,
                token=self._client.token,
            )
            return client.continue_work(
                portable_work=portable_work,
                source_device_id=source_device_id,
                continuity_id=continuity_id,
            )

        if not self._is_connected:
            raise ZaryaConnectionError(
                "ZaryaProvider is not connected.",
            )

        return self._client.continue_work(
            portable_work=portable_work,
            source_device_id=source_device_id,
            continuity_id=continuity_id,
        )