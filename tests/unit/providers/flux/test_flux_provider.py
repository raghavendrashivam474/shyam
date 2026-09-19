"""Unit tests for FluxProvider."""

from unittest.mock import MagicMock

import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.providers.flux.client import FluxClient
from shyam.providers.flux.exceptions import FluxConnectionError, FluxProtocolError
from shyam.providers.flux.models import (
    FluxCancelResponse,
    FluxConnectResponse,
    FluxIdentityResponse,
    FluxNodeState,
    FluxPeerInfo,
    FluxPeersResponse,
    FluxStatusResponse,
    FluxTransferResponse,
    FluxTransferStatus,
    FluxTransferStatusResponse,
)
from shyam.providers.flux.provider import FluxProvider


def _make_mock_client(
    identity: FluxIdentityResponse | None = None,
    status: FluxStatusResponse | None = None,
) -> MagicMock:
    client = MagicMock(spec=FluxClient)
    client.get_identity.return_value = identity or FluxIdentityResponse(
        peer_id="550e8400-e29b-41d4-a716-446655440000",
        version="2.3.0",
        protocol_version="1.0",
    )
    client.get_status.return_value = status or FluxStatusResponse(
        state=FluxNodeState.RUNNING,
        peer_id="550e8400-e29b-41d4-a716-446655440000",
        discovered_peer_count=1,
        active_path_count=2,
        active_transfer_count=0,
    )
    return client


def test_flux_provider_disconnected_state() -> None:
    provider = FluxProvider()
    assert not provider.is_connected
    assert provider.capability_definitions == ()
    descriptor = provider.descriptor
    assert descriptor.provider_id == "flux.connectivity"
    assert descriptor.availability == AvailabilityStatus.UNAVAILABLE
    assert descriptor.version == "0.0.0"

    with pytest.raises(FluxConnectionError):
        provider.discover_peers()


def test_flux_provider_connect_success() -> None:
    client = _make_mock_client()
    provider = FluxProvider(client=client)

    success = provider.connect()
    assert success is True
    assert provider.is_connected is True
    assert len(provider.capability_definitions) == 5

    descriptor = provider.descriptor
    assert descriptor.availability == AvailabilityStatus.AVAILABLE
    assert descriptor.version == "2.3.0"
    assert "connectivity.peer_discovery" in descriptor.capabilities


def test_flux_provider_connect_failure() -> None:
    client = MagicMock(spec=FluxClient)
    client.get_identity.side_effect = FluxConnectionError("Gateway down")

    provider = FluxProvider(client=client)
    success = provider.connect()
    assert success is False
    assert provider.is_connected is False
    assert provider.descriptor.availability == AvailabilityStatus.UNAVAILABLE


def test_flux_provider_protocol_incompatible() -> None:
    client = MagicMock(spec=FluxClient)
    client.get_identity.return_value = FluxIdentityResponse(
        peer_id="p-1",
        version="2.3.0",
        protocol_version="99.0",  # Incompatible major
    )

    provider = FluxProvider(client=client)
    with pytest.raises(FluxProtocolError) as exc_info:
        provider.connect()
    assert "Incompatible Flux protocol" in str(exc_info.value)
    # Provider must NOT be marked connected after protocol failure
    assert provider.is_connected is False


def test_flux_provider_refresh_status() -> None:
    client = _make_mock_client()
    provider = FluxProvider(client=client)
    provider.connect()

    # Change mock status to Degraded (maps to UNAVAILABLE in Shyam)
    client.get_status.return_value = FluxStatusResponse(
        state=FluxNodeState.DEGRADED,
        peer_id="550e8400-e29b-41d4-a716-446655440000",
    )

    new_avail = provider.refresh_status()
    assert new_avail == AvailabilityStatus.UNAVAILABLE


def test_flux_provider_delegated_operations() -> None:
    client = _make_mock_client()
    client.get_peers.return_value = FluxPeersResponse(
        peers=[FluxPeerInfo(peer_id="p-remote", connectivity="reachable")]
    )
    client.get_peer.return_value = FluxPeerInfo(peer_id="p-remote", connectivity="reachable")

    conn_val = FluxConnectResponse(peer_id="p-remote", connected=True, active_path_count=1)
    client.connect_peer.return_value = conn_val

    init_val = FluxTransferResponse(
        transfer_id="t-1", peer_id="p-remote", status=FluxTransferStatus.QUEUED
    )
    client.initiate_transfer.return_value = init_val

    status_val = FluxTransferStatusResponse(
        transfer_id="t-1",
        peer_id="p-remote",
        status=FluxTransferStatus.COMPLETED,
        progress_percent=100.0,
    )
    client.get_transfer_status.return_value = status_val

    cancel_val = FluxCancelResponse(transfer_id="t-1", status=FluxTransferStatus.CANCELLED)
    client.cancel_transfer.return_value = cancel_val

    provider = FluxProvider(client=client)
    provider.connect()

    peers = provider.discover_peers()
    assert len(peers) == 1
    assert peers[0].peer_id == "p-remote"

    peer = provider.resolve_peer("p-remote")
    assert peer.peer_id == "p-remote"

    conn = provider.connect_peer("p-remote")
    assert conn.connected is True

    xfer = provider.transfer("p-remote", "/data/artifact.tar.gz")
    assert xfer.transfer_id == "t-1"

    status = provider.get_transfer_status("t-1")
    assert status.status == FluxTransferStatus.COMPLETED

    cancelled = provider.cancel_transfer("t-1")
    assert cancelled.status == FluxTransferStatus.CANCELLED
