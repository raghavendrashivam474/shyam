"""Application runner for the visual Shyam UI."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import tkinter as tk
from typing import Callable

from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.surface.coordinator import SurfaceCoordinator
from shyam.ui.window import ShyamWindow

logger = logging.getLogger("shyam.ui.app")


class ShyamUIApp:
    """Manages the lifecycle of Shyam visual desktop application."""

    def __init__(self, settings: ShyamSettings | None = None) -> None:
        self.settings = settings
        self.runtime: ShyamRuntime | None = None
        self.coordinator: SurfaceCoordinator | None = None

        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()

        self.root: tk.Tk | None = None
        self.window: ShyamWindow | None = None

    def _run_async_loop(self) -> None:
        """Run the asyncio loop in the background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def _lifecycle():
            self.runtime = ShyamRuntime(settings=self.settings)
            async with self.runtime:
                self.coordinator = SurfaceCoordinator(runtime=self.runtime)
                await self.coordinator.start()
                self._ready_event.set()

                while not self._stop_event.is_set():
                    await asyncio.sleep(0.1)

        try:
            self._loop.run_until_complete(_lifecycle())
        except Exception as exc:
            logger.exception("Error in async runtime thread: %s", exc)
        finally:
            self._ready_event.set()
            self._loop.close()

    def start(self) -> None:
        """Start the application and run Tkinter mainloop on the main thread."""
        # 1. Start Async Engine Thread
        self._loop_thread = threading.Thread(
            target=self._run_async_loop,
            name="ShyamAsyncThread",
            daemon=True,
        )
        self._loop_thread.start()

        # Wait for runtime & coordinator to initialize
        if not self._ready_event.wait(timeout=10.0):
            raise TimeoutError("Timed out waiting for Shyam runtime initialization.")

        if not self.coordinator or not self.runtime:
            raise RuntimeError("Failed to initialize Shyam runtime or coordinator.")

        # 2. Start Tkinter Main Thread Window
        self.root = tk.Tk()
        self.window = ShyamWindow(
            root=self.root,
            coordinator=self.coordinator,
            loop=self._loop,
            on_close=self.stop,
        )

        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stop Tkinter GUI and signal runtime shutdown."""
        self._stop_event.set()

        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None

        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=3.0)


def main() -> None:
    """Entry point for standalone UI launch."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    app = ShyamUIApp()
    try:
        app.start()
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    main()
