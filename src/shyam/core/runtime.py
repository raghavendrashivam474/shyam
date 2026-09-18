"""Shyam Core Runtime orchestrator."""

import asyncio
import logging
from types import TracebackType
from typing import Self

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.capabilities.registry import CapabilityRegistry
from shyam.core.config import ShyamSettings
from shyam.core.lifecycle import InvalidStateTransitionError, LifecycleState
from shyam.core.logging import setup_logging
from shyam.core.state import RuntimeState
from shyam.discovery.model import NodeIdentityReadyEvent
from shyam.discovery.service import DiscoveryService
from shyam.events.bus import (
    EventBus,
    RuntimeErrorEvent,
    RuntimeStartedEvent,
    RuntimeStoppedEvent,
    RuntimeStoppingEvent,
)
from shyam.identity.manager import IdentityManager
from shyam.providers.registry import ProviderRegistry

logger = logging.getLogger("shyam.runtime")


class ShyamRuntime:
    """Standalone, local-first runtime core for Shyam."""

    def __init__(self, settings: ShyamSettings | None = None) -> None:
        self.settings = settings or ShyamSettings()
        self.state = RuntimeState()
        self.events = EventBus()
        self.capabilities = CapabilityRegistry(event_bus=self.events)
        self.providers = ProviderRegistry(event_bus=self.events)
        self._lock = asyncio.Lock()
        setup_logging(self.settings)

        # Components initialized on start()
        self.identity_manager: IdentityManager | None = None
        self.discovery: DiscoveryService | None = None

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

                # Initialize persistent node identity
                self.identity_manager = IdentityManager(
                    data_dir=self.settings.data_directory,
                    custom_node_name=self.settings.runtime_name,
                )
                identity = self.identity_manager.get_or_create_identity()

                # Publish S2 Identity Ready notification
                await self.events.publish(
                    NodeIdentityReadyEvent(
                        node_id=identity.node_id,
                        node_name=identity.node_name,
                        protocol_version=identity.protocol_version,
                    )
                )

                # Register default synthetic introspection capability (S3)
                await self.capabilities.register(
                    Capability(
                        capability_id="shyam.runtime.inspect",
                        name="Runtime Introspection",
                        version="1.0.0",
                        description="Inspect local Shyam node status, identity, and capabilities",
                        availability=AvailabilityStatus.AVAILABLE,
                    ),
                    overwrite=True,
                )

                # Launch Local Discovery Service if enabled
                if self.settings.discovery_enabled:
                    self.discovery = DiscoveryService(
                        identity_manager=self.identity_manager,
                        event_bus=self.events,
                        broadcast_port=self.settings.discovery_port,
                        broadcast_interval=self.settings.discovery_interval,
                        peer_expiry_interval=self.settings.discovery_expiry,
                    )
                    await self.discovery.start()

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

            # Shutdown S2 Local Peer Discovery Service
            if self.discovery:
                try:
                    await self.discovery.stop()
                except Exception as exc:
                    logger.exception("Failed to stop discovery service: %s", exc)

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
