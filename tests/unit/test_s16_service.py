"""Unit tests for S16 ContinuityService orchestration pipeline."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.discovery.ecosystem_models import EcosystemNodeState
from shyam.continuity.errors import DuplicateContinuityError
from shyam.continuity.models import (
    ContinuityOutcome,
    ContinuityRequest,
    ContinuitySession,
    ContinuityState,
)
from shyam.continuity.service import ContinuityService
from shyam.navigation.models import NavigationResult, NavigationCandidate
from shyam.providers.flux.models import FluxTransferResponse, FluxTransferStatus
from shyam.providers.zarya.models import (
    ContinuationResponse,
    VerificationOutcome,
)
from shyam.trust.models import RelationshipType, TrustRecord, TrustStatus


@pytest.fixture
def mock_navigator() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_trust() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_flux() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_zarya() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_registry() -> MagicMock:
    reg = MagicMock()
    reg.create_snapshot.return_value = MagicMock()
    return reg


@pytest.fixture
def mock_events() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(
    mock_navigator: MagicMock,
    mock_trust: MagicMock,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
    mock_registry: MagicMock,
    mock_events: MagicMock,
) -> ContinuityService:
    return ContinuityService(
        navigator=mock_navigator,
        trust_service=mock_trust,
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=mock_registry,
        event_bus=mock_events,
    )


def _get_default_node_state() -> EcosystemNodeState:
    return list(EcosystemNodeState)[0]


def _get_default_availability_status() -> AvailabilityStatus:
    return list(AvailabilityStatus)[0]


def _make_mock_candidate(
    node_id: str,
    provider_id: str = "zarya.sovereign",
    capability_id: str = "zarya.work.continue",
) -> NavigationCandidate:
    """Helper to build a fully compliant NavigationCandidate with all required fields."""
    return NavigationCandidate(
        node_id=node_id,
        node_name=f"Node {node_id}",
        provider_id=provider_id,
        provider_name=f"Provider {provider_id}",
        capability_id=capability_id,
        is_local=False,
        node_state=_get_default_node_state(),
        provider_status=_get_default_availability_status(),
        capability_availability=_get_default_availability_status(),
    )


@pytest.mark.asyncio
async def test_successful_continuity_pipeline(
    service: ContinuityService,
    mock_navigator: MagicMock,
    mock_trust: MagicMock,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Test standard end-to-end happy path flow with artifact transfer."""
    req = ContinuityRequest(
        work_id="work-456",
        source_device_id="device-source",
        portable_work={"type": "shell_script", "script": "echo 1"},
        artifact_paths=("/data/file1.txt",),
    )

    # 1. Mock Navigator (S9)
    candidate = _make_mock_candidate("node-target")
    mock_navigator.navigate.return_value = NavigationResult(
        capability="zarya.work.continue",
        has_selection=True,
        selected=candidate,
        reason="Perfect match",
    )

    # 2. Mock Trust (S13)
    mock_trust.get_record = AsyncMock(
        return_value=TrustRecord(
            node_id="node-target",
            relationship=RelationshipType.PEER,
            status=TrustStatus.TRUSTED,
        )
    )

    # 3. Mock Flux (Transfer)
    mock_flux.transfer.return_value = FluxTransferResponse(
        transfer_id="transfer-tx-99",
        status=FluxTransferStatus.COMPLETED,
    )

    # 4. Mock Zarya N4 continuation
    mock_zarya.continue_work.return_value = ContinuationResponse(
        operation_id="target-op-77",
        outcome=VerificationOutcome.VERIFIED_SUCCESS,
        reconstruction_completed=True,
        execution_completed=True,
        summary="Work resumed successfully",
    )

    session = await service.request_continuity(req)

    # Verify pipeline state terminal
    assert session.state == ContinuityState.COMPLETED
    assert session.result is not None
    assert session.result.outcome == ContinuityOutcome.SUCCESS
    assert session.result.transfer_completed is True
    assert session.result.reconstruction_completed is True
    assert session.result.execution_completed is True
    assert session.result.zarya_outcome == "VERIFIED_SUCCESS"
    assert session.operation_id == "target-op-77"
    assert session.transfer_id == "transfer-tx-99"

    # Verify coordinator dependency calls
    mock_navigator.navigate.assert_called_once()
    mock_trust.get_record.assert_awaited_with("node-target")
    mock_flux.transfer.assert_called_with("node-target", "/data/file1.txt")
    mock_zarya.continue_work.assert_called_with(
        {"type": "shell_script", "script": "echo 1"},
        "device-source",
        session.continuity_id,
    )


@pytest.mark.asyncio
async def test_unsupported_intent(service: ContinuityService) -> None:
    """Verify unsupported intents are safely short-circuited."""
    req = ContinuityRequest(
        work_id="work-456",
        source_device_id="device-source",
        portable_work={"type": "shell_script"},
        continuity_intent="MIGRATION",
    )

    session = await service.request_continuity(req)
    assert session.state == ContinuityState.UNSUPPORTED
    assert session.result.outcome == ContinuityOutcome.UNSUPPORTED


@pytest.mark.asyncio
async def test_target_selection_failure(
    service: ContinuityService,
    mock_navigator: MagicMock,
) -> None:
    """Pipeline should stop and transition to FAILED if no targets match."""
    req = ContinuityRequest(
        work_id="work-456",
        source_device_id="device-source",
        portable_work={"type": "shell_script"},
    )
    mock_navigator.navigate.return_value = NavigationResult(
        capability="zarya.work.continue",
        selected=None,
        reason="No nodes hosting zarya.work.continue found",
    )

    session = await service.request_continuity(req)
    assert session.state == ContinuityState.FAILED
    assert "No eligible target" in session.result.reason


@pytest.mark.asyncio
async def test_trust_verification_failure(
    service: ContinuityService,
    mock_navigator: MagicMock,
    mock_trust: MagicMock,
) -> None:
    """Pipeline should fail if target is not S13 trusted."""
    req = ContinuityRequest(
        work_id="work-456",
        source_device_id="device-source",
        portable_work={"type": "shell_script"},
    )
    candidate = _make_mock_candidate("untrusted-node")
    mock_navigator.navigate.return_value = NavigationResult(
        capability="zarya.work.continue",
        selected=candidate,
    )

    # Return UNKNOWN relationship (untrusted)
    mock_trust.get_record = AsyncMock(
        return_value=TrustRecord(
            node_id="untrusted-node",
            relationship=RelationshipType.NONE,
            status=TrustStatus.UNKNOWN,
        )
    )

    session = await service.request_continuity(req)
    assert session.state == ContinuityState.FAILED
    assert "No trust relationship" in session.result.reason


@pytest.mark.asyncio
async def test_flux_transfer_failure(
    service: ContinuityService,
    mock_navigator: MagicMock,
    mock_trust: MagicMock,
    mock_flux: MagicMock,
) -> None:
    """Pipeline should fail if file transfer crashes."""
    req = ContinuityRequest(
        work_id="work-456",
        source_device_id="device-source",
        portable_work={"type": "shell_script"},
        artifact_paths=("/data/file1.txt",),
    )
    candidate = _make_mock_candidate("target")
    mock_navigator.navigate.return_value = NavigationResult(
        capability="zarya.work.continue",
        selected=candidate,
    )
    mock_trust.get_record = AsyncMock(
        return_value=TrustRecord(
            node_id="target",
            relationship=RelationshipType.PEER,
            status=TrustStatus.TRUSTED,
        )
    )

    # Flux raises error
    mock_flux.transfer.side_effect = Exception("Network timeout")

    session = await service.request_continuity(req)
    assert session.state == ContinuityState.FAILED
    assert "Artifact transfer failed" in session.result.reason


@pytest.mark.asyncio
async def test_target_continuation_failure_or_rejection(
    service: ContinuityService,
    mock_navigator: MagicMock,
    mock_trust: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Pipeline should fail if Zarya execution throws exceptions."""
    req = ContinuityRequest(
        work_id="work-456",
        source_device_id="device-source",
        portable_work={"type": "shell_script"},
    )
    candidate = _make_mock_candidate("target")
    mock_navigator.navigate.return_value = NavigationResult(
        capability="zarya.work.continue",
        selected=candidate,
    )
    mock_trust.get_record = AsyncMock(
        return_value=TrustRecord(
            node_id="target",
            relationship=RelationshipType.PEER,
            status=TrustStatus.TRUSTED,
        )
    )

    mock_zarya.continue_work.side_effect = Exception("Reconstruction signature mismatch")

    session = await service.request_continuity(req)
    assert session.state == ContinuityState.FAILED
    assert "Target continuation failed" in session.result.reason


@pytest.mark.asyncio
async def test_conservative_verification_uncertainty(
    service: ContinuityService,
    mock_navigator: MagicMock,
    mock_trust: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Verify conservative mapping: UNKNOWN remains UNKNOWN outcome (not mapped to success)."""
    req = ContinuityRequest(
        work_id="work-456",
        source_device_id="device-source",
        portable_work={"type": "shell_script"},
    )
    candidate = _make_mock_candidate("target")
    mock_navigator.navigate.return_value = NavigationResult(
        capability="zarya.work.continue",
        selected=candidate,
    )
    mock_trust.get_record = AsyncMock(
        return_value=TrustRecord(
            node_id="target",
            relationship=RelationshipType.PEER,
            status=TrustStatus.TRUSTED,
        )
    )

    # Target returns UNKNOWN outcome
    mock_zarya.continue_work.return_value = ContinuationResponse(
        operation_id="target-op-77",
        outcome=VerificationOutcome.UNKNOWN,
        reconstruction_completed=True,
        execution_completed=False,
    )

    session = await service.request_continuity(req)
    assert session.state == ContinuityState.UNKNOWN
    assert session.result.outcome == ContinuityOutcome.UNKNOWN


@pytest.mark.asyncio
async def test_idempotency_duplicate_blocking(
    service: ContinuityService,
) -> None:
    """Ensures duplicate continuity requests for active work are blocked."""
    req = ContinuityRequest(
        work_id="active-work-88",
        source_device_id="device-source",
        portable_work={"type": "shell_script"},
    )

    # Create and manually seed an active session into the service
    active_session = ContinuitySession(
        request=req,
        state=ContinuityState.TRANSFERRING,
    )
    service._sessions[active_session.continuity_id] = active_session
    service._work_continuities[req.work_id] = active_session.continuity_id

    # A duplicate request should be explicitly blocked without running the pipeline
    with pytest.raises(DuplicateContinuityError):
        await service.request_continuity(req)
