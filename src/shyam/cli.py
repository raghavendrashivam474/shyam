"""Command-line interface for starting and managing Shyam runtime."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.surface.coordinator import SurfaceCoordinator
from shyam.surface.input import TextInputAdapter

logger = logging.getLogger("shyam.cli")


async def run_interactive_surface(coordinator: SurfaceCoordinator, stop_event: asyncio.Event) -> None:
    """Run an interactive prompt for human interaction."""
    input_adapter = TextInputAdapter()
    print("\n[Shyam Surface] Type your request below (or 'exit' to quit):")

    loop = asyncio.get_running_loop()
    while not stop_event.is_set():
        try:
            status_msg = coordinator.get_status_message()
            prompt_str = f"\n{status_msg}\n> "
            user_text = await loop.run_in_executor(None, input, prompt_str)
            user_text = user_text.strip()
            if not user_text:
                continue
            if user_text.lower() in ("exit", "quit"):
                stop_event.set()
                break

            req = input_adapter.create_request(user_text)
            resp = await coordinator.handle_request(req)
            print(f"\nShyam: {resp.message}")
        except (EOFError, KeyboardInterrupt):
            stop_event.set()
            break
        except Exception as exc:
            logger.exception("Error processing surface interaction: %s", exc)


async def run_runtime(
    settings: ShyamSettings | None = None,
    duration: float | None = None,
    interactive: bool = False,
    command: str | None = None,
) -> None:
    """Run the Shyam runtime instance with graceful shutdown handling.

    Args:
        settings: Optional ShyamSettings override.
        duration: Optional runtime duration in seconds (if None, runs until interrupted).
        interactive: If True, launch the interactive text surface loop.
        command: If provided, execute a single command via surface and exit.
    """
    runtime = ShyamRuntime(settings=settings)
    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        logger.info("Shutdown signal received.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except (NotImplementedError, AttributeError):
            signal.signal(sig, lambda _s, _f: _handle_signal())

    async with runtime:
        ident = runtime.identity_manager.identity if runtime.identity_manager else None
        node_id_str = str(ident.node_id) if ident else "unknown"
        node_name_str = ident.node_name if ident else "unknown"

        is_disc_active = bool(runtime.discovery and runtime.discovery._running)
        disc_status = "enabled" if is_disc_active else "disabled"

        logger.info("==================================================")
        logger.info("  🟢 SHYAM RUNTIME ONLINE")
        logger.info("  Runtime ID: %s", runtime.state.runtime_id)
        logger.info("  Node ID:    %s", node_id_str)
        logger.info("  Node Name:  %s", node_name_str)
        logger.info("  Discovery:  %s", disc_status)
        logger.info("==================================================")

        coordinator = SurfaceCoordinator(runtime=runtime)
        await coordinator.start()

        if command:
            input_adapter = TextInputAdapter()
            req = input_adapter.create_request(command)
            resp = await coordinator.handle_request(req)
            print(f"Shyam: {resp.message}")
            return

        if interactive:
            surface_task = asyncio.create_task(run_interactive_surface(coordinator, stop_event))
            try:
                if duration is not None:
                    await asyncio.wait_for(stop_event.wait(), timeout=duration)
                else:
                    await stop_event.wait()
            except TimeoutError:
                logger.info("Target duration elapsed.")
            finally:
                surface_task.cancel()
                try:
                    await surface_task
                except asyncio.CancelledError:
                    pass
        else:
            logger.info("Shyam is running. Press Ctrl+C to terminate.")
            try:
                if duration is not None:
                    await asyncio.wait_for(stop_event.wait(), timeout=duration)
                else:
                    await stop_event.wait()
            except TimeoutError:
                logger.info("Target duration elapsed.")
            except (asyncio.CancelledError, KeyboardInterrupt):
                logger.info("Interrupt received. Commencing shutdown...")


def main() -> None:
    """Synchronous entry point for CLI executions."""
    parser = argparse.ArgumentParser(description="Shyam Runtime & Surface Interface")
    parser.add_argument("--ui", action="store_true", help="Launch visual Shyam desktop surface")
    parser.add_argument("-i", "--interactive", action="store_true", help="Start interactive surface interface")
    parser.add_argument("-c", "--command", type=str, help="Execute a single surface command")
    parser.add_argument("-d", "--duration", type=float, help="Run for duration in seconds and exit")

    args = parser.parse_args()

    if args.ui:
        from shyam.ui.app import ShyamUIApp
        app = ShyamUIApp()
        try:
            app.start()
        except KeyboardInterrupt:
            app.stop()
        return

    try:
        asyncio.run(
            run_runtime(
                duration=args.duration,
                interactive=args.interactive,
                command=args.command,
            )
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
