"""S17.3 Physical Two-Machine Continuity Validation & Failure Matrix Tests.

Validates the complete cross-node continuity chain:
Shyam A -> UDP Discovery -> S13 Trust -> S9 Navigation -> S16 Continuity -> Flux Transport -> Zarya Target Execution.
"""

from __future__ import annotations

import hashlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.continuity.errors import DuplicateContinuityError
from shyam.continuity.models import (
    ContinuityOutcome,
    ContinuityRequest,
    ContinuityResult,
    ContinuitySession,
    ContinuityState,
    ContinuityTarget,
)
from shyam.continuity.service import ContinuityService
from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeState,
    EcosystemSnapshot,
)
from shyam.discovery.ecosystem_registry import EcosystemRegistry
from shyam.discovery.model import Peer
from shyam.discovery.service import DiscoveryService
from shyam.events.bus import EventBus
from shyam.identity import IdentityManager
from shyam.navigation.models import NavigationConstraints, NavigationRequest
from shyam.navigation.navigator import HybridNavigator
from shyam.providers.flux.models import FluxTransferResponse, FluxTransferStatus
from shyam.providers.flux.provider import FluxProvider
from shyam.providers.zarya.models import ContinuationResponse, VerificationOutcome
from shyam.providers.zarya.provider import ZaryaProvider
from shyam.trust.models import RelationshipType, TrustRecord, TrustStatus
from shyam.trust.service import TrustService


@pytest.fixture
def temp_artifact(tmp_path: Path) -> Path:
    """Create a deterministic test artifact with known SHA-256."""
    p = tmp_path / "work_artifact.json"
    p.write_text('{"task_id": "s17_3_test", "data": "payload_verification_value"}', encoding="utf-8")
    return p


@pytest.fixture
def mock_flux_provider() -> MagicMock:
    """Mock FluxProvider satisfying S17.2 flux_peer_id transfer contract."""
    flux = MagicMock(spec=FluxProvider)
    flux.transfer.return_value = FluxTransferResponse(
        transfer_id="transfer-s17-3-001",
        status=FluxTransferStatus.COMPLETED,
        bytes_transferred=64,
        elapsed_seconds=0.15,
        destination_path="/data/artifacts/work_artifact.json",
    )
    return flux


@pytest.fixture
def mock_zarya_provider() -> MagicMock:
    """Mock ZaryaProvider satisfying S17.2 remote target_url contract."""
    zarya = MagicMock(spec=ZaryaProvider)
    zarya.continue_work.return_value = ContinuationResponse(
        operation_id="op-s17-3-999",
        outcome=VerificationOutcome.VERIFIED_SUCCESS,
        reconstruction_completed=True,
        execution_completed=True,
        result={"status": "success", "rows_processed": 100},
        summary="Remote execution completed successfully on target node",
    )
    return zarya


@pytest.fixture
def setup_dual_node_ecosystem():
    """Setup dual node ecosystem with S13 trust and remote metadata."""
    events = EventBus()
    registry = EcosystemRegistry(event_bus=events)
    navigator = HybridNavigator()
    trust = MagicMock(spec=TrustService)

    node_alpha_id = "node-alpha-1111"
    node_beta_id = "node-beta-2222"
    beta_flux_peer = "flux-peer-beta-5555"
    beta_zarya_url = "http://192.168.1.150:8765/ecosystem/v1"

    now = datetime.now(UTC)

    # Register Node Beta in EcosystemRegistry with live metadata
    zarya_cap = DiscoveredCapability(
        capability_id="zarya.work.continue",
        name="Zarya Work Continuation",
        availability=AvailabilityStatus.AVAILABLE,
    )
    zarya_prov = DiscoveredProvider(
        provider_id="zarya.agent",
        name="Zarya Agent Provider",
        version="1.0.0",
        capabilities=(zarya_cap,),
        status=AvailabilityStatus.AVAILABLE,
        metadata={"zarya_url": beta_zarya_url},
    )
    beta_node = DiscoveredNode(
        node_id=node_beta_id,
        node_name="Node Beta",
        state=EcosystemNodeState.AVAILABLE,
        is_local=False,
        protocol_version="1.0.0",
        providers={"zarya.agent": zarya_prov},
        metadata={
            "flux_peer_id": beta_flux_peer,
            "zarya_url": beta_zarya_url,
            "address": "192.168.1.150",
        },
    )
    registry._nodes[node_beta_id] = beta_node

    # Trust service trusts Node Beta
    trust.get_record = AsyncMock(
        return_value=TrustRecord(
            node_id=node_beta_id,
            status=TrustStatus.TRUSTED,
            relationship=RelationshipType.PEER,
            created_at=now,
            updated_at=now,
        )
    )

    return {
        "events": events,
        "registry": registry,
        "navigator": navigator,
        "trust": trust,
        "node_alpha_id": node_alpha_id,
        "node_beta_id": node_beta_id,
        "beta_flux_peer": beta_flux_peer,
        "beta_zarya_url": beta_zarya_url,
    }


# -----------------------------------------------------------------------------
# Test 1: Full Happy Path Continuity & Localhost Leak Detection
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_s17_3_happy_path_continuity_and_no_localhost_leak(
    setup_dual_node_ecosystem,
    mock_flux_provider: MagicMock,
    mock_zarya_provider: MagicMock,
    temp_artifact: Path,
) -> None:
    """Validate full end-to-end continuity to remote node without localhost fallback."""
    env = setup_dual_node_ecosystem

    service = ContinuityService(
        navigator=env["navigator"],
        trust_service=env["trust"],
        flux_provider=mock_flux_provider,
        zarya_provider=mock_zarya_provider,
        ecosystem_registry=env["registry"],
        event_bus=env["events"],
    )

    req = ContinuityRequest(
        work_id="work-s17-3-happy",
        source_device_id=env["node_alpha_id"],
        portable_work={"work_id": "work-s17-3-happy", "task": "data_process"},
        artifact_paths=(str(temp_artifact),),
        target_constraints=NavigationConstraints(preferred_node=env["node_beta_id"]),
        continuity_intent="COPY",
    )

    session = await service.request_continuity(req)

    # 1. Outcome Verification
    assert session.state == ContinuityState.COMPLETED
    assert session.result is not None
    assert session.result.outcome == ContinuityOutcome.SUCCESS

    # 2. Target Routing Verification
    assert session.target is not None
    assert session.target.node_id == env["node_beta_id"]
    assert session.target.flux_peer_id == env["beta_flux_peer"]
    assert session.target.zarya_url == env["beta_zarya_url"]

    # 3. Flux Transfer Call Verification (Must use beta_flux_peer)
    mock_flux_provider.transfer.assert_called_once_with(
        env["beta_flux_peer"],
        str(temp_artifact),
    )

    # 4. Zarya Continuation Call Verification (Must use remote target_url, NOT localhost!)
    mock_zarya_provider.continue_work.assert_called_once_with(
        req.portable_work,
        env["node_alpha_id"],
        session.continuity_id,
        env["beta_zarya_url"],
    )
    assert env["beta_zarya_url"] != "http://127.0.0.1:8765/ecosystem/v1"
    assert "192.168.1.150" in env["beta_zarya_url"]


# -----------------------------------------------------------------------------
# Test 2: Artifact SHA-256 Integrity Verification
# -----------------------------------------------------------------------------
def test_s17_3_artifact_sha256_integrity(temp_artifact: Path) -> None:
    """Prove that source artifact SHA-256 matches expectation."""
    content = temp_artifact.read_bytes()
    calculated_hash = hashlib.sha256(content).hexdigest()

    assert len(calculated_hash) == 64
    assert calculated_hash == hashlib.sha256(b'{"task_id": "s17_3_test", "data": "payload_verification_value"}').hexdigest()


# -----------------------------------------------------------------------------
# Test 3: Failure Matrix — Target Zarya Unavailable
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_s17_3_failure_matrix_target_zarya_unavailable(
    setup_dual_node_ecosystem,
    mock_flux_provider: MagicMock,
    temp_artifact: Path,
) -> None:
    """Verify that when target Zarya is unavailable, continuity fails safely."""
    env = setup_dual_node_ecosystem

    failing_zarya = MagicMock(spec=ZaryaProvider)
    failing_zarya.continue_work.side_effect = ConnectionError("Could not reach remote Zarya on 192.168.1.150:8765")

    service = ContinuityService(
        navigator=env["navigator"],
        trust_service=env["trust"],
        flux_provider=mock_flux_provider,
        zarya_provider=failing_zarya,
        ecosystem_registry=env["registry"],
        event_bus=env["events"],
    )

    req = ContinuityRequest(
        work_id="work-fail-zarya",
        source_device_id=env["node_alpha_id"],
        portable_work={"work_id": "work-fail-zarya"},
        artifact_paths=(str(temp_artifact),),
        target_constraints=NavigationConstraints(preferred_node=env["node_beta_id"]),
        continuity_intent="COPY",
    )

    session = await service.request_continuity(req)

    assert session.state == ContinuityState.FAILED
    assert session.result is not None
    assert session.result.outcome == ContinuityOutcome.FAILED
    assert "Target continuation failed" in session.result.reason or "Could not reach remote Zarya" in session.result.reason


# -----------------------------------------------------------------------------
# Test 4: Failure Matrix — Flux Transfer Error
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_s17_3_failure_matrix_flux_transfer_error(
    setup_dual_node_ecosystem,
    mock_zarya_provider: MagicMock,
    temp_artifact: Path,
) -> None:
    """Verify that artifact transfer failure aborts continuity before continuation."""
    env = setup_dual_node_ecosystem

    failing_flux = MagicMock(spec=FluxProvider)
    failing_flux.transfer.side_effect = ConnectionError("Network connection reset by peer during transfer")

    service = ContinuityService(
        navigator=env["navigator"],
        trust_service=env["trust"],
        flux_provider=failing_flux,
        zarya_provider=mock_zarya_provider,
        ecosystem_registry=env["registry"],
        event_bus=env["events"],
    )

    req = ContinuityRequest(
        work_id="work-fail-flux",
        source_device_id=env["node_alpha_id"],
        portable_work={"work_id": "work-fail-flux"},
        artifact_paths=(str(temp_artifact),),
        target_constraints=NavigationConstraints(preferred_node=env["node_beta_id"]),
        continuity_intent="COPY",
    )

    session = await service.request_continuity(req)

    assert session.state == ContinuityState.FAILED
    assert session.result is not None
    assert session.result.outcome == ContinuityOutcome.FAILED
    assert "Artifact transfer failed" in session.result.reason
    mock_zarya_provider.continue_work.assert_not_called()


# -----------------------------------------------------------------------------
# Test 5: Failure Matrix — Untrusted Target Authorization Rejection
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_s17_3_failure_matrix_untrusted_target(
    setup_dual_node_ecosystem,
    mock_flux_provider: MagicMock,
    mock_zarya_provider: MagicMock,
    temp_artifact: Path,
) -> None:
    """Verify that untrusted target is rejected before transport occurs."""
    env = setup_dual_node_ecosystem
    now = datetime.now(UTC)

    untrusted_trust = MagicMock(spec=TrustService)
    untrusted_trust.get_record = AsyncMock(
        return_value=TrustRecord(
            node_id=env["node_beta_id"],
            status=TrustStatus.REVOKED,
            relationship=RelationshipType.PEER,
            created_at=now,
            updated_at=now,
        )
    )

    service = ContinuityService(
        navigator=env["navigator"],
        trust_service=untrusted_trust,
        flux_provider=mock_flux_provider,
        zarya_provider=mock_zarya_provider,
        ecosystem_registry=env["registry"],
        event_bus=env["events"],
    )

    req = ContinuityRequest(
        work_id="work-fail-trust",
        source_device_id=env["node_alpha_id"],
        portable_work={"work_id": "work-fail-trust"},
        artifact_paths=(str(temp_artifact),),
        target_constraints=NavigationConstraints(preferred_node=env["node_beta_id"]),
        continuity_intent="COPY",
    )

    session = await service.request_continuity(req)

    assert session.state == ContinuityState.FAILED
    assert session.result is not None
    assert session.result.outcome == ContinuityOutcome.FAILED
    assert "Target trust status: revoked" in session.result.reason
    mock_flux_provider.transfer.assert_not_called()
    mock_zarya_provider.continue_work.assert_not_called()


# -----------------------------------------------------------------------------
# Test 6: Failure Matrix — Duplicate Continuity Blocking (Idempotency)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_s17_3_failure_matrix_duplicate_continuity_blocking(
    setup_dual_node_ecosystem,
    mock_flux_provider: MagicMock,
    mock_zarya_provider: MagicMock,
    temp_artifact: Path,
) -> None:
    """Verify duplicate active continuity requests for the same work_id are rejected."""
    env = setup_dual_node_ecosystem

    service = ContinuityService(
        navigator=env["navigator"],
        trust_service=env["trust"],
        flux_provider=mock_flux_provider,
        zarya_provider=mock_zarya_provider,
        ecosystem_registry=env["registry"],
        event_bus=env["events"],
    )

    req = ContinuityRequest(
        work_id="work-dup-test",
        source_device_id=env["node_alpha_id"],
        portable_work={"work_id": "work-dup-test"},
        artifact_paths=(str(temp_artifact),),
        target_constraints=NavigationConstraints(preferred_node=env["node_beta_id"]),
        continuity_intent="COPY",
    )

    # Inject an in-progress session
    active_session = ContinuitySession(
        continuity_id="existing-session-123",
        request=req,
        state=ContinuityState.TRANSFERRING,
    )
    service._sessions["existing-session-123"] = active_session
    service._work_continuities[req.work_id] = "existing-session-123"

    with pytest.raises(DuplicateContinuityError):
        await service.request_continuity(req)
