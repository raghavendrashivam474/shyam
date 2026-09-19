"""Unit tests for ShyamRuntime and S2 Integration."""

import pytest

from shyam.core.config import ShyamSettings
from shyam.core.lifecycle import InvalidStateTransitionError, LifecycleState
from shyam.core.runtime import ShyamRuntime
from shyam.discovery.model import NodeIdentityReadyEvent
from shyam.events.bus import (
    RuntimeStartedEvent,
    RuntimeStoppedEvent,
    RuntimeStoppingEvent,
)


@pytest.mark.asyncio
async def test_runtime_lifecycle_start_and_stop(tmp_path) -> None:
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
async def test_runtime_emits_lifecycle_events(tmp_path) -> None:
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
async def test_runtime_stop_is_idempotent(tmp_path) -> None:
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
async def test_runtime_cannot_start_twice(tmp_path) -> None:
    """Verify starting an already running runtime raises InvalidStateTransitionError."""
    settings = ShyamSettings(data_directory=tmp_path / ".shyam")
    runtime = ShyamRuntime(settings=settings)

    await runtime.start()
    with pytest.raises(InvalidStateTransitionError):
        await runtime.start()

    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_async_context_manager(tmp_path) -> None:
    """Verify runtime works seamlessly as an async context manager."""
    settings = ShyamSettings(data_directory=tmp_path / ".shyam")

    async with ShyamRuntime(settings=settings) as runtime:
        assert runtime.status == LifecycleState.RUNNING

    assert runtime.status == LifecycleState.STOPPED


@pytest.mark.asyncio
async def test_runtime_initializes_identity_and_discovery(tmp_path) -> None:
    """Verify runtime loads identity and launches discovery cleanly on start."""
    settings = ShyamSettings(
        data_directory=tmp_path / ".shyam",
        runtime_name="node-test-1",
        discovery_port=58999,  # isolated port
    )
    runtime = ShyamRuntime(settings=settings)

    identity_events = []

    async def on_ident(e: NodeIdentityReadyEvent) -> None:
        identity_events.append(e)

    await runtime.events.subscribe(NodeIdentityReadyEvent, on_ident)

    await runtime.start()

    assert runtime.identity_manager is not None
    assert runtime.discovery is not None
    assert runtime.discovery._running is True

    ident = runtime.identity_manager.identity
    assert ident is not None
    assert ident.node_name == "node-test-1"

    assert len(identity_events) == 1
    assert identity_events[0].node_id == ident.node_id

    await runtime.stop()
    assert runtime.discovery._running is False


@pytest.mark.asyncio
async def test_runtime_skips_discovery_when_disabled(tmp_path) -> None:
    """Verify runtime skips discovery initializing when discovery_enabled is False."""
    settings = ShyamSettings(
        data_directory=tmp_path / ".shyam",
        discovery_enabled=False,
    )
    runtime = ShyamRuntime(settings=settings)

    await runtime.start()

    assert runtime.identity_manager is not None
    assert runtime.identity_manager.identity is not None
    assert runtime.discovery is None

    await runtime.stop()
