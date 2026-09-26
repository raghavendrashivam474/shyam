"""S17.2 Cross-Node Provider Transport Integration Tests.

Validates the transport-layer completion:
- Target metadata resolution (flux_peer_id, zarya_url)
- Flux peer ID routing
- Zarya target-aware continuation routing
- Complete multi-node continuity lifecycle and failure matrix.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.continuity.errors import DuplicateContinuityError
from shyam.continuity.models import (
    ContinuityOutcome,
    ContinuityRequest,
    ContinuityTarget,
)
from shyam.continuity.service import ContinuityService
from shyam.continuity.state import ContinuityState
from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeState,
)
from shyam.discovery.ecosystem_registry import EcosystemRegistry
from shyam.events.bus import EventBus
from shyam.navigation.models import NavigationConstraints, NavigationRequest
from shyam.navigation.navigator import HybridNavigator
from shyam.providers.flux.models import (
    FluxTransferResponse,
    FluxTransferStatus,
)
from shyam.providers.flux.provider import FluxProvider
from shyam.providers.zarya.client import ZaryaClient
from shyam.providers.zarya.models import (
    ContinuationResponse,
    VerificationOutcome,
)
from shyam.providers.zarya.provider import ZaryaProvider
from shyam.trust.models import RelationshipType, TrustRecord, TrustStatus
from shyam.trust.service import TrustService


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def registry(event_bus: EventBus) -> EcosystemRegistry:
    return EcosystemRegistry(event_bus=event_bus)


@pytest.fixture
def navigator() -> HybridNavigator:
    return HybridNavigator()


@pytest.fixture
def mock_trust() -> MagicMock:
    trust = MagicMock(spec=TrustService)
    trust.get_record = AsyncMock(
        return_value=TrustRecord(
            node_id="node-beta-remote",
            status=TrustStatus.TRUSTED,
            relationship=RelationshipType.PEER,
        )
    )
    return trust


@pytest.fixture
def mock_flux() -> MagicMock:
    flux = MagicMock(spec=FluxProvider)
    flux.transfer.return_value = FluxTransferResponse(
        transfer_id="flux-tx-beta-100",
        status=FluxTransferStatus.COMPLETED,
    )
    return flux


@pytest.fixture
def mock_zarya() -> MagicMock:
    zarya = MagicMock(spec=ZaryaProvider)
    zarya.continue_work.return_value = ContinuationResponse(
        outcome=VerificationOutcome.VERIFIED_SUCCESS,
        operation_id="zarya-op-beta-200",
        reconstruction_completed=True,
        execution_completed=True,
        summary="Remote work continued successfully on Node Beta",
    )
    return zarya


@pytest.fixture
def continuity_service(
    navigator: HybridNavigator,
    mock_trust: MagicMock,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
    registry: EcosystemRegistry,
    event_bus: EventBus,
) -> ContinuityService:
    return ContinuityService(
        navigator=navigator,
        trust_service=mock_trust,
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=registry,
        event_bus=event_bus,
    )


@pytest.mark.asyncio
async def test_target_metadata_extraction_in_continuity_selection(
    registry: EcosystemRegistry,
    navigator: HybridNavigator,
    mock_trust: MagicMock,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Stage A: Verify S9 candidate metadata extracts flux_peer_id and zarya_url into ContinuityTarget."""
    # Register Node Beta with transport metadata
    beta_provider = DiscoveredProvider(
        provider_id="zarya.remote.agent",
        name="Remote Zarya Agent",
        capabilities=(
            DiscoveredCapability(
                capability_id="zarya.work.continue",
                name="Continue Portable Work",
                availability=AvailabilityStatus.AVAILABLE,
            ),
        ),
        metadata={
            "flux_peer_id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
            "zarya_url": "http://192.168.1.50:8765/ecosystem/v1",
        },
    )
    beta_node = DiscoveredNode(
        node_id="node-beta-remote",
        node_name="Laptop B",
        state=EcosystemNodeState.AVAILABLE,
        providers={"zarya.remote.agent": beta_provider},
    )
    await registry.register_node(beta_node)

    service = ContinuityService(
        navigator=navigator,
        trust_service=mock_trust,
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=registry,
    )

    req = ContinuityRequest(
        work_id="work-s17-2-001",
        source_device_id="node-alpha-local",
        portable_work={"test": "payload"},
        artifact_paths=("/path/to/artifact.dat",),
        target_constraints=NavigationConstraints(preferred_node="node-beta-remote"),
    )

    session = await service.request_continuity(req)

    assert session.state == ContinuityState.COMPLETED
    assert session.target is not None
    assert session.target.node_id == "node-beta-remote"
    assert session.target.flux_peer_id == "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"
    assert session.target.zarya_url == "http://192.168.1.50:8765/ecosystem/v1"

    # Verify flux transfer received flux_peer_id, NOT shyam node_id!
    mock_flux.transfer.assert_called_once_with(
        "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
        "/path/to/artifact.dat",
    )

    # Verify Zarya continue_work was called with remote target_url
    mock_zarya.continue_work.assert_called_once_with(
        {"test": "payload"},
        "node-alpha-local",
        session.continuity_id,
        "http://192.168.1.50:8765/ecosystem/v1",
    )


def test_zarya_provider_remote_client_instantiation() -> None:
    """Stage B: Verify ZaryaProvider routes remote URLs to a dynamic target ZaryaClient."""
    local_client = MagicMock(spec=ZaryaClient)
    local_client.token = "auth-token-xyz"
    provider = ZaryaProvider(client=local_client)

    with patch("shyam.providers.zarya.client.ZaryaClient.continue_work") as mock_remote_call:
        mock_remote_call.return_value = ContinuationResponse(
            outcome=VerificationOutcome.VERIFIED_SUCCESS,
            operation_id="op-remote-123",
            reconstruction_completed=True,
            execution_completed=True,
            summary="Remote execution verified",
        )

        resp = provider.continue_work(
            portable_work={"step": 1},
            source_device_id="node-a",
            continuity_id="cont-123",
            target_url="http://192.168.1.99:8765/ecosystem/v1",
        )

        assert resp.outcome == VerificationOutcome.VERIFIED_SUCCESS
        assert resp.operation_id == "op-remote-123"
        mock_remote_call.assert_called_once_with(
            portable_work={"step": 1},
            source_device_id="node-a",
            continuity_id="cont-123",
        )
        # Local client should NOT have been called
        local_client.continue_work.assert_not_called()


@pytest.mark.asyncio
async def test_failure_matrix_untrusted_remote_node(
    registry: EcosystemRegistry,
    navigator: HybridNavigator,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Stage C: Verify untrusted remote target is rejected before transport occurs."""
    untrusted_trust = MagicMock(spec=TrustService)
    untrusted_trust.get_record = AsyncMock(
        return_value=TrustRecord(
            node_id="node-beta-untrusted",
            status=TrustStatus.REVOKED,
            relationship=RelationshipType.NONE,
        )
    )

    beta_node = DiscoveredNode(
        node_id="node-beta-untrusted",
        node_name="Rogue Laptop",
        state=EcosystemNodeState.AVAILABLE,
        providers={
            "zarya.agent": DiscoveredProvider(
                provider_id="zarya.agent",
                name="Zarya",
                capabilities=(
                    DiscoveredCapability(
                        capability_id="zarya.work.continue",
                        availability=AvailabilityStatus.AVAILABLE,
                    ),
                ),
            )
        },
    )
    await registry.register_node(beta_node)

    service = ContinuityService(
        navigator=navigator,
        trust_service=untrusted_trust,
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=registry,
    )

    req = ContinuityRequest(
        work_id="work-untrusted-01",
        source_device_id="node-alpha",
        portable_work={"test": 1},
    )

    session = await service.request_continuity(req)
    assert session.state == ContinuityState.FAILED
    assert "Target trust status: revoked" in session.result.reason
    mock_flux.transfer.assert_not_called()
    mock_zarya.continue_work.assert_not_called()


@pytest.mark.asyncio
async def test_failure_matrix_flux_transfer_error(
    registry: EcosystemRegistry,
    navigator: HybridNavigator,
    mock_trust: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Stage D: Verify Flux transfer failure fails the continuity attempt without invoking Zarya."""
    failing_flux = MagicMock(spec=FluxProvider)
    failing_flux.transfer.side_effect = RuntimeError("Flux peer unreachable / connection timed out")

    beta_node = DiscoveredNode(
        node_id="node-beta-remote",
        node_name="Laptop B",
        state=EcosystemNodeState.AVAILABLE,
        providers={
            "zarya.agent": DiscoveredProvider(
                provider_id="zarya.agent",
                name="Zarya",
                capabilities=(
                    DiscoveredCapability(
                        capability_id="zarya.work.continue",
                        availability=AvailabilityStatus.AVAILABLE,
                    ),
                ),
            )
        },
    )
    await registry.register_node(beta_node)

    service = ContinuityService(
        navigator=navigator,
        trust_service=mock_trust,
        flux_provider=failing_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=registry,
    )

    req = ContinuityRequest(
        work_id="work-fail-transfer",
        source_device_id="node-alpha",
        portable_work={"test": 1},
        artifact_paths=("/data/file.bin",),
    )

    session = await service.request_continuity(req)
    assert session.state == ContinuityState.FAILED
    assert "Artifact transfer failed" in session.result.reason
    mock_zarya.continue_work.assert_not_called()


@pytest.mark.asyncio
async def test_failure_matrix_conservative_unknown_preservation(
    registry: EcosystemRegistry,
    navigator: HybridNavigator,
    mock_trust: MagicMock,
    mock_flux: MagicMock,
) -> None:
    """Stage E: Verify target Zarya returning UNKNOWN propagates as UNKNOWN outcome."""
    zarya_unknown = MagicMock(spec=ZaryaProvider)
    zarya_unknown.continue_work.return_value = ContinuationResponse(
        outcome=VerificationOutcome.UNKNOWN,
        operation_id="zarya-op-unknown-300",
        reconstruction_completed=True,
        execution_completed=False,
        summary="Remote execution state uncertain",
    )

    beta_node = DiscoveredNode(
        node_id="node-beta-remote",
        node_name="Laptop B",
        state=EcosystemNodeState.AVAILABLE,
        providers={
            "zarya.agent": DiscoveredProvider(
                provider_id="zarya.agent",
                name="Zarya",
                capabilities=(
                    DiscoveredCapability(
                        capability_id="zarya.work.continue",
                        availability=AvailabilityStatus.AVAILABLE,
                    ),
                ),
            )
        },
    )
    await registry.register_node(beta_node)

    service = ContinuityService(
        navigator=navigator,
        trust_service=mock_trust,
        flux_provider=mock_flux,
        zarya_provider=zarya_unknown,
        ecosystem_registry=registry,
    )

    req = ContinuityRequest(
        work_id="work-uncertainty",
        source_device_id="node-alpha",
        portable_work={"test": 1},
    )

    session = await service.request_continuity(req)
    assert session.state == ContinuityState.UNKNOWN
    assert session.result.outcome == ContinuityOutcome.UNKNOWN
    assert session.result.reconstruction_completed is True
    assert session.result.execution_completed is False


def test_failure_matrix_duplicate_continuity_blocking(
    registry: EcosystemRegistry,
    navigator: HybridNavigator,
    mock_trust: MagicMock,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Stage F: Verify S16 idempotency prevents duplicate concurrent attempts for the same work_id."""
    service = ContinuityService(
        navigator=navigator,
        trust_service=mock_trust,
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=registry,
    )

    # Manually insert active session
    active_req = ContinuityRequest(
        work_id="duplicate-work-id",
        source_device_id="node-alpha",
        portable_work={"test": 1},
    )
    from shyam.continuity.models import ContinuitySession
    active_session = ContinuitySession(
        request=active_req,
        state=ContinuityState.TRANSFERRING,
    )
    service._sessions[active_session.continuity_id] = active_session
    service._work_continuities[active_req.work_id] = active_session.continuity_id

    # Attempt second request with same work_id
    with pytest.raises(DuplicateContinuityError):
        asyncio.run(service.request_continuity(active_req))
