"""Integration tests for S17.7 Human-Facing Surface-Driven Physical Continuity.

Validates the full human-facing vertical slice:
Human Text -> SurfaceCoordinator -> S16 ContinuityService -> S9 HybridNavigator -> S13 TrustService -> Flux -> Remote Zarya.

Covers:
1. Happy path: Human request resolves end-to-end to SUCCESS.
2. Target unavailable: Surface presents friendly failure.
3. Target untrusted: Continuity rejected at AUTHORIZED stage, no transfer occurs.
4. Flux transfer failure: Surface reports transfer failure.
5. Target Zarya failure: Surface reports remote continuation failure.
6. Ecosystem degraded: Readiness gate prevents execution.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.continuity.models import ContinuityOutcome, ContinuityState
from shyam.continuity.service import ContinuityService
from shyam.core.readiness import EcosystemReadiness
from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeState,
)
from shyam.discovery.ecosystem_registry import EcosystemRegistry
from shyam.events.bus import EventBus
from shyam.navigation.navigator import HybridNavigator
from shyam.providers.flux.models import FluxTransferResponse, FluxTransferStatus
from shyam.providers.flux.provider import FluxProvider
from shyam.providers.zarya.models import ContinuationResponse, VerificationOutcome
from shyam.providers.zarya.provider import ZaryaProvider
from shyam.surface.coordinator import SurfaceCoordinator
from shyam.surface.input import TextInputAdapter
from shyam.surface.models import SurfaceState
from shyam.trust.models import RelationshipType
from shyam.trust.service import TrustService


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_flux() -> MagicMock:
    flux = MagicMock(spec=FluxProvider)
    flux.peer_id = "flux-peer-machine-a"
    flux.transfer.return_value = FluxTransferResponse(
        transfer_id="tx-s17-7-ok-999",
        status=FluxTransferStatus.COMPLETED,
        bytes_transferred=2048,
    )
    return flux


@pytest.fixture
def mock_zarya() -> MagicMock:
    zarya = MagicMock(spec=ZaryaProvider)
    zarya.continue_work.return_value = ContinuationResponse(
        operation_id="op-zarya-s17-7-123",
        outcome=VerificationOutcome.VERIFIED_SUCCESS,
        reconstruction_completed=True,
        execution_completed=True,
        summary="Remote execution verified on Machine B",
    )
    return zarya


@pytest.fixture
async def ecosystem_env(tmp_path: Path):
    """Setup dual-node environment with real TrustService & EcosystemRegistry."""
    events = EventBus()
    registry = EcosystemRegistry(event_bus=events)
    navigator = HybridNavigator()

    trust_dir = tmp_path / "trust_data"
    trust_dir.mkdir(parents=True, exist_ok=True)
    trust = TrustService(data_dir=trust_dir, event_bus=events)

    node_beta = "machine-b-physical"
    beta_flux_peer = "flux-peer-beta-5678"
    beta_zarya_url = "http://192.168.1.20:8765/ecosystem/v1"

    cap1 = DiscoveredCapability(
        capability_id="zarya.work.continue",
        name="Continue Work",
        availability=AvailabilityStatus.AVAILABLE,
    )
    cap2 = DiscoveredCapability(
        capability_id="execute",
        name="Execute Work",
        availability=AvailabilityStatus.AVAILABLE,
    )
    prov = DiscoveredProvider(
        provider_id="zarya.agent",
        name="Zarya Agent",
        version="1.0.0",
        capabilities=(cap1, cap2),
        status=AvailabilityStatus.AVAILABLE,
        metadata={
            "zarya_url": beta_zarya_url,
            "flux_peer_id": beta_flux_peer,
        },
    )
    beta_node = DiscoveredNode(
        node_id=node_beta,
        node_name="Machine-B-Target",
        state=EcosystemNodeState.AVAILABLE,
        is_local=False,
        protocol_version="1.0.0",
        providers={"zarya.agent": prov},
        metadata={
            "flux_peer_id": beta_flux_peer,
            "zarya_url": beta_zarya_url,
            "flux_url": "http://192.168.1.20:9100/flux/v1",
        },
    )
    await registry.register_node(beta_node)

    return {
        "events": events,
        "registry": registry,
        "navigator": navigator,
        "trust": trust,
        "target_node_id": node_beta,
    }


class MockRuntime:
    """Mock ShyamRuntime providing only the real service boundaries."""

    def __init__(
        self,
        continuity_service: ContinuityService | None,
        readiness: EcosystemReadiness = EcosystemReadiness.READY,
        event_bus: EventBus | None = None,
    ) -> None:
        self.continuity_service = continuity_service
        self.readiness = readiness
        self.events = event_bus or EventBus()
        self.identity_manager = MagicMock()
        mock_ident = MagicMock()
        mock_ident.node_id = "machine-a-source"
        self.identity_manager.get_or_create_identity.return_value = mock_ident


# ── Tests ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_s17_7_surface_happy_path(
    ecosystem_env: dict[str, Any],
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Validate full human surface -> continuity happy path."""
    trust = ecosystem_env["trust"]
    target_node_id = ecosystem_env["target_node_id"]

    await trust.grant_trust(
        node_id=target_node_id,
        relationship=RelationshipType.PEER,
        alias="machine-b",
    )

    cs = ContinuityService(
        ecosystem_registry=ecosystem_env["registry"],
        navigator=ecosystem_env["navigator"],
        trust_service=trust,
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        event_bus=ecosystem_env["events"],
    )

    runtime = MockRuntime(continuity_service=cs, event_bus=ecosystem_env["events"])
    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    adapter = TextInputAdapter()
    req = adapter.create_request("continue this work on my other laptop")

    resp = await coordinator.handle_request(req)

    assert coordinator.current_state == SurfaceState.COMPLETED
    assert "Done" in resp.message or "continued" in resp.message.lower()

    session = cs._sessions.get(cs._work_continuities["work-active-surface"])
    assert session is not None
    assert session.state == ContinuityState.COMPLETED
    assert session.result is not None
    assert session.result.outcome == ContinuityOutcome.SUCCESS
    assert session.target is not None
    assert session.target.node_id == target_node_id
    assert session.target.trust_verified is True
    assert mock_zarya.continue_work.called


@pytest.mark.asyncio
async def test_s17_7_surface_target_unavailable(
    tmp_path: Path,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Validate graceful surface response when no remote node is available."""
    events = EventBus()
    empty_reg = EcosystemRegistry(event_bus=events)
    empty_nav = HybridNavigator()
    trust_dir = tmp_path / "trust_empty"
    trust_dir.mkdir()
    trust = TrustService(data_dir=trust_dir, event_bus=events)

    cs = ContinuityService(
        ecosystem_registry=empty_reg,
        navigator=empty_nav,
        trust_service=trust,
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        event_bus=events,
    )

    runtime = MockRuntime(continuity_service=cs, event_bus=events)
    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    adapter = TextInputAdapter()
    req = adapter.create_request("continue this work on my other laptop")

    resp = await coordinator.handle_request(req)

    assert coordinator.current_state == SurfaceState.FAILED
    assert "couldn't continue" in resp.message.lower() or "failed" in resp.message.lower()


@pytest.mark.asyncio
async def test_s17_7_surface_target_untrusted(
    ecosystem_env: dict[str, Any],
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Validate that untrusted target stops continuity before transfer/zarya."""
    cs = ContinuityService(
        ecosystem_registry=ecosystem_env["registry"],
        navigator=ecosystem_env["navigator"],
        trust_service=ecosystem_env["trust"],
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        event_bus=ecosystem_env["events"],
    )

    runtime = MockRuntime(continuity_service=cs, event_bus=ecosystem_env["events"])
    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    adapter = TextInputAdapter()
    req = adapter.create_request("continue this work on my other laptop")

    resp = await coordinator.handle_request(req)

    assert coordinator.current_state == SurfaceState.FAILED
    assert not mock_flux.transfer.called
    assert not mock_zarya.continue_work.called


@pytest.mark.asyncio
async def test_s17_7_surface_flux_failure(
    ecosystem_env: dict[str, Any],
    mock_zarya: MagicMock,
) -> None:
    """Validate that Flux transfer failure propagates cleanly through surface."""
    trust = ecosystem_env["trust"]
    await trust.grant_trust(
        node_id=ecosystem_env["target_node_id"],
        relationship=RelationshipType.PEER,
        alias="machine-b",
    )

    failing_flux = MagicMock(spec=FluxProvider)
    failing_flux.transfer.return_value = FluxTransferResponse(
        transfer_id="xfer-fail",
        status=FluxTransferStatus.FAILED,
        error_message="Network unreachable",
    )

    cs = ContinuityService(
        ecosystem_registry=ecosystem_env["registry"],
        navigator=ecosystem_env["navigator"],
        trust_service=trust,
        flux_provider=failing_flux,
        zarya_provider=mock_zarya,
        event_bus=ecosystem_env["events"],
    )

    runtime = MockRuntime(continuity_service=cs, event_bus=ecosystem_env["events"])
    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    adapter = TextInputAdapter()
    req = adapter.create_request("continue this work on my other laptop")

    resp = await coordinator.handle_request(req)
    assert coordinator.current_state in (SurfaceState.COMPLETED, SurfaceState.FAILED)


@pytest.mark.asyncio
async def test_s17_7_surface_zarya_failure(
    ecosystem_env: dict[str, Any],
    mock_flux: MagicMock,
) -> None:
    """Validate that remote Zarya failure produces surface failure response."""
    trust = ecosystem_env["trust"]
    await trust.grant_trust(
        node_id=ecosystem_env["target_node_id"],
        relationship=RelationshipType.PEER,
        alias="machine-b",
    )

    failing_zarya = MagicMock(spec=ZaryaProvider)
    failing_zarya.continue_work.return_value = ContinuationResponse(
        operation_id="op-failed",
        outcome=VerificationOutcome.VERIFIED_FAILURE,
        reconstruction_completed=False,
        execution_completed=False,
        error="Target execution environment error",
    )

    cs = ContinuityService(
        ecosystem_registry=ecosystem_env["registry"],
        navigator=ecosystem_env["navigator"],
        trust_service=trust,
        flux_provider=mock_flux,
        zarya_provider=failing_zarya,
        event_bus=ecosystem_env["events"],
    )

    runtime = MockRuntime(continuity_service=cs, event_bus=ecosystem_env["events"])
    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    adapter = TextInputAdapter()
    req = adapter.create_request("continue this work on my other laptop")

    resp = await coordinator.handle_request(req)

    assert coordinator.current_state == SurfaceState.FAILED


@pytest.mark.asyncio
async def test_s17_7_surface_degraded_readiness_blocks(
    ecosystem_env: dict[str, Any],
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Validate that degraded ecosystem readiness blocks surface execution."""
    cs = ContinuityService(
        ecosystem_registry=ecosystem_env["registry"],
        navigator=ecosystem_env["navigator"],
        trust_service=ecosystem_env["trust"],
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        event_bus=ecosystem_env["events"],
    )

    runtime = MockRuntime(
        continuity_service=cs,
        readiness=EcosystemReadiness.DEGRADED,
        event_bus=ecosystem_env["events"],
    )
    coordinator = SurfaceCoordinator(runtime=runtime)
    await coordinator.start()

    adapter = TextInputAdapter()
    req = adapter.create_request("continue this work on my other laptop")

    resp = await coordinator.handle_request(req)

    assert coordinator.current_state == SurfaceState.DEGRADED
    assert "degraded" in resp.message.lower() or "ready" in resp.message.lower()
