"""Unit tests for CLI runner."""

import pytest

from shyam.cli import run_runtime
from shyam.core.config import ShyamSettings


@pytest.mark.asyncio
async def test_run_runtime_with_timeout(tmp_path):
    """Verify run_runtime initializes, runs, and gracefully exits on duration elapsed."""
    settings = ShyamSettings(
        environment="testing",
        data_directory=tmp_path / ".shyam_cli_test",
    )
    # Run with 0.05s timeout
    await run_runtime(settings=settings, duration=0.05)
