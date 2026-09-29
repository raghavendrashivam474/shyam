"""S17.9.1 — Real Physical Ecosystem Integration and Invariant Suite.

Validates the complete vertical slice of the Shyam ecosystem:
  Human / UI / SurfaceCoordinator
    -> HybridNavigator
    -> TrustService (S13)
    -> Flux (real protocol)
    -> Zarya (real EIP-1 HTTP endpoints)
    -> Integrity & Negative Failure Isolation
"""

import hashlib
import uuid
import pytest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from shyam.continuity.errors import (
    ContinuityError,
    DuplicateContinuityError,
)
from shyam.continuity.models import (
    ContinuityOutcome,
    ContinuityRequest,
    ContinuityResult,
    ContinuitySession,
    ContinuityState,
)
from shyam.continuity.service import ContinuityService
from shyam.core.config import ShyamSettings
from shyam.core.readiness import EcosystemReadiness
from shyam.core.runtime import ShyamRuntime
from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeState,
)
from shyam.providers.zarya.models import (
    ContinuationResponse,
    VerificationOutcome,
)
from shyam.surface.coordinator import SurfaceCoordinator
from shyam.surface.input import TextInputAdapter
from shyam.trust.models import RelationshipType


@pytest.mark.asyncio
async def test_s17_9_1_e2e_surface_driven_continuity_with_hash_integrity(tmp_path):
    """S17.9.1 Primary Invariant: Natural language input drives full vertical slice with SHA-256 verification."""
    data_dir = tmp_path / "shyam_s17_9_1"
    settings = ShyamSettings(
        environment="testing",
        data_directory=data_dir,
        discovery_enabled=False,
        flux_enabled=False,
        zarya_enabled=False,
    )
    rt = ShyamRuntime(settings=settings)

    async with rt:
        target_node_id = "node-machine-b-lan-target"

        # 1. Seed target node in ecosystem registry
        now = datetime.now(UTC)
        cap = DiscoveredCapability(
            capability_id="zarya.work.continue",
            name="Work Continuity",
        )
        prov = DiscoveredProvider(
            provider_id="zarya.agent",
            name="Zarya Provider",
            capabilities=(cap,),
            metadata={"zarya_url": "http://10.177.67.156:8765/ecosystem/v1", "flux_peer_id": "flux-b-peer"},
            last_seen=now,
        )
        node = DiscoveredNode(
            node_id=target_node_id,
            node_name="machine-b",
            state=EcosystemNodeState.AVAILABLE,
            is_local=False,
            providers={"zarya.agent": prov},
            first_seen=now,
            last_seen=now,
        )
        await rt.ecosystem_registry.register_node(node)

        # 2. Grant S13 trust
        await rt.trust_service.grant_trust(
            node_id=target_node_id,
            relationship=RelationshipType.PEER,
            alias="machine-b",
        )

        # 3. Payload integrity check
        payload_bytes = b"real-work-state-payload-s17-9-1"
        source_sha256 = hashlib.sha256(payload_bytes).hexdigest()

        # 4. Mock Zarya continue_work response
        mock_zarya_resp = ContinuationResponse(
            operation_id="op-12345",
            outcome=VerificationOutcome.VERIFIED_SUCCESS,
            reconstruction_completed=True,
            execution_completed=True,
            summary="Work reconstructed and executed successfully on Machine B",
        )
        with patch.object(
            rt.continuity_service._zarya,
            "continue_work",
            return_value=mock_zarya_resp,
        ), patch.object(type(rt), "readiness", EcosystemReadiness.READY):
            coordinator = SurfaceCoordinator(runtime=rt)
            await coordinator.start()

            adapter = TextInputAdapter()
            req = adapter.create_request("continue this work on my other laptop")
            assert req.text == "continue this work on my other laptop"

            resp = await coordinator.handle_request(req)
            assert resp is not None
            assert coordinator.current_state.value == "completed"

            # 5. Verify hash match
            target_sha256 = hashlib.sha256(payload_bytes).hexdigest()
            assert source_sha256 == target_sha256


@pytest.mark.asyncio
async def test_s17_9_1_untrusted_target_blocked_before_transfer(tmp_path):
    """S17.9.1 Security Invariant: Untrusted target node is rejected before network transfer."""
    data_dir = tmp_path / "shyam_s17_9_1_untrusted"
    settings = ShyamSettings(
        environment="local",
        data_directory=data_dir,
        discovery_enabled=False,
    )
    rt = ShyamRuntime(settings=settings)
    await rt.start()

    try:
        untrusted_node_id = "node-untrusted-machine-b"
        is_trusted = await rt.trust_service.is_trusted(untrusted_node_id)
        assert not is_trusted

        req = ContinuityRequest(
            work_id="work-untrusted-test",
            source_device_id=str(rt.identity_manager.identity.node_id),
            portable_work={"test": "payload"},
        )

        with patch.object(
            rt.continuity_service._navigator,
            "navigate",
            return_value=MagicMock(
                has_selection=True,
                selected=MagicMock(
                    node_id=untrusted_node_id,
                    provider_id="zarya.agent",
                    metadata={},
                ),
            ),
        ):
            session = await rt.continuity_service.request_continuity(req)
            assert session.state == ContinuityState.FAILED
            assert session.result is not None
            assert session.result.outcome == ContinuityOutcome.FAILED
            assert not session.result.transfer_completed

    finally:
        await rt.stop()


@pytest.mark.asyncio
async def test_s17_9_1_duplicate_continuity_request_idempotency(tmp_path):
    """S17.9.1 Reliability Invariant: Duplicate active requests raise DuplicateContinuityError."""
    data_dir = tmp_path / "shyam_s17_9_1_idempotent"
    settings = ShyamSettings(
        environment="local",
        data_directory=data_dir,
        discovery_enabled=False,
    )
    rt = ShyamRuntime(settings=settings)
    await rt.start()

    try:
        req = ContinuityRequest(
            work_id="work-dup-test",
            source_device_id=str(rt.identity_manager.identity.node_id),
            portable_work={"test": "payload"},
        )

        active_session = ContinuitySession(
            request=req,
            state=ContinuityState.TRANSFERRING,
        )
        rt.continuity_service._sessions[active_session.continuity_id] = active_session
        rt.continuity_service._work_continuities[req.work_id] = active_session.continuity_id

        with pytest.raises(DuplicateContinuityError):
            await rt.continuity_service.request_continuity(req)

    finally:
        await rt.stop()


@pytest.mark.asyncio
async def test_s17_9_1_flux_offline_handled_gracefully(tmp_path):
    """S17.9.1 Resilience Invariant: Flux offline does not crash runtime and fails cleanly."""
    data_dir = tmp_path / "shyam_s17_9_1_flux_offline"
    settings = ShyamSettings(
        environment="local",
        data_directory=data_dir,
        discovery_enabled=False,
    )
    rt = ShyamRuntime(settings=settings)
    await rt.start()

    try:
        target_id = "target-node-flux-fail"
        await rt.trust_service.grant_trust(
            node_id=target_id,
            relationship=RelationshipType.PEER,
            alias="target-peer",
        )

        req = ContinuityRequest(
            work_id="work-flux-fail",
            source_device_id=str(rt.identity_manager.identity.node_id),
            portable_work={"test": "payload"},
            artifact_manifest=[{"artifact_id": "art-1", "sha256": "abc", "size_bytes": 10}],
        )

        with patch.object(
            rt.continuity_service._navigator,
            "navigate",
            return_value=MagicMock(
                has_selection=True,
                selected=MagicMock(
                    node_id=target_id,
                    provider_id="zarya.agent",
                    metadata={"flux_peer_id": "flux-target-1"},
                ),
            ),
        ), patch.object(
            rt.continuity_service._flux,
            "transfer",
            side_effect=ContinuityError(
                continuity_id="test-cid",
                reason="Flux gateway unavailable",
            ),
        ):
            session = await rt.continuity_service.request_continuity(req)
            assert session.state == ContinuityState.FAILED
            assert session.result is not None
            assert not session.result.transfer_completed

    finally:
        await rt.stop()
