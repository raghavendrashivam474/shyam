"""Command-line interface for starting and managing Shyam runtime."""

import asyncio
import logging
import signal

from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime

logger = logging.getLogger("shyam.cli")


async def run_runtime(settings: ShyamSettings | None = None, duration: float | None = None) -> None:
    """Run the Shyam runtime instance with graceful shutdown handling.

    Args:
        settings: Optional ShyamSettings override.
        duration: Optional runtime duration in seconds (if None, runs until interrupted).
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
        logger.info("  🟣 SHYAM RUNTIME ONLINE")
        logger.info("  Runtime ID: %s", runtime.state.runtime_id)
        logger.info("  Node ID:    %s", node_id_str)
        logger.info("  Node Name:  %s", node_name_str)
        logger.info("  Discovery:  %s", disc_status)
        logger.info("==================================================")
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
    try:
        asyncio.run(run_runtime())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
