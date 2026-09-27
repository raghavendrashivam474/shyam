"""Architectural boundary and contract verification tests for the UI layer."""

from __future__ import annotations

import ast
import asyncio
import pathlib
import pytest

import shyam.ui
import shyam.ui.app
import shyam.ui.window
from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.surface.coordinator import SurfaceCoordinator


def test_ui_layer_architectural_isolation():
    """Verify that shyam.ui does not bypass SurfaceCoordinator or directly touch internal subsystems."""
    ui_dir = pathlib.Path(shyam.ui.__file__).parent
    forbidden_modules = {
        "shyam.continuity.service",
        "shyam.navigation",
        "shyam.trust",
        "shyam.providers.flux",
        "shyam.providers.zarya",
        "shyam.workflow",
    }

    for py_file in ui_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8-sig"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_modules:
                        assert not alias.name.startswith(forbidden), (
                            f"Architectural bypass detected in {py_file.name}: "
                            f"UI layer is directly importing '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_modules:
                        assert not node.module.startswith(forbidden), (
                            f"Architectural bypass detected in {py_file.name}: "
                            f"UI layer is directly importing from '{node.module}'"
                        )


@pytest.mark.asyncio
async def test_ui_e2e_surface_flow(tk_root):
    """Test UI flow integrated with a real in-memory ShyamRuntime and SurfaceCoordinator."""
    settings = ShyamSettings(
        environment="testing",
        discovery_enabled=False,
        flux_enabled=False,
        zarya_enabled=False,
    )
    runtime = ShyamRuntime(settings=settings)

    async with runtime:
        coordinator = SurfaceCoordinator(runtime=runtime)
        await coordinator.start()

        window = shyam.ui.window.ShyamWindow(root=tk_root, coordinator=coordinator, loop=asyncio.get_running_loop())
        tk_root.update()

        # Standalone test runtime with local providers is READY
        assert window.symbol_label.cget("text") == "●"
        assert window.state_label.cget("text") == "Ready to help"

        # Submit unknown request
        window.input_entry.insert(0, "what is the weather today?")
        window.submit_input()

        # Allow the async task and Tk event queue to process
        await asyncio.sleep(0.05)
        tk_root.update()

        # Expect graceful response for unknown intent
        assert "not sure how to help" in window.message_label.cget("text").lower()