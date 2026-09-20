"""Integration tests for S8 Ecosystem Discovery in ShyamRuntime."""

import pytest
from pathlib import Path

from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.discovery.ecosystem_models import EcosystemNodeState


@pytest.mark.asyncio
async def test_runtime_starts_with_ecosystem_discovery(tmp_path: Path):
    settings = ShyamSettings(
        data_directory=tmp_path / "data",
        runtime_name="test-s8-node",
        discovery_enabled=False,
        zarya_enabled=False,
        flux_enabled=False,
    )

    runtime = ShyamRuntime(settings=settings)
    await runtime.start()

    try:
        assert runtime.ecosystem is not None
        assert runtime.ecosystem_registry.count == 1

        # Check ecosystem snapshot
        snapshot = await runtime.get_ecosystem_snapshot()
        assert snapshot.total_nodes == 1
        assert len(snapshot.active_nodes) == 1

        local_node = snapshot.nodes[snapshot.local_node_id]
        assert local_node.node_name == "test-s8-node"
        assert local_node.is_local is True
        assert local_node.state == EcosystemNodeState.AVAILABLE
        assert "local.filesystem" in local_node.providers
    finally:
        await runtime.stop()
