"""Unit tests for ShyamRuntime."""

import pytest

from shyam.core.config import ShyamSettings
from shyam.core.lifecycle import InvalidStateTransitionError, LifecycleState
from shyam.core.runtime import ShyamRuntime
from shyam.events.bus import RuntimeStartedEvent, RuntimeStoppedEvent, RuntimeStoppingEvent


@pytest.mark.asyncio
async def test_runtime_lifecycle_start_and_stop(tmp_path):
    """Verify clean start and stop transition cycle."""
    settings = ShyamSettings(data_directory=tmp_path / ".shyam")
    runtime = ShyamRuntime(settings=settings)

    assert runtime.status == LifecycleState.CREATED
    assert not runtime.is_running

    await runtime.start()
    assert runtime.status == LifecycleState.RUNNING
    assert runtime.is_running
    assert settings.data_directory.exists()

    await runtime.stop()
    assert runtime.status == LifecycleState.STOPPED
    assert not runtime.is_running


@pytest.mark.asyncio
async def test_runtime_emits_lifecycle_events(tmp_path):
    """Verify runtime fires lifecycle events."""
    settings = ShyamSettings(data_directory=tmp_path / ".shyam")
    runtime = ShyamRuntime(settings=settings)

    events_captured = []

    async def on_started(event: RuntimeStartedEvent) -> None:
        events_captured.append("started")

    async def on_stopping(event: RuntimeStoppingEvent) -> None:
        events_captured.append("stopping")

    async def on_stopped(event: RuntimeStoppedEvent) -> None:
        events_captured.append("stopped")

    await runtime.events.subscribe(RuntimeStartedEvent, on_started)
    await runtime.events.subscribe(RuntimeStoppingEvent, on_stopping)
    await runtime.events.subscribe(RuntimeStoppedEvent, on_stopped)

    await runtime.start()
    await runtime.stop()

    assert events_captured == ["started", "stopping", "stopped"]


@pytest.mark.asyncio
async def test_runtime_stop_is_idempotent(tmp_path):
    """Verify calling stop() multiple times does not raise error."""
    settings = ShyamSettings(data_directory=tmp_path / ".shyam")
    runtime = ShyamRuntime(settings=settings)

    await runtime.start()
    await runtime.stop()
    assert runtime.status == LifecycleState.STOPPED

    # Second stop should be a no-op
    await runtime.stop()
    assert runtime.status == LifecycleState.STOPPED


@pytest.mark.asyncio
async def test_runtime_cannot_start_twice(tmp_path):
    """Verify starting an already running runtime raises InvalidStateTransitionError."""
    settings = ShyamSettings(data_directory=tmp_path / ".shyam")
    runtime = ShyamRuntime(settings=settings)

    await runtime.start()
    with pytest.raises(InvalidStateTransitionError):
        await runtime.start()

    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_async_context_manager(tmp_path):
    """Verify runtime works seamlessly as an async context manager."""
    settings = ShyamSettings(data_directory=tmp_path / ".shyam")

    async with ShyamRuntime(settings=settings) as runtime:
        assert runtime.status == LifecycleState.RUNNING

    assert runtime.status == LifecycleState.STOPPED
