"""Shyam Core Runtime orchestrator with S9 Hybrid Navigator."""

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
from shyam.discovery.ecosystem_models import EcosystemSnapshot
from shyam.discovery.ecosystem_registry import EcosystemRegistry
from shyam.discovery.ecosystem_service import EcosystemDiscoveryService
from shyam.discovery.model import (
    NodeIdentityReadyEvent,
    PeerDiscoveredEvent,
    PeerLostEvent,
    PeerUpdatedEvent,
)
from shyam.discovery.service import DiscoveryService
from shyam.events.bus import (
    EventBus,
    RuntimeErrorEvent,
    RuntimeStartedEvent,
    RuntimeStoppedEvent,
    RuntimeStoppingEvent,
)
from shyam.identity.manager import IdentityManager
from shyam.navigation.models import NavigationRequest, NavigationResult
from shyam.navigation.navigator import HybridNavigator
from shyam.providers.fabric import LocalProviderFabric
from shyam.providers.flux.provider import FluxProvider
from shyam.providers.registry import ProviderRegistry
from shyam.providers.zarya.provider import ZaryaProvider

logger = logging.getLogger("shyam.runtime")


class ShyamRuntime:
    """Standalone, local-first runtime core for Shyam."""

    def __init__(self, settings: ShyamSettings | None = None) -> None:
        self.settings = settings or ShyamSettings()
        self.state = RuntimeState()
        self.events = EventBus()
        self.capabilities = CapabilityRegistry(event_bus=self.events)
        self.providers = ProviderRegistry(event_bus=self.events)

        # In-memory Ecosystem Discovery Registry (S8)
        self.ecosystem_registry = EcosystemRegistry(event_bus=self.events)

        # Instantiate the S9 Hybrid Navigator
        self.navigator = HybridNavigator()

        # Instantiate the Local Provider Fabric (S5)
        self.provider_fabric = LocalProviderFabric(
            capability_registry=self.capabilities,
            provider_registry=self.providers,
        )

        # Instantiate the Zarya Provider Integration (S6)
        self.zarya_provider = ZaryaProvider(
            base_url=self.settings.zarya_url,
            token=self.settings.zarya_token,
        )

        # Instantiate the Flux Provider Integration (S7)
        self.flux_provider = FluxProvider(
            base_url=self.settings.flux_url,
        )

        self._lock = asyncio.Lock()
        setup_logging(self.settings)

        # Components initialized on start()
        self.identity_manager: IdentityManager | None = None
        self.discovery: DiscoveryService | None = None
        self.ecosystem: EcosystemDiscoveryService | None = None

    @property
    def status(self) -> LifecycleState:
        """Current lifecycle status of the runtime."""
        return self.state.status

    @property
    def is_running(self) -> bool:
        """True if the runtime is actively running."""
        return self.state.status == LifecycleState.RUNNING

    async def get_ecosystem_snapshot(self) -> EcosystemSnapshot:
        """Return the current normalized view of the ecosystem (S8)."""
        if self.ecosystem:
            return await self.ecosystem.discover()
        return self.ecosystem_registry.create_snapshot()

    async def navigate(self, request: NavigationRequest) -> NavigationResult:
        """Resolve a capability requirement against the current ecosystem snapshot (S9)."""
        snapshot = await self.get_ecosystem_snapshot()
        return self.navigator.navigate(request, snapshot)

    async def start(self) -> None:
        """Initialize and start the Shyam runtime."""
        async with self._lock:
            if self.state.status != LifecycleState.CREATED:
                raise InvalidStateTransitionError(
                    self.state.status,
                    LifecycleState.INITIALIZING,
                )

            logger.info(
                "Initializing Shyam runtime [%s]...",
                self.state.runtime_id,
            )
            self.state.transition_to(LifecycleState.INITIALIZING)

            try:
                self.settings.data_directory.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                self.identity_manager = IdentityManager(
                    data_dir=self.settings.data_directory,
                    custom_node_name=self.settings.runtime_name,
                )
                identity = self.identity_manager.get_or_create_identity()

                await self.events.publish(
                    NodeIdentityReadyEvent(
                        node_id=identity.node_id,
                        node_name=identity.node_name,
                        protocol_version=identity.protocol_version,
                    )
                )

                await self.capabilities.register(
                    Capability(
                        capability_id="shyam.runtime.inspect",
                        name="Runtime Introspection",
                        version="1.0.0",
                        description=("Inspect local Shyam node status, identity, and capabilities"),
                        availability=AvailabilityStatus.AVAILABLE,
                    ),
                    overwrite=True,
                )

                # Start the local provider fabric (S5)
                await self.provider_fabric.start()

                # Connect to Zarya sovereign agent if enabled (S6)
                if self.settings.zarya_enabled:
                    connected = self.zarya_provider.connect()
                    if connected:
                        logger.info("Integrated Zarya provider into runtime.")
                        await self.providers.register(
                            self.zarya_provider.descriptor,
                            overwrite=True,
                        )
                        for cap in self.zarya_provider.capability_definitions:
                            await self.capabilities.register(
                                cap,
                                overwrite=True,
                            )
                    else:
                        logger.info(
                            "Zarya not reachable at %s. Shyam continuing standalone.",
                            self.settings.zarya_url,
                        )

                # Connect to Flux connectivity gateway if enabled (S7)
                if self.settings.flux_enabled:
                    connected = self.flux_provider.connect()
                    if connected:
                        logger.info("Integrated Flux provider into runtime.")
                        await self.providers.register(
                            self.flux_provider.descriptor,
                            overwrite=True,
                        )
                        for cap in self.flux_provider.capability_definitions:
                            await self.capabilities.register(
                                cap,
                                overwrite=True,
                            )
                    else:
                        logger.info(
                            "Flux not reachable at %s. Shyam continuing standalone.",
                            self.settings.flux_url,
                        )

                # Instantiate and initialize Ecosystem Discovery Service (S8)
                self.ecosystem = EcosystemDiscoveryService(
                    local_identity=identity,
                    provider_registry=self.providers,
                    capability_registry=self.capabilities,
                    ecosystem_registry=self.ecosystem_registry,
                    zarya_provider=self.zarya_provider,
                    flux_provider=self.flux_provider,
                    event_bus=self.events,
                    stale_threshold_secs=self.settings.discovery_expiry,
                )
                await self.ecosystem.discover_local_node()

                # Wire UDP peer events to Ecosystem Discovery
                async def _on_udp_peer_discovered(event: PeerDiscoveredEvent) -> None:
                    if self.ecosystem:
                        await self.ecosystem.ingest_udp_peer(event.peer)

                async def _on_udp_peer_updated(event: PeerUpdatedEvent) -> None:
                    if self.ecosystem:
                        await self.ecosystem.ingest_udp_peer(event.peer)

                async def _on_udp_peer_lost(event: PeerLostEvent) -> None:
                    if self.ecosystem:
                        await self.ecosystem.handle_udp_peer_lost(event.node_id)

                await self.events.subscribe(PeerDiscoveredEvent, _on_udp_peer_discovered)
                await self.events.subscribe(PeerUpdatedEvent, _on_udp_peer_updated)
                await self.events.subscribe(PeerLostEvent, _on_udp_peer_lost)

                # Start UDP Discovery Service if enabled
                if self.settings.discovery_enabled:
                    self.discovery = DiscoveryService(
                        identity_manager=self.identity_manager,
                        event_bus=self.events,
                        broadcast_port=self.settings.discovery_port,
                        broadcast_interval=(self.settings.discovery_interval),
                        peer_expiry_interval=(self.settings.discovery_expiry),
                    )
                    await self.discovery.start()

            except Exception as exc:
                self.state.transition_to(
                    LifecycleState.ERROR,
                    error_detail=str(exc),
                )
                await self.events.publish(
                    RuntimeErrorEvent(
                        runtime_id=self.state.runtime_id,
                        error=str(exc),
                    )
                )
                logger.exception(
                    "Runtime init failed [%s]: %s",
                    self.state.runtime_id,
                    exc,
                )
                raise

            self.state.transition_to(LifecycleState.RUNNING)
            logger.info(
                "Shyam runtime started [%s] in '%s'",
                self.state.runtime_id,
                self.settings.environment,
            )
            await self.events.publish(
                RuntimeStartedEvent(
                    runtime_id=self.state.runtime_id,
                )
            )

    async def stop(self) -> None:
        """Gracefully stop the Shyam runtime. Idempotent."""
        async with self._lock:
            if self.state.status == LifecycleState.STOPPED:
                return

            logger.info(
                "Stopping Shyam runtime [%s]...",
                self.state.runtime_id,
            )

            try:
                await self.provider_fabric.stop()
            except Exception as exc:
                logger.exception(
                    "Failed to stop provider fabric: %s",
                    exc,
                )

            if self.discovery:
                try:
                    await self.discovery.stop()
                except Exception as exc:
                    logger.exception(
                        "Failed to stop discovery: %s",
                        exc,
                    )

            if self.state.status != LifecycleState.ERROR:
                self.state.transition_to(LifecycleState.STOPPING)
                await self.events.publish(
                    RuntimeStoppingEvent(
                        runtime_id=self.state.runtime_id,
                    )
                )

            self.state.transition_to(LifecycleState.STOPPED)
            logger.info(
                "Shyam runtime stopped [%s]",
                self.state.runtime_id,
            )
            await self.events.publish(
                RuntimeStoppedEvent(
                    runtime_id=self.state.runtime_id,
                )
            )

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
