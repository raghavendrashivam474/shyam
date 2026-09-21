"""Integration tests for S13 Identity & Trust within the Shyam runtime."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.trust.models import RelationshipType, TrustStatus


@pytest.fixture
async def runtime() -> ShyamRuntime:
    """Create and start a minimal ShyamRuntime in a temp directory."""
    with tempfile.TemporaryDirectory() as tmp:
        settings = ShyamSettings(
            data_directory=Path(tmp),
            discovery_enabled=False,
            zarya_enabled=False,
            flux_enabled=False,
        )
        rt = ShyamRuntime(settings=settings)
        await rt.start()
        yield rt
        await rt.stop()


class TestRuntimeIdentityLifecycle:
    """Verify S13 identity components initialize correctly in the runtime."""

    @pytest.mark.asyncio
    async def test_identity_manager_initialized(self, runtime: ShyamRuntime) -> None:
        assert runtime.identity_manager is not None

    @pytest.mark.asyncio
    async def test_crypto_identity_initialized(self, runtime: ShyamRuntime) -> None:
        assert runtime.crypto_identity is not None
        assert runtime.crypto_identity.algorithm == "Ed25519"
        assert runtime.crypto_identity.public_key

    @pytest.mark.asyncio
    async def test_keypair_initialized(self, runtime: ShyamRuntime) -> None:
        assert runtime.keypair is not None
        data = b"runtime integration test"
        sig = runtime.keypair.sign(data)
        assert runtime.keypair.verify(data, sig)

    @pytest.mark.asyncio
    async def test_crypto_identity_matches_logical_identity(self, runtime: ShyamRuntime) -> None:
        identity = runtime.identity_manager.get_or_create_identity()
        assert runtime.crypto_identity.node_id == identity.node_id


class TestRuntimeTrustLifecycle:
    """Verify S13 trust service works within the runtime."""

    @pytest.mark.asyncio
    async def test_local_node_is_self_trusted(self, runtime: ShyamRuntime) -> None:
        local_id = str(runtime.crypto_identity.node_id)
        assert await runtime.trust.is_trusted(local_id)

    @pytest.mark.asyncio
    async def test_local_node_has_personal_relationship(self, runtime: ShyamRuntime) -> None:
        local_id = str(runtime.crypto_identity.node_id)
        rec = await runtime.trust.get_record(local_id)
        assert rec.relationship == RelationshipType.PERSONAL
        assert rec.metadata.get("is_local") is True

    @pytest.mark.asyncio
    async def test_unknown_node_not_trusted(self, runtime: ShyamRuntime) -> None:
        assert not await runtime.trust.is_trusted("random-unknown-node")

    @pytest.mark.asyncio
    async def test_grant_and_revoke_remote_node(self, runtime: ShyamRuntime) -> None:
        remote_id = "remote-laptop-xyz"
        await runtime.trust.grant_trust(
            remote_id,
            public_key="dGVzdA==",
            relationship=RelationshipType.PEER,
            alias="Work Laptop",
        )
        assert await runtime.trust.is_trusted(remote_id)
        await runtime.trust.revoke_trust(remote_id, reason="decommissioned")
        assert not await runtime.trust.is_trusted(remote_id)


class TestRuntimeEcosystemIntegration:
    """Verify S13 does not break S8/S12 ecosystem contracts."""

    @pytest.mark.asyncio
    async def test_ecosystem_context_has_local_node_id(self, runtime: ShyamRuntime) -> None:
        ctx = await runtime.get_ecosystem_context()
        assert ctx.local_node_id == str(runtime.crypto_identity.node_id)

    @pytest.mark.asyncio
    async def test_ecosystem_snapshot_works(self, runtime: ShyamRuntime) -> None:
        snapshot = await runtime.get_ecosystem_snapshot()
        assert snapshot.total_nodes >= 1
        assert snapshot.local_node_id == str(runtime.crypto_identity.node_id)

    @pytest.mark.asyncio
    async def test_ecosystem_state_works(self, runtime: ShyamRuntime) -> None:
        state = await runtime.get_ecosystem_state()
        assert state.total_nodes >= 1


class TestMultiNodeSimulation:
    """Simulate a multi-node trust scenario without networking."""

    @pytest.mark.asyncio
    async def test_multi_node_trust_topology(self, runtime: ShyamRuntime) -> None:
        # Simulate discovering three remote nodes
        node_b = "node-b-phone"
        node_c = "node-c-tablet"
        node_d = "node-d-old-laptop"

        # Trust B and C, revoke D
        await runtime.trust.grant_trust(node_b, alias="Phone", relationship=RelationshipType.PERSONAL)
        await runtime.trust.grant_trust(node_c, alias="Tablet", relationship=RelationshipType.PEER)
        await runtime.trust.grant_trust(node_d, alias="Old Laptop")
        await runtime.trust.revoke_trust(node_d, reason="sold device")

        # Verify topology
        trusted = await runtime.trust.get_trusted_node_ids()
        local_id = str(runtime.crypto_identity.node_id)
        assert local_id in trusted
        assert node_b in trusted
        assert node_c in trusted
        assert node_d not in trusted

        # Verify all records
        all_records = await runtime.trust.list_records()
        assert len(all_records) == 4  # local + B + C + D

        revoked = await runtime.trust.list_records(status_filter=TrustStatus.REVOKED)
        assert len(revoked) == 1
        assert revoked[0].node_id == node_d
