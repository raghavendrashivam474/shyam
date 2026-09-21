"""Shyam Core Runtime orchestrator with S12 Ecosystem Context, S13 Identity/Trust & S14 Peer Sync."""

import asyncio
import logging
from types import TracebackType
from typing import Any, Self

from shyam.capabilities.model import AvailabilityStatus, Capability
from shyam.capabilities.registry import CapabilityRegistry
from shyam.composite import (
    CompositeCapabilityRegistry,
    CompositeEngine,
    CompositeResult,
)
from shyam.context import (
    EcosystemContext,
    EcosystemContextService,
    EcosystemState,
    EcosystemStateStore,
)
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
from shyam.identity import (
    CryptoIdentity,
    IdentityManager,
    KeyPair,
    load_or_create_keypair,
)
from shyam.navigation.models import NavigationRequest, NavigationResult
from shyam.navigation.navigator import HybridNavigator
from shyam.providers.fabric import LocalProviderFabric
from shyam.providers.flux.provider import FluxProvider
from shyam.providers.registry import ProviderRegistry
from shyam.providers.zarya.provider import ZaryaProvider
from shyam.sync import SyncService
from shyam.trust import RelationshipType, TrustRecord, TrustService, TrustStatus

# S10 Workflow subsystem imports
from shyam.workflow.engine import WorkflowCancellationToken, WorkflowEngine
from shyam.workflow.executor import ExecutorRegistry
from shyam.workflow.executors.flux import FluxExecutor
from shyam.workflow.executors.local_fs import LocalFilesystemExecutor
from shyam.workflow.executors.zarya import ZaryaExecutor
from shyam.workflow.models import Workflow, WorkflowResult

logger = logging.getLogger("shyam.runtime")


class ShyamRuntime:
    """Standalone, local-first runtime core for Shyam with S13 Trust and S14 Peer Synchronization."""

    def __init__(self, settings: ShyamSettings | None = None) -> None:
        self.settings = settings or ShyamSettings()
        self.state = RuntimeState()
        self.events = EventBus()
        self.capabilities = CapabilityRegistry(event_bus=self.events)
        self.providers = ProviderRegistry(event_bus=self.events)

        # In-memory Ecosystem Discovery Registry (S8)
        self.ecosystem_registry = EcosystemRegistry(event_bus=self.events)

        # Instantiate S12 state store and coordinator service
        self.state_store = EcosystemStateStore()
        self.context_service = EcosystemContextService(
            registry=self.ecosystem_registry,
            event_bus=self.events,
            store=self.state_store,
        )

        # Instantiate S13 Trust Service
        self.trust_service = TrustService(
            data_dir=self.settings.data_directory,
            event_bus=self.events,
        )

        # S14 Sync Service (initialized in start() when identity/keypair are loaded)
        self.sync_service: SyncService | None = None

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

        # S10: Setup Capability Execution Boundary and Workflow Engine
        self.executor_registry = ExecutorRegistry()
        self.executor_registry.register("local.filesystem", LocalFilesystemExecutor())
        self.executor_registry.register("zarya.sovereign", ZaryaExecutor(self.zarya_provider))
        self.executor_registry.register("flux.connectivity", FluxExecutor(self.flux_provider))

        self.workflow_engine = WorkflowEngine(
            navigator_fn=self.navigate,
            executor_registry=self.executor_registry,
            event_bus=self.events,
        )

        # S11: Setup Composite Capability Subsystem
        self.composites = CompositeCapabilityRegistry()
        self.composite_engine = CompositeEngine(
            workflow_engine=self.workflow_engine,
            registry=self.composites,
        )

        self._lock = asyncio.Lock()
        setup_logging(self.settings)

        # S13 Components initialized on start()
        self.identity_manager: IdentityManager | None = None
        self.crypto_identity: CryptoIdentity | None = None
        self.keypair: KeyPair | None = None

        # S8 / Network components initialized on start()
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

    @property
    def trust(self) -> TrustService:
        """Access the S13 Trust Service."""
        return self.trust_service

    @property
    def sync(self) -> SyncService:
        """Access the S14 Peer Synchronization Service."""
        if self.sync_service is None:
            raise RuntimeError("SyncService is not initialized. Runtime must be started first.")
        return self.sync_service

    async def get_ecosystem_snapshot(self) -> EcosystemSnapshot:
        """Return the current normalized view of the ecosystem (S8)."""
        if self.ecosystem:
            return await self.ecosystem.discover()
        return self.ecosystem_registry.create_snapshot()

    async def get_ecosystem_state(self) -> EcosystemState:
        """Return a frozen snapshot of current state and active workflows (S12)."""
        snapshot = await self.get_ecosystem_snapshot()
        await self.state_store.update_discovery(snapshot)
        return await self.state_store.get_state()

    async def get_ecosystem_context(self) -> EcosystemContext:
        """Return a frozen context view detailing situational awareness (S12)."""
        snapshot = await self.get_ecosystem_snapshot()
        await self.state_store.update_discovery(snapshot)
        return await self.state_store.get_context()

    async def navigate(self, request: NavigationRequest) -> NavigationResult:
        """Resolve a capability requirement against the current ecosystem snapshot (S9)."""
        snapshot = await self.get_ecosystem_snapshot()
        return self.navigator.navigate(request, snapshot)

    async def invoke_composite(
        self,
        capability_id: str,
        inputs: dict[str, Any],
        cancellation_token: WorkflowCancellationToken | None = None,
    ) -> CompositeResult:
        """Invoke a composite capability by resolving bindings and running steps through S10."""
        logger.info("Executing composite capability '%s' via runtime engine...", capability_id)
        return await self.composite_engine.invoke(capability_id, inputs, cancellation_token)

    async def run_workflow(
        self,
        workflow: Workflow,
        cancellation_token: WorkflowCancellationToken | None = None,
    ) -> WorkflowResult:
        """Execute a multi-step Workflow sequentially using S9 Navigator and S10 Executors."""
        logger.info("Executing workflow '%s' [%s] via runtime engine...", workflow.name, workflow.workflow_id)
        return await self.workflow_engine.run(workflow, cancellation_token)

    async def start(self) -> None:
        """Initialize and start the Shyam runtime with S13 identity & S14 sync setup."""
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

                # S13.1: Logical Identity initialization
                self.identity_manager = IdentityManager(
                    data_dir=self.settings.data_directory,
                    custom_node_name=self.settings.runtime_name,
                )
                identity = self.identity_manager.get_or_create_identity()

                # S13.2: Cryptographic Identity & KeyPair initialization
                self.keypair, self.crypto_identity = load_or_create_keypair(
                    data_dir=self.settings.data_directory,
                    node_id=identity.node_id,
                )

                # S13.3: Trust Service initialization & self-trust registration
                await self.trust_service.initialize()
                await self.trust_service.grant_trust(
                    node_id=str(identity.node_id),
                    public_key=self.crypto_identity.public_key,
                    relationship=RelationshipType.PERSONAL,
                    alias=identity.node_name,
                    metadata={"is_local": True},
                )

                # S14: Peer Synchronization Service initialization
                self.sync_service = SyncService(
                    local_node_id=identity.node_id,
                    keypair=self.keypair,
                    trust_service=self.trust_service,
                    event_bus=self.events,
                )

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

                # Start the S12 Context Service to monitor the ecosystem
                await self.context_service.start()

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

            # Stop the S12 Context Service first to clean up listeners
            try:
                await self.context_service.stop()
            except Exception as exc:
                logger.exception(
                    "Failed to stop context service: %s",
                    exc,
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
