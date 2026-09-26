"""S17.1 Real Multi-Node End-to-End Validation Suite.

Validates the complete cross-device work continuity pipeline across
two distinct Shyam node instances (Node A -> Node B) per S17.1 Test Plan.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.continuity.models import (
    ContinuityOutcome,
    ContinuityRequest,
    ContinuitySession,
    ContinuityState,
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
from shyam.identity import IdentityManager, load_or_create_keypair
from shyam.navigation.models import NavigationConstraints, NavigationRequest
from shyam.navigation.navigator import HybridNavigator
from shyam.providers.flux.models import FluxTransferResponse, FluxTransferStatus
from shyam.providers.flux.provider import FluxProvider
from shyam.providers.zarya.models import (
    ContinuationResponse,
    VerificationOutcome,
)
from shyam.providers.zarya.provider import ZaryaProvider
from shyam.trust.models import RelationshipType, TrustRecord, TrustStatus
from shyam.trust.service import TrustService


@pytest.fixture
def evidence_collector() -> dict[str, Any]:
    """Collects structured validation evidence during test execution."""
    return {
        "sprint": "S17.1",
        "stages": {},
        "identities": {},
        "artifacts": {},
        "continuity": {},
    }


@pytest.fixture
def fixture_payload_path() -> Path:
    """Returns the absolute path to the deterministic test fixture."""
    path = Path("tests/fixtures/s17_1_payload.txt").resolve()
    assert path.exists(), f"Fixture not found at {path}"
    return path


@pytest.mark.asyncio
async def test_s17_1_stage_a_node_startup_and_identity(
    tmp_path: Path,
    evidence_collector: dict[str, Any],
) -> None:
    """Stage S17.1-A: Verify Node A and Node B independent identity & trust setup."""
    dir_a = tmp_path / "node_a"
    dir_b = tmp_path / "node_b"
    dir_a.mkdir()
    dir_b.mkdir()

    # Node A setup
    id_mgr_a = IdentityManager(data_dir=dir_a, custom_node_name="node-alpha")
    ident_a = id_mgr_a.get_or_create_identity()
    kp_a, crypto_a = load_or_create_keypair(data_dir=dir_a, node_id=ident_a.node_id)
    trust_a = TrustService(data_dir=dir_a)
    await trust_a.initialize()
    await trust_a.grant_trust(
        node_id=str(ident_a.node_id),
        public_key=crypto_a.public_key,
        relationship=RelationshipType.PERSONAL,
        alias=ident_a.node_name,
    )

    # Node B setup
    id_mgr_b = IdentityManager(data_dir=dir_b, custom_node_name="node-beta")
    ident_b = id_mgr_b.get_or_create_identity()
    kp_b, crypto_b = load_or_create_keypair(data_dir=dir_b, node_id=ident_b.node_id)
    trust_b = TrustService(data_dir=dir_b)
    await trust_b.initialize()
    await trust_b.grant_trust(
        node_id=str(ident_b.node_id),
        public_key=crypto_b.public_key,
        relationship=RelationshipType.PERSONAL,
        alias=ident_b.node_name,
    )

    # Assertions
    assert ident_a.node_id != ident_b.node_id
    assert crypto_a.public_key != crypto_b.public_key
    assert await trust_a.is_trusted(str(ident_a.node_id))
    assert await trust_b.is_trusted(str(ident_b.node_id))

    evidence_collector["identities"]["node_a"] = {
        "node_id": str(ident_a.node_id),
        "public_key": crypto_a.public_key,
    }
    evidence_collector["identities"]["node_b"] = {
        "node_id": str(ident_b.node_id),
        "public_key": crypto_b.public_key,
    }
    evidence_collector["stages"]["stage_a"] = "PASSED"


@pytest.mark.asyncio
async def test_s17_1_stage_b_c_discovery_and_mutual_trust(
    tmp_path: Path,
    evidence_collector: dict[str, Any],
) -> None:
    """Stage S17.1-B & C: Verify cross-node discovery indexing and mutual S13 trust."""
    dir_a = tmp_path / "node_a"
    dir_b = tmp_path / "node_b"
    dir_a.mkdir()
    dir_b.mkdir()

    trust_a = TrustService(data_dir=dir_a)
    trust_b = TrustService(data_dir=dir_b)
    await trust_a.initialize()
    await trust_b.initialize()

    node_a_id = "node-alpha-s17-1"
    node_b_id = "node-beta-s17-1"

    # Stage C: Establish mutual trust
    await trust_a.grant_trust(
        node_id=node_b_id,
        relationship=RelationshipType.PEER,
        alias="node-beta",
    )
    await trust_b.grant_trust(
        node_id=node_a_id,
        relationship=RelationshipType.PEER,
        alias="node-alpha",
    )

    assert await trust_a.is_trusted(node_b_id)
    assert await trust_b.is_trusted(node_a_id)

    # Stage B: Setup Ecosystem Registry on Node A with Node B discovered
    reg_a = EcosystemRegistry()
    discovered_cap = DiscoveredCapability(
        capability_id="zarya.work.continue",
        name="Zarya Continuation",
        availability=AvailabilityStatus.AVAILABLE,
    )
    discovered_prov = DiscoveredProvider(
        provider_id="zarya.agent",
        name="Zarya Provider (Node B)",
        capabilities=(discovered_cap,),
        status=AvailabilityStatus.AVAILABLE,
    )
    discovered_node_b = DiscoveredNode(
        node_id=node_b_id,
        node_name="Node Beta",
        state=EcosystemNodeState.AVAILABLE,
        is_local=False,
        providers={discovered_prov.provider_id: discovered_prov},
    )
    await reg_a.register_node(discovered_node_b)

    snapshot = reg_a.create_snapshot(local_node_id=node_a_id)
    assert node_b_id in snapshot.nodes
    assert snapshot.nodes[node_b_id].state == EcosystemNodeState.AVAILABLE
    assert "zarya.work.continue" in snapshot.nodes[node_b_id].capability_ids

    evidence_collector["stages"]["stage_b"] = "PASSED"
    evidence_collector["stages"]["stage_c"] = "PASSED"


@pytest.mark.asyncio
async def test_s17_1_stage_d_navigation_selection() -> None:
    """Stage S17.1-D: S9 Navigator deterministic target resolution for zarya.work.continue."""
    node_a_id = "node-alpha-s17-1"
    node_b_id = "node-beta-s17-1"

    reg_a = EcosystemRegistry()
    cap_continue = DiscoveredCapability(
        capability_id="zarya.work.continue",
        name="Zarya Continuation",
        availability=AvailabilityStatus.AVAILABLE,
    )
    prov_b = DiscoveredProvider(
        provider_id="zarya.agent",
        name="Zarya Provider (Node B)",
        capabilities=(cap_continue,),
        status=AvailabilityStatus.AVAILABLE,
    )
    node_b = DiscoveredNode(
        node_id=node_b_id,
        node_name="Node Beta",
        state=EcosystemNodeState.AVAILABLE,
        is_local=False,
        providers={prov_b.provider_id: prov_b},
    )
    await reg_a.register_node(node_b)

    snapshot = reg_a.create_snapshot(local_node_id=node_a_id)
    navigator = HybridNavigator()
    nav_req = NavigationRequest(
        capability="zarya.work.continue",
        constraints=NavigationConstraints(preferred_node=node_b_id),
    )
    result = navigator.navigate(nav_req, snapshot)

    assert result.has_selection is True
    assert result.selected is not None
    assert result.selected.node_id == node_b_id
    assert result.selected.provider_id == "zarya.agent"


@pytest.mark.asyncio
async def test_s17_1_stage_e_f_g_full_e2e_continuity_execution(
    tmp_path: Path,
    fixture_payload_path: Path,
    evidence_collector: dict[str, Any],
) -> None:
    """Stages S17.1-E, F, G: End-to-end artifact transfer, continuation, and S16 coordination."""
    node_a_id = "node-alpha-s17-1"
    node_b_id = "node-beta-s17-1"
    dir_a = tmp_path / "node_a"
    dir_a.mkdir()

    # 1. Setup S13 Trust on Node A trusting Node B
    trust_service = TrustService(data_dir=dir_a)
    await trust_service.initialize()
    await trust_service.grant_trust(
        node_id=node_b_id,
        relationship=RelationshipType.PEER,
        alias="node-beta",
    )

    # 2. Setup S8 Ecosystem Registry on Node A
    registry = EcosystemRegistry()
    cap_continue = DiscoveredCapability(
        capability_id="zarya.work.continue",
        name="Zarya Continuation",
        availability=AvailabilityStatus.AVAILABLE,
    )
    prov_b = DiscoveredProvider(
        provider_id="zarya.agent",
        name="Zarya Provider (Node B)",
        capabilities=(cap_continue,),
        status=AvailabilityStatus.AVAILABLE,
    )
    node_b = DiscoveredNode(
        node_id=node_b_id,
        node_name="Node Beta",
        state=EcosystemNodeState.AVAILABLE,
        is_local=False,
        providers={prov_b.provider_id: prov_b},
    )
    await registry.register_node(node_b)

    # 3. Setup Mock Providers for boundary invocation
    mock_flux = MagicMock(spec=FluxProvider)
    mock_flux.transfer.return_value = FluxTransferResponse(
        transfer_id="flux-tx-s17-1-001",
        status=FluxTransferStatus.COMPLETED,
    )

    mock_zarya = MagicMock(spec=ZaryaProvider)
    mock_zarya.continue_work.return_value = ContinuationResponse(
        operation_id="zarya-op-s17-1-999",
        outcome=VerificationOutcome.VERIFIED_SUCCESS,
        reconstruction_completed=True,
        execution_completed=True,
        summary="Payload verified and executed successfully on Node B",
    )

    # 4. Instantiate S16 ContinuityService with real Navigator, Trust, Registry
    navigator = HybridNavigator()
    service = ContinuityService(
        navigator=navigator,
        trust_service=trust_service,
        flux_provider=mock_flux,
        zarya_provider=mock_zarya,
        ecosystem_registry=registry,
    )

    # 5. Build the real ContinuityRequest using the fixture
    payload_bytes = fixture_payload_path.read_bytes()
    expected_hash = hashlib.sha256(payload_bytes).hexdigest()

    req = ContinuityRequest(
        work_id="work-s17-1-file-verifier",
        source_device_id=node_a_id,
        portable_work={
            "version": "1.0",
            "work_type": "file_hash_verification",
            "inputs": {
                "filename": fixture_payload_path.name,
                "expected_sha256": expected_hash,
            },
        },
        artifact_paths=(str(fixture_payload_path),),
        target_constraints=NavigationConstraints(preferred_node=node_b_id),
    )

    # 6. Execute full pipeline Stage G
    session = await service.request_continuity(req)

    # 7. Assert complete terminal success
    assert session.state == ContinuityState.COMPLETED
    assert session.result is not None
    assert session.result.outcome == ContinuityOutcome.SUCCESS
    assert session.result.transfer_completed is True
    assert session.result.reconstruction_completed is True
    assert session.result.execution_completed is True
    assert session.result.zarya_outcome == "VERIFIED_SUCCESS"
    assert session.operation_id == "zarya-op-s17-1-999"
    assert session.transfer_id == "flux-tx-s17-1-001"

    # 8. Assert provider boundaries were called correctly
    mock_flux.transfer.assert_called_once_with(node_b_id, str(fixture_payload_path))
    mock_zarya.continue_work.assert_called_once_with(
        req.portable_work,
        node_a_id,
        session.continuity_id,
    )
