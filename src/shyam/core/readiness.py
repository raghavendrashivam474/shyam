"""Readiness detection and lifecycle monitoring for the Shyam personal computing ecosystem.

Sovereign components (Zarya, Flux) start independently from Shyam.
ReadinessTracker monitors their availability through existing provider contracts,
determines the aggregated ecosystem readiness state, and adapts dynamically
to startup ordering and delayed availability.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import StrEnum
import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from shyam.capabilities.model import AvailabilityStatus
from shyam.events.bus import Event, EventBus

if TYPE_CHECKING:
    from shyam.capabilities.registry import CapabilityRegistry
    from shyam.providers.flux.provider import FluxProvider
    from shyam.providers.registry import ProviderRegistry
    from shyam.providers.zarya.provider import ZaryaProvider

logger = logging.getLogger("shyam.core.readiness")


class ComponentState(StrEnum):
    """Lifecycle/readiness state of an individual ecosystem component."""

    UNKNOWN = "unknown"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class EcosystemReadiness(StrEnum):
    """Aggregate readiness state of the entire personal computing ecosystem."""

    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ComponentReadinessSnapshot(BaseModel):
    """Point-in-time readiness observation for an individual component."""

    component: str
    state: ComponentState
    last_checked_at: datetime
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EcosystemReadinessSnapshot(BaseModel):
    """Aggregated ecosystem readiness status."""

    readiness: EcosystemReadiness
    components: dict[str, ComponentReadinessSnapshot]
    evaluated_at: datetime
    is_ready: bool = False
    details: str = ""


# --- Lifecycle Events ---


class ComponentReadinessChangedEvent(Event):
    """Published when a component changes its readiness state."""

    component: str
    old_state: ComponentState
    new_state: ComponentState
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EcosystemReadinessChangedEvent(Event):
    """Published when aggregate ecosystem readiness state changes."""

    old_readiness: EcosystemReadiness
    new_readiness: EcosystemReadiness
    component_states: dict[str, ComponentState] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Readiness Tracker ---


class ReadinessTracker:
    """Monitors component readiness and computes aggregate ecosystem state.

    Operates asynchronously in the background. Does not spawn, supervise,
    or restart sovereign components (Zarya, Flux). Discovers their state
    purely through existing provider interfaces.
    """

    def __init__(
        self,
        event_bus: EventBus,
        zarya_provider: ZaryaProvider | None = None,
        flux_provider: FluxProvider | None = None,
        provider_registry: ProviderRegistry | None = None,
        capability_registry: CapabilityRegistry | None = None,
        poll_interval: float = 3.0,
        zarya_enabled: bool = True,
        flux_enabled: bool = True,
    ) -> None:
        self.events = event_bus
        self.zarya_provider = zarya_provider
        self.flux_provider = flux_provider
        self.provider_registry = provider_registry
        self.capability_registry = capability_registry
        self.poll_interval = poll_interval
        self.zarya_enabled = zarya_enabled
        self.flux_enabled = flux_enabled

        self._components: dict[str, ComponentReadinessSnapshot] = {
            "node": ComponentReadinessSnapshot(
                component="node",
                state=ComponentState.STARTING,
                last_checked_at=datetime.now(timezone.utc),
            )
        }
        if self.zarya_enabled:
            self._components["zarya"] = ComponentReadinessSnapshot(
                component="zarya",
                state=ComponentState.STARTING,
                last_checked_at=datetime.now(timezone.utc),
            )
        if self.flux_enabled:
            self._components["flux"] = ComponentReadinessSnapshot(
                component="flux",
                state=ComponentState.STARTING,
                last_checked_at=datetime.now(timezone.utc),
            )

        self._readiness: EcosystemReadiness = EcosystemReadiness.STARTING
        self._lock = asyncio.Lock()
        self._poll_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def readiness(self) -> EcosystemReadiness:
        """Current aggregated ecosystem readiness."""
        return self._readiness

    @property
    def is_ready(self) -> bool:
        """Whether the ecosystem is fully ready."""
        return self._readiness == EcosystemReadiness.READY

    def set_node_ready(self) -> None:
        """Mark local node core runtime as READY."""
        now = datetime.now(timezone.utc)
        old_state = self._components["node"].state
        self._components["node"] = ComponentReadinessSnapshot(
            component="node",
            state=ComponentState.READY,
            last_checked_at=now,
        )
        if old_state != ComponentState.READY:
            asyncio.create_task(
                self.events.publish(
                    ComponentReadinessChangedEvent(
                        component="node",
                        old_state=old_state,
                        new_state=ComponentState.READY,
                    )
                )
            )

    async def start(self) -> None:
        """Start background readiness polling task."""
        async with self._lock:
            if self._running:
                return
            self._running = True
            # Perform initial poll
            await self._poll_all_components()
            self._poll_task = asyncio.create_task(self._poll_loop())
            logger.info("Readiness tracker started (poll interval: %ss)", self.poll_interval)

    async def stop(self) -> None:
        """Gracefully stop background readiness polling."""
        async with self._lock:
            if not self._running:
                return
            self._running = False
            if self._poll_task:
                self._poll_task.cancel()
                try:
                    await self._poll_task
                except asyncio.CancelledError:
                    pass
                self._poll_task = None
            logger.info("Readiness tracker stopped.")

    async def poll_now(self) -> EcosystemReadinessSnapshot:
        """Explicitly run a poll round and return the updated snapshot."""
        async with self._lock:
            await self._poll_all_components()
            return self._build_snapshot()

    def get_snapshot(self) -> EcosystemReadinessSnapshot:
        """Get the current point-in-time ecosystem readiness snapshot."""
        return self._build_snapshot()

    async def _poll_loop(self) -> None:
        """Periodic background evaluation loop."""
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval)
                async with self._lock:
                    if not self._running:
                        break
                    await self._poll_all_components()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error during readiness poll: %s", exc)

    async def _poll_all_components(self) -> None:
        """Evaluate readiness for each registered component."""
        now = datetime.now(timezone.utc)

        # 1. Zarya Check
        if self.zarya_enabled and self.zarya_provider:
            await self._evaluate_zarya(now)

        # 2. Flux Check
        if self.flux_enabled and self.flux_provider:
            await self._evaluate_flux(now)

        # 3. Aggregate ecosystem readiness calculation
        await self._evaluate_ecosystem_readiness(now)

    async def _evaluate_zarya(self, now: datetime) -> None:
        old_snap = self._components.get("zarya")
        old_state = old_snap.state if old_snap else ComponentState.UNKNOWN
        new_state = ComponentState.UNAVAILABLE
        err: str | None = None
        meta: dict[str, Any] = {}

        try:
            # If not connected yet, attempt connection
            if not getattr(self.zarya_provider, "_is_connected", False):
                connected = self.zarya_provider.connect()
                if connected:
                    new_state = ComponentState.READY
                else:
                    new_state = ComponentState.UNAVAILABLE
            else:
                status = self.zarya_provider.refresh_status()
                if status == AvailabilityStatus.AVAILABLE:
                    new_state = ComponentState.READY
                elif status == AvailabilityStatus.REGISTERED:
                    new_state = ComponentState.STARTING
                else:
                    new_state = ComponentState.UNAVAILABLE
        except Exception as exc:
            new_state = ComponentState.FAILED
            err = str(exc)

        # Update dynamic capabilities and providers if transitioning to READY
        if new_state == ComponentState.READY and old_state != ComponentState.READY:
            await self._on_zarya_ready()

        self._components["zarya"] = ComponentReadinessSnapshot(
            component="zarya",
            state=new_state,
            last_checked_at=now,
            error=err,
            metadata=meta,
        )

        if old_state != new_state:
            logger.info("Zarya readiness transition: %s -> %s", old_state.value, new_state.value)
            await self.events.publish(
                ComponentReadinessChangedEvent(
                    component="zarya",
                    old_state=old_state,
                    new_state=new_state,
                    error=err,
                )
            )

    async def _evaluate_flux(self, now: datetime) -> None:
        old_snap = self._components.get("flux")
        old_state = old_snap.state if old_snap else ComponentState.UNKNOWN
        new_state = ComponentState.UNAVAILABLE
        err: str | None = None
        meta: dict[str, Any] = {}

        try:
            # If not connected yet, attempt connection
            if not getattr(self.flux_provider, "_is_connected", False):
                connected = self.flux_provider.connect()
                if connected:
                    new_state = ComponentState.READY
                else:
                    new_state = ComponentState.UNAVAILABLE
            else:
                status = self.flux_provider.refresh_status()
                if status == AvailabilityStatus.AVAILABLE:
                    new_state = ComponentState.READY
                elif status == AvailabilityStatus.REGISTERED:
                    new_state = ComponentState.STARTING
                else:
                    new_state = ComponentState.UNAVAILABLE

            if getattr(self.flux_provider, "peer_id", None):
                meta["peer_id"] = self.flux_provider.peer_id
        except Exception as exc:
            new_state = ComponentState.FAILED
            err = str(exc)

        # Update dynamic capabilities and providers if transitioning to READY
        if new_state == ComponentState.READY and old_state != ComponentState.READY:
            await self._on_flux_ready()

        self._components["flux"] = ComponentReadinessSnapshot(
            component="flux",
            state=new_state,
            last_checked_at=now,
            error=err,
            metadata=meta,
        )

        if old_state != new_state:
            logger.info("Flux readiness transition: %s -> %s", old_state.value, new_state.value)
            await self.events.publish(
                ComponentReadinessChangedEvent(
                    component="flux",
                    old_state=old_state,
                    new_state=new_state,
                    error=err,
                )
            )

    async def _on_zarya_ready(self) -> None:
        """Synchronize provider & capability registries when Zarya becomes READY."""
        if not self.zarya_provider:
            return
        if self.provider_registry:
            await self.provider_registry.register(
                self.zarya_provider.descriptor,
                overwrite=True,
            )
        if self.capability_registry:
            for cap in self.zarya_provider.capability_definitions:
                await self.capability_registry.register(
                    cap,
                    overwrite=True,
                )

    async def _on_flux_ready(self) -> None:
        """Synchronize provider & capability registries when Flux becomes READY."""
        if not self.flux_provider:
            return
        if self.provider_registry:
            await self.provider_registry.register(
                self.flux_provider.descriptor,
                overwrite=True,
            )
        if self.capability_registry:
            for cap in self.flux_provider.capability_definitions:
                await self.capability_registry.register(
                    cap,
                    overwrite=True,
                )

    async def _evaluate_ecosystem_readiness(self, now: datetime) -> None:
        """Derive aggregate readiness from individual component states."""
        old_readiness = self._readiness

        node_state = self._components.get("node", ComponentReadinessSnapshot(
            component="node", state=ComponentState.UNKNOWN, last_checked_at=now
        )).state

        # If node core isn't ready, ecosystem cannot be ready
        if node_state != ComponentState.READY:
            new_readiness = EcosystemReadiness.STARTING
        else:
            active_states = []
            if self.zarya_enabled and "zarya" in self._components:
                active_states.append(self._components["zarya"].state)
            if self.flux_enabled and "flux" in self._components:
                active_states.append(self._components["flux"].state)

            if not active_states:
                # No external sovereign components enabled, node alone is READY
                new_readiness = EcosystemReadiness.READY
            elif all(s == ComponentState.READY for s in active_states):
                new_readiness = EcosystemReadiness.READY
            elif any(s == ComponentState.READY for s in active_states):
                # Partial availability: at least one sovereign component is ready
                new_readiness = EcosystemReadiness.DEGRADED
            elif any(s == ComponentState.STARTING for s in active_states):
                new_readiness = EcosystemReadiness.STARTING
            else:
                # All external enabled components UNAVAILABLE or FAILED
                new_readiness = EcosystemReadiness.DEGRADED

        self._readiness = new_readiness

        if old_readiness != new_readiness:
            logger.info(
                "Ecosystem readiness changed: %s -> %s",
                old_readiness.value,
                new_readiness.value,
            )
            states_map = {k: v.state for k, v in self._components.items()}
            await self.events.publish(
                EcosystemReadinessChangedEvent(
                    old_readiness=old_readiness,
                    new_readiness=new_readiness,
                    component_states=states_map,
                )
            )

    def _build_snapshot(self) -> EcosystemReadinessSnapshot:
        now = datetime.now(timezone.utc)
        details_list = []
        for name, comp in self._components.items():
            details_list.append(f"{name}: {comp.state.value.upper()}")

        return EcosystemReadinessSnapshot(
            readiness=self._readiness,
            components=dict(self._components),
            evaluated_at=now,
            is_ready=self.is_ready,
            details=", ".join(details_list),
        )
