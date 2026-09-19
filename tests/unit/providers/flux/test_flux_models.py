"""Unit tests for Flux provider data models (aligned with live Gateway contract S7.1)."""

import pytest
from pydantic import ValidationError

from shyam.providers.flux.exceptions import (
    FluxClientError,
    FluxConnectionError,
    FluxPeerNotFoundError,
    FluxProtocolError,
    FluxTransferError,
    FluxUnavailableError,
)
from shyam.providers.flux.models import (
    FluxCancelResponse,
    FluxConnectRequest,
    FluxConnectResponse,
    FluxErrorDetail,
    FluxIdentityResponse,
    FluxNodeState,
    FluxPathInfo,
    FluxPathState,
    FluxPeerInfo,
    FluxPeersResponse,
    FluxStatusResponse,
    FluxTransferRequest,
    FluxTransferResponse,
    FluxTransferStatus,
    FluxTransferStatusResponse,
    FluxTransportKind,
)


def test_flux_identity_model() -> None:
    resp = FluxIdentityResponse(
        peer_id="peer-123",
        version="0.1.0",
        protocol_version="1.0",
    )
    assert resp.peer_id == "peer-123"
    assert resp.version == "0.1.0"
    assert resp.protocol_version == "1.0"


def test_flux_status_model() -> None:
    resp = FluxStatusResponse(
        state=FluxNodeState.RUNNING,
        peer_id="peer-123",
        discovered_peer_count=2,
        active_path_count=1,
        active_transfer_count=0,
    )
    assert resp.state == FluxNodeState.RUNNING
    assert resp.discovered_peer_count == 2
    assert resp.active_path_count == 1
    assert resp.active_transfer_count == 0


def test_flux_peers_model() -> None:
    path = FluxPathInfo(
        path_id="path-1",
        transport=FluxTransportKind.TCP_LAN,
        remote_addr="192.168.1.50:9000",
        state=FluxPathState.AVAILABLE,
        rtt_ms=1.2,
    )
    # M5 regression: Gateway returns last_seen_secs_ago (float)
    peer = FluxPeerInfo(
        peer_id="peer-456",
        address="192.168.1.50:9000",
        last_seen_secs_ago=0.5,
        paths=[path],
        connectivity="reachable",
    )
    peers_resp = FluxPeersResponse(peers=[peer])
    assert len(peers_resp.peers) == 1
    assert peers_resp.peers[0].peer_id == "peer-456"
    assert peers_resp.peers[0].last_seen_secs_ago == 0.5


def test_flux_transfer_models() -> None:
    # ANOM-001: file_paths list instead of artifact_path
    req = FluxTransferRequest(
        peer_id="peer-123",
        file_paths=["/path/to/test.bin"],
    )
    assert req.peer_id == "peer-123"
    assert req.file_paths == ["/path/to/test.bin"]

    # ANOM-002 & ANOM-003: POST response has no peer_id, SCREAMING_SNAKE_CASE status
    resp = FluxTransferResponse(
        transfer_id="xfer-999",
        status=FluxTransferStatus.RUNNING,
    )
    assert resp.transfer_id == "xfer-999"
    assert resp.status == FluxTransferStatus.RUNNING

    # ANOM-003: GET status matches GatewayTransferInfo
    status_resp = FluxTransferStatusResponse(
        transfer_id="xfer-999",
        peer_id="peer-123",
        status=FluxTransferStatus.RUNNING,
        bytes_transferred=512,
        total_bytes=1024,
        files_transferred=1,
        total_files=2,
    )
    assert status_resp.transfer_id == "xfer-999"
    assert status_resp.bytes_transferred == 512
    assert status_resp.total_bytes == 1024
    assert status_resp.files_transferred == 1
    assert status_resp.total_files == 2

    # ANOM-004: cancel response returns boolean cancelled
    cancel_resp = FluxCancelResponse(
        transfer_id="xfer-999",
        cancelled=True,
    )
    assert cancel_resp.transfer_id == "xfer-999"
    assert cancel_resp.cancelled is True


def test_flux_exceptions_hierarchy() -> None:
    assert issubclass(FluxConnectionError, FluxClientError)
    assert issubclass(FluxProtocolError, FluxClientError)
    assert issubclass(FluxPeerNotFoundError, FluxClientError)
    assert issubclass(FluxTransferError, FluxClientError)
    assert issubclass(FluxUnavailableError, FluxClientError)
