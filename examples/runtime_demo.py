"""Demonstration of Shyam Core Runtime Lifecycle and In-Process Event Bus."""

import asyncio
from pathlib import Path

from shyam import ShyamRuntime, ShyamSettings
from shyam.events.bus import Event, RuntimeStartedEvent, RuntimeStoppedEvent


class HeartbeatEvent(Event):
    count: int
    message: str


async def main() -> None:
    print("==================================================")
    print("        🟣 SHYAM RUNTIME CORE DEMONSTRATION       ")
    print("==================================================")

    # 1. Configure settings
    settings = ShyamSettings(
        environment="development",
        data_directory=Path("./.shyam_demo_data"),
        log_level="INFO",
        runtime_name="demo-node-local",
    )

    # 2. Instantiate runtime
    runtime = ShyamRuntime(settings=settings)
    print(f"\n[Status before start]: {runtime.status.value}")

    # 3. Register event handlers
    async def on_runtime_started(event: RuntimeStartedEvent) -> None:
        print(f"--> [EVENT HANDLER] Runtime started with ID: {event.runtime_id}")

    async def on_heartbeat(event: HeartbeatEvent) -> None:
        ts = event.timestamp.isoformat()
        print(f"--> [EVENT HANDLER] Heartbeat #{event.count}: {event.message} at {ts}")

    async def on_runtime_stopped(event: RuntimeStoppedEvent) -> None:
        print(f"--> [EVENT HANDLER] Runtime stopped successfully: {event.runtime_id}")

    await runtime.events.subscribe(RuntimeStartedEvent, on_runtime_started)
    await runtime.events.subscribe(HeartbeatEvent, on_heartbeat)
    await runtime.events.subscribe(RuntimeStoppedEvent, on_runtime_stopped)

    # 4. Run through lifecycle using async context manager
    print("\n[Starting Shyam Runtime...]")
    async with runtime:
        print(f"[Status while running]: {runtime.status.value}")
        print(f"[Runtime ID]: {runtime.state.runtime_id}")
        print(f"[Started At]: {runtime.state.started_at}")

        # Dispatch sample domain events
        for i in range(1, 4):
            await asyncio.sleep(0.1)
            await runtime.events.publish(
                HeartbeatEvent(count=i, message=f"Runtime tick {i} healthy")
            )

        print("\n[Initiating graceful shutdown...]")

    print(f"[Status after exit]: {runtime.status.value}")
    print(f"[Stopped At]: {runtime.state.stopped_at}")
    print("\n==================================================")
    print("      DEMONSTRATION COMPLETED SUCCESSFULLY        ")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(main())
