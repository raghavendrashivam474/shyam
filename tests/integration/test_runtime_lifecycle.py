"""Integration tests verifying end-to-end runtime lifecycle and event flows."""

import pytest

from shyam import LifecycleState, ShyamRuntime, ShyamSettings
from shyam.events.bus import Event


class AppTaskEvent(Event):
    payload: str


@pytest.mark.asyncio
async def test_full_runtime_workflow_with_in_process_events(tmp_path):
    """Verify complete lifecycle: creation -> subscription -> startup -> events -> shutdown."""
    settings = ShyamSettings(
        environment="testing",
        data_directory=tmp_path / ".shyam_test",
        log_level="DEBUG",
        runtime_name="integration-test-node",
    )
    runtime = ShyamRuntime(settings=settings)
    received_app_events = []

    async def handle_app_event(event: AppTaskEvent) -> None:
        received_app_events.append(event.payload)

    await runtime.events.subscribe(AppTaskEvent, handle_app_event)

    async with runtime:
        assert runtime.status == LifecycleState.RUNNING
        assert runtime.state.runtime_id is not None
        assert runtime.state.started_at is not None

        # Dispatch internal app events during active runtime
        await runtime.events.publish(AppTaskEvent(payload="sync-data-batch-1"))
        await runtime.events.publish(AppTaskEvent(payload="sync-data-batch-2"))

    # Post-shutdown assertions
    assert runtime.status == LifecycleState.STOPPED
    assert runtime.state.stopped_at is not None
    assert received_app_events == ["sync-data-batch-1", "sync-data-batch-2"]
