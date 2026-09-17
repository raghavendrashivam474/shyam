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
