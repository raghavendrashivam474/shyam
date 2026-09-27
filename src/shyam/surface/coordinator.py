"""Surface Coordinator orchestrating human requests with the Shyam runtime."""

from __future__ import annotations

import logging
from typing import Any

from shyam.continuity.models import ContinuityOutcome, ContinuityRequest, ContinuityState
from shyam.core.readiness import EcosystemReadiness, EcosystemReadinessChangedEvent
from shyam.core.runtime import ShyamRuntime
from shyam.navigation.models import NavigationConstraints
from shyam.surface.models import InteractionRequest, InteractionResponse, SurfaceState, UserIntent
from shyam.surface.parser import IntentParser
from shyam.surface.presenter import Presenter

logger = logging.getLogger("shyam.surface.coordinator")


class SurfaceCoordinator:
    """Coordinates interaction between human inputs and the Shyam runtime."""

    def __init__(
        self,
        runtime: ShyamRuntime,
        parser: IntentParser | None = None,
        presenter: Presenter | None = None,
    ) -> None:
        self.runtime = runtime
        self.parser = parser or IntentParser()
        self.presenter = presenter or Presenter()
        self.current_state: SurfaceState = SurfaceState.IDLE
        self._subscribed = False

    async def start(self) -> None:
        """Initialize subscriptions to runtime events."""
        if not self._subscribed and self.runtime.events:
            await self.runtime.events.subscribe(
                EcosystemReadinessChangedEvent,
                self._on_readiness_changed,
            )
            self._subscribed = True

        # Sync initial state with current readiness
        readiness = self.runtime.readiness
        if readiness != EcosystemReadiness.READY:
            self.current_state = SurfaceState.DEGRADED
        else:
            self.current_state = SurfaceState.IDLE

    async def _on_readiness_changed(self, event: EcosystemReadinessChangedEvent) -> None:
        """Handle ecosystem readiness updates dynamically."""
        if event.new_readiness == EcosystemReadiness.READY:
            if self.current_state == SurfaceState.DEGRADED:
                self.current_state = SurfaceState.IDLE
        else:
            if self.current_state in (SurfaceState.IDLE, SurfaceState.DEGRADED):
                self.current_state = SurfaceState.DEGRADED

    def get_status_message(self) -> str:
        """Return the current transient status message."""
        return self.presenter.readiness_message(self.runtime.readiness)

    async def handle_request(self, request: InteractionRequest) -> InteractionResponse:
        """Process a human interaction request."""
        # 1. Check readiness
        if self.runtime.readiness != EcosystemReadiness.READY:
            self.current_state = SurfaceState.DEGRADED
            return self.presenter.degraded_response()

        # 2. Parse intent
        intent = self.parser.parse(request.text)
        if intent == UserIntent.UNKNOWN:
            return self.presenter.unknown_intent_response()

        # 3. Handle specific intents
        if intent == UserIntent.CONTINUE_WORK:
            return await self._handle_continue_work()

        return self.presenter.unknown_intent_response()

    async def _handle_continue_work(self) -> InteractionResponse:
        """Execute the continuity workflow slice."""
        self.current_state = SurfaceState.EXECUTING

        if not self.runtime.continuity_service:
            self.current_state = SurfaceState.FAILED
            return self.presenter.failure_response("Continuity service is not available.")

        # Resolve local node ID
        source_device_id = "unknown"
        if self.runtime.identity_manager:
            identity = self.runtime.identity_manager.get_or_create_identity()
            source_device_id = str(identity.node_id)

        # Build continuity request (defaulting to the active work slice)
        # Note: Portable work structure complies with Zarya / S16 specs
        continuity_req = ContinuityRequest(
            work_id="work-active-surface",
            source_device_id=source_device_id,
            portable_work={"source": "surface_request", "state": "active"},
            target_constraints=NavigationConstraints(capability="execute"),
            continuity_intent="COPY",
        )

        try:
            res = await self.runtime.continuity_service.request_continuity(continuity_req)
            outcome = None
            if hasattr(res, "result") and res.result is not None:
                outcome = getattr(res.result, "outcome", None)
            elif hasattr(res, "outcome"):
                outcome = getattr(res, "outcome", None)
            elif getattr(res, "state", None) == ContinuityState.COMPLETED:
                outcome = ContinuityOutcome.SUCCESS

            if outcome == ContinuityOutcome.SUCCESS:
                self.current_state = SurfaceState.COMPLETED
                return self.presenter.success_response()
            else:
                outcome_str = outcome.value if hasattr(outcome, "value") else str(outcome)
                self.current_state = SurfaceState.FAILED
                return self.presenter.failure_response(f"Continuity failed: {outcome_str}")
        except Exception as exc:
            logger.exception("Error executing continuity from surface: %s", exc)
            self.current_state = SurfaceState.FAILED
            return self.presenter.failure_response(str(exc))
