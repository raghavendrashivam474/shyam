"""Shyam Core Runtime orchestrator."""

import asyncio
import logging
from types import TracebackType
from typing import Self

from shyam.core.config import ShyamSettings
from shyam.core.lifecycle import InvalidStateTransitionError, LifecycleState
from shyam.core.logging import setup_logging
from shyam.core.state import RuntimeState
from shyam.events.bus import (
    EventBus,
    RuntimeErrorEvent,
    RuntimeStartedEvent,
    RuntimeStoppedEvent,
    RuntimeStoppingEvent,
)

logger = logging.getLogger("shyam.runtime")


class ShyamRuntime:
    """Standalone, local-first runtime core for Shyam."""

    def __init__(self, settings: ShyamSettings | None = None) -> None:
        self.settings = settings or ShyamSettings()
        self.state = RuntimeState()
        self.events = EventBus()
        self._lock = asyncio.Lock()
        setup_logging(self.settings)

    @property
    def status(self) -> LifecycleState:
        """Current lifecycle status of the runtime."""
        return self.state.status

    @property
    def is_running(self) -> bool:
        """True if the runtime is actively running."""
        return self.state.status == LifecycleState.RUNNING

    async def start(self) -> None:
        """Initialize and start the Shyam runtime."""
        async with self._lock:
            if self.state.status != LifecycleState.CREATED:
                raise InvalidStateTransitionError(self.state.status, LifecycleState.INITIALIZING)

            logger.info("Initializing Shyam runtime [%s]...", self.state.runtime_id)
            self.state.transition_to(LifecycleState.INITIALIZING)

            try:
                # Ensure local data directory exists
                self.settings.data_directory.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                self.state.transition_to(LifecycleState.ERROR, error_detail=str(exc))
                await self.events.publish(
                    RuntimeErrorEvent(runtime_id=self.state.runtime_id, error=str(exc))
                )
                logger.exception(
                    "Runtime initialization failed [%s]: %s", self.state.runtime_id, exc
                )
                raise

            self.state.transition_to(LifecycleState.RUNNING)
            logger.info(
                "Shyam runtime started [%s] in environment '%s'",
                self.state.runtime_id,
                self.settings.environment,
            )
            await self.events.publish(RuntimeStartedEvent(runtime_id=self.state.runtime_id))

    async def stop(self) -> None:
        """Gracefully stop the Shyam runtime. This operation is idempotent."""
        async with self._lock:
            if self.state.status == LifecycleState.STOPPED:
                return

            logger.info("Stopping Shyam runtime [%s]...", self.state.runtime_id)
            if self.state.status != LifecycleState.ERROR:
                self.state.transition_to(LifecycleState.STOPPING)
                await self.events.publish(RuntimeStoppingEvent(runtime_id=self.state.runtime_id))

            self.state.transition_to(LifecycleState.STOPPED)
            logger.info("Shyam runtime stopped [%s]", self.state.runtime_id)
            await self.events.publish(RuntimeStoppedEvent(runtime_id=self.state.runtime_id))

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.stop()
