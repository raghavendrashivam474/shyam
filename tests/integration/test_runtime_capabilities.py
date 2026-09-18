"""Integration test for ShyamRuntime capability subsystem."""

import tempfile
from pathlib import Path

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime


class TestRuntimeCapabilities:
    """Integration test verifying ShyamRuntime initializes and operates the capability subsystem."""

    async def test_runtime_capability_lifecycle(self) -> None:
        """Verify default capability registration and runtime operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = ShyamSettings(
                data_directory=Path(tmpdir),
                discovery_enabled=False,
            )

            runtime = ShyamRuntime(settings=settings)

            # Pre-start: registry is empty
            assert runtime.capabilities.count == 0

            async with runtime:
                # Post-start: introspection (S3) + 3 filesystem caps (S5) = 4
                assert runtime.capabilities.count == 4
                assert "shyam.runtime.inspect" in runtime.capabilities

                inspect_cap = runtime.capabilities.get("shyam.runtime.inspect")
                assert inspect_cap is not None
                assert inspect_cap.availability == AvailabilityStatus.AVAILABLE

                # S5: verify fabric-registered capabilities exist
                assert "file.read" in runtime.capabilities
                assert "file.write" in runtime.capabilities
                assert "file.list" in runtime.capabilities

                # Register custom node capabilities at runtime
                await runtime.capabilities.register(
                    Capability(
                        capability_id="text.translate",
                        name="Text Translation",
                        version="1.0.0",
                        description="Translates between languages",
                        availability=AvailabilityStatus.AVAILABLE,
                    )
                )

                assert runtime.capabilities.count == 5
                assert "text.translate" in runtime.capabilities

                # Query capabilities through runtime
                available = runtime.capabilities.find(
                    availability=AvailabilityStatus.AVAILABLE
                )
                assert len(available) == 5

            # Post-stop: runtime stopped gracefully
            assert not runtime.is_running
