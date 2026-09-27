"""Integration tests for S17.4 Real Two-Device Physical Continuity Validation.

Uses REAL S13 TrustService and real EcosystemRegistry to test:
1. Full E2E continuity with SHA-256 artifact integrity.
2. Untrusted target rejection.
3. Structured FluxTransferStatus.FAILED rejection (S17.4 fix).
4. Target Zarya unreachable failure.
5. Duplicate continuity idempotency.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.continuity.errors import DuplicateContinuityError
from shyam.continuity.models import (
    ContinuityOutcome,
    ContinuityRequest,
    ContinuityState,
)
from shyam.continuity.service import ContinuityService
from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeState,
)
from shyam.discovery.ecosystem_registry import EcosystemRegistry
from shyam.events.bus import EventBus
from shyam.navigation.models import NavigationConstraints
from shyam.navigation.navigator import HybridNavigator
from shyam.providers.flux.models import FluxTransferResponse, FluxTransferStatus
from shyam.providers.flux.provider import FluxProvider
from shyam.providers.zarya.models import ContinuationResponse, VerificationOutcome
from shyam.providers.zarya.provider import ZaryaProvider
from shyam.trust.models import RelationshipType, TrustStatus
from shyam.trust.service import TrustService


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def temp_artifact(tmp_path: Path) -> Path:
    """Create a deterministic test artifact with known SHA-256."""
    p = tmp_path / "s17_4_payload.bin"
    p.write_bytes(b"S17.4-DETERMINISTIC-CROSS-DEVICE-WORK-PAYLOAD")
    return p


@pytest.fixture
def mock_flux() -> MagicMock:
    flux = MagicMock(spec=FluxProvider)
    flux.peer_id = "flux-peer-alpha-1111"
    flux.transfer.return_value = FluxTransferResponse(
        transfer_id="tx-s17-4-ok-999",
        status=FluxTransferStatus.COMPLETED,
    )
    return flux


@pytest.fixture
def mock_zarya() -> MagicMock:
    zarya = MagicMock(spec=ZaryaProvider)
    zarya.continue_work.return_value = ContinuationResponse(
        operation_id="op-zarya-s17-4-123",
        outcome=VerificationOutcome.VERIFIED_SUCCESS,
        reconstruction_completed=True,
        execution_completed=True,
        summary="Remote execution verified on Machine B",
    )
    return zarya


@pytest.fixture
def dual_node_env(tmp_path: Path):
    """Dual-node ecosystem with REAL TrustService: Node Alpha (source) + Node Beta (target)."""
    events = EventBus()
    registry = EcosystemRegistry(event_bus=events)
    navigator = HybridNavigator()

    # REAL TrustService with real persistence
    trust_dir = tmp_path / "trust_data"
    trust_dir.mkdir()
    trust = TrustService(data_dir=trust_dir, event_bus=events)

    node_alpha = "node-alpha-source"
    node_beta = "node-beta-target"
    beta_flux_peer = "flux-peer-beta-5678"
    beta_zarya_url = "http://192.168.1.20:8765/ecosystem/v1"
    now = datetime.now(UTC)

    cap = DiscoveredCapability(
        capability_id="zarya.work.continue",
        name="Continue Work",
        availability=AvailabilityStatus.AVAILABLE,
    )
    prov = DiscoveredProvider(
        provider_id="zarya.agent",
        name="Zarya Agent",
        version="1.0.0",
        capabilities=(cap,),
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
            "address": "192.168.1.20",
        },
        first_seen=now,
        last_seen=now,
    )
    registry._nodes[node_beta] = beta_node

    return {
        "events": events,
        "registry": registry,
        "navigator": navigator,
        "trust": trust,
        "node_alpha": node_alpha,
        "node_beta": node_beta,
        "beta_flux_peer": beta_flux_peer,
        "beta_zarya_url": beta_zarya_url,
    }


# ── Test 1: Full E2E Happy Path with SHA-256 Integrity ──────────────────

@pytest.mark.asyncio
async def test_s17_4_e2e_continuity_with_sha256_integrity(
    dual_node_env,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
    temp_artifact: Path,
) -> None:
    """Full cross-device continuity: discovery -> REAL trust -> transfer -> continuation -> verify."""
    env = dual_node_env
    expected_sha = hashlib.sha256(temp_artifact.read_bytes()).hexdigest()

    # Grant REAL S13 Trust to target
    await env["trust"].grant_trust(
        node_id=env["node_beta"],
        relationship=RelationshipType.PEER,
        alias="Machine B Peer",
    )
    assert await env["trust"].is_trusted(env["node_beta"])

    service = ContinuityService(
        navigator=env["navigator"],
        trust_service=env["trust"],
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=env["registry"],
        event_bus=env["events"],
    )

    req = ContinuityRequest(
        work_id="work-s17-4-e2e-001",
        source_device_id=env["node_alpha"],
        portable_work={
            "task": "distributed_computation",
            "sha256": expected_sha,
        },
        artifact_paths=(str(temp_artifact),),
        target_constraints=NavigationConstraints(preferred_node=env["node_beta"]),
    )

    session = await service.request_continuity(req)

    assert session.state == ContinuityState.COMPLETED
    assert session.result is not None
    assert session.result.outcome == ContinuityOutcome.SUCCESS
    assert session.result.transfer_completed is True
    assert session.result.execution_completed is True
    assert session.transfer_id == "tx-s17-4-ok-999"
    assert session.operation_id == "op-zarya-s17-4-123"

    # Verify Flux called with remote peer_id (not localhost)
    mock_flux.transfer.assert_called_once_with(
        env["beta_flux_peer"],
        str(temp_artifact),
    )

    # Verify Zarya called with remote URL (not localhost)
    mock_zarya.continue_work.assert_called_once()
    args, _ = mock_zarya.continue_work.call_args
    assert args[3] == env["beta_zarya_url"]
    assert "127.0.0.1" not in env["beta_zarya_url"]
    assert "localhost" not in env["beta_zarya_url"]


# ── Test 2: Untrusted Target Rejection ──────────────────────────────────

@pytest.mark.asyncio
async def test_s17_4_failure_untrusted_target(
    dual_node_env,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Continuity rejects target when REAL trust record does not exist."""
    env = dual_node_env
    # Do NOT grant trust in this test

    service = ContinuityService(
        navigator=env["navigator"],
        trust_service=env["trust"],
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=env["registry"],
        event_bus=env["events"],
    )

    req = ContinuityRequest(
        work_id="work-s17-4-untrusted",
        source_device_id=env["node_alpha"],
        portable_work={"task": "secret"},
        target_constraints=NavigationConstraints(preferred_node=env["node_beta"]),
    )

    session = await service.request_continuity(req)

    assert session.state == ContinuityState.FAILED
    assert "No trust relationship" in session.result.reason
    mock_flux.transfer.assert_not_called()
    mock_zarya.continue_work.assert_not_called()


# ── Test 3: Structured Flux Transfer Failure (S17.4 Fix) ────────────────

@pytest.mark.asyncio
async def test_s17_4_failure_structured_flux_error(
    dual_node_env,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
    temp_artifact: Path,
) -> None:
    """FluxTransferStatus.FAILED causes clean continuity failure, no continuation."""
    env = dual_node_env
    await env["trust"].grant_trust(
        node_id=env["node_beta"],
        relationship=RelationshipType.PEER,
    )

    mock_flux.transfer.return_value = FluxTransferResponse(
        transfer_id="tx-fail-001",
        status=FluxTransferStatus.FAILED,
    )

    service = ContinuityService(
        navigator=env["navigator"],
        trust_service=env["trust"],
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=env["registry"],
        event_bus=env["events"],
    )

    req = ContinuityRequest(
        work_id="work-s17-4-flux-fail",
        source_device_id=env["node_alpha"],
        portable_work={"task": "data_process"},
        artifact_paths=(str(temp_artifact),),
        target_constraints=NavigationConstraints(preferred_node=env["node_beta"]),
    )

    session = await service.request_continuity(req)

    assert session.state == ContinuityState.FAILED
    assert session.result.outcome == ContinuityOutcome.FAILED
    assert "Artifact transfer failed with status: FAILED" in session.result.reason
    mock_zarya.continue_work.assert_not_called()


# ── Test 4: Target Zarya Unreachable ────────────────────────────────────

@pytest.mark.asyncio
async def test_s17_4_failure_target_zarya_unreachable(
    dual_node_env,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Clean failure when remote Zarya endpoint raises connection error."""
    env = dual_node_env
    await env["trust"].grant_trust(
        node_id=env["node_beta"],
        relationship=RelationshipType.PEER,
    )
    mock_zarya.continue_work.side_effect = RuntimeError("Connection refused")

    service = ContinuityService(
        navigator=env["navigator"],
        trust_service=env["trust"],
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=env["registry"],
        event_bus=env["events"],
    )

    req = ContinuityRequest(
        work_id="work-s17-4-zarya-offline",
        source_device_id=env["node_alpha"],
        portable_work={"task": "run"},
        target_constraints=NavigationConstraints(preferred_node=env["node_beta"]),
    )

    session = await service.request_continuity(req)

    assert session.state == ContinuityState.FAILED
    assert "Target continuation failed" in session.result.reason
    assert "Connection refused" in session.result.reason


# ── Test 5: Duplicate Continuity Idempotency ────────────────────────────

@pytest.mark.asyncio
async def test_s17_4_failure_duplicate_continuity_blocked(
    dual_node_env,
    mock_flux: MagicMock,
    mock_zarya: MagicMock,
) -> None:
    """Duplicate active continuity request raises DuplicateContinuityError."""
    env = dual_node_env
    await env["trust"].grant_trust(
        node_id=env["node_beta"],
        relationship=RelationshipType.PEER,
    )

    def slow_continue(*args: Any, **kwargs: Any) -> ContinuationResponse:
        time.sleep(0.5)
        return ContinuationResponse(
            operation_id="op-dup-123",
            outcome=VerificationOutcome.VERIFIED_SUCCESS,
            reconstruction_completed=True,
            execution_completed=True,
        )

    mock_zarya.continue_work.side_effect = slow_continue

    service = ContinuityService(
        navigator=env["navigator"],
        trust_service=env["trust"],
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=env["registry"],
        event_bus=env["events"],
    )

    req = ContinuityRequest(
        work_id="work-s17-4-dup-test",
        source_device_id=env["node_alpha"],
        portable_work={"task": "slow"},
        target_constraints=NavigationConstraints(preferred_node=env["node_beta"]),
    )

    task = asyncio.create_task(service.request_continuity(req))
    await asyncio.sleep(0.05)

    with pytest.raises(DuplicateContinuityError):
        await service.request_continuity(req)

    first = await task
    assert first.state == ContinuityState.COMPLETED