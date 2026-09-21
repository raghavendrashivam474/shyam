"""Integration tests for S14 Peer Synchronization across multiple ShyamRuntime instances."""

from pathlib import Path

import pytest

from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.sync.models import SyncOutcome
from shyam.trust.models import RelationshipType


@pytest.mark.asyncio
async def test_runtime_peer_state_exchange_lifecycle(tmp_path: Path):
    """Verify state exchange and convergence between two running Shyam nodes."""
    dir_a = tmp_path / "node_a"
    dir_b = tmp_path / "node_b"

    settings_a = ShyamSettings(
        data_directory=dir_a,
        runtime_name="Node-Alpha",
        discovery_enabled=False,
        flux_enabled=False,
        zarya_enabled=False,
    )
    settings_b = ShyamSettings(
        data_directory=dir_b,
        runtime_name="Node-Beta",
        discovery_enabled=False,
        flux_enabled=False,
        zarya_enabled=False,
    )

    async with ShyamRuntime(settings_a) as runtime_a, ShyamRuntime(settings_b) as runtime_b:
        id_a = str(runtime_a.identity_manager.get_or_create_identity().node_id)
        id_b = str(runtime_b.identity_manager.get_or_create_identity().node_id)

        # Mutual trust grant
        await runtime_a.trust.grant_trust(
            node_id=id_b,
            public_key=runtime_b.crypto_identity.public_key,
            relationship=RelationshipType.PEER,
            alias="Beta",
        )
        await runtime_b.trust.grant_trust(
            node_id=id_a,
            public_key=runtime_a.crypto_identity.public_key,
            relationship=RelationshipType.PEER,
            alias="Alpha",
        )

        # Node A updates local facts
        await runtime_a.sync.update_local_facts(
            capabilities={id_a: ["shyam.runtime.inspect", "camera.stream"]},
            availability={id_a: "available"},
        )

        # Node A creates signed sync envelope
        envelope_a = await runtime_a.sync.create_sync_envelope()

        # Node B ingests and applies Node A's envelope
        res = await runtime_b.sync.process_incoming_envelope(envelope_a)
        assert res.outcome == SyncOutcome.APPLIED

        # Node B now accurately reflects Node A's state facts
        caps_b_has_for_a = await runtime_b.sync.get_node_capabilities(id_a)
        assert "camera.stream" in caps_b_has_for_a
        assert "shyam.runtime.inspect" in caps_b_has_for_a
        assert await runtime_b.sync.get_node_availability(id_a) == "available"
