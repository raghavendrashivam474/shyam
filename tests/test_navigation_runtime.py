"""Integration tests for Shyam S9 Hybrid Navigator and Runtime integration."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.navigation.models import NavigationRequest


@pytest.mark.anyio
async def test_runtime_navigation_integration() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = ShyamSettings(
            data_directory=Path(tmpdir),
            discovery_enabled=False,
            zarya_enabled=False,
            flux_enabled=False,
        )

        async with ShyamRuntime(settings) as runtime:
            # 1. Navigate for file.read (provided by local provider fabric)
            req = NavigationRequest(capability="file.read")
            result = await runtime.navigate(req)

            assert result.has_selection is True
            assert result.selected is not None
            assert result.selected.capability_id == "file.read"
            assert result.selected.provider_id == "local.filesystem"
            assert result.selected.is_local is True
            assert result.selected.node_id == str(runtime.identity_manager.get_or_create_identity().node_id)
            assert "local.filesystem" in result.reason

            # 2. Navigate for a non-existent capability
            bad_req = NavigationRequest(capability="quantum.compute")
            bad_result = await runtime.navigate(bad_req)

            assert bad_result.has_selection is False
            assert bad_result.selected is None
            assert len(bad_result.rejected) == 0
