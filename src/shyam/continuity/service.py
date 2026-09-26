from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from shyam.continuity.errors import (
    ArtifactTransferError,
    ContinuationRejectedError,
    ContinuityError,
    DuplicateContinuityError,
    InvalidContinuityTransitionError,
    TargetIneligibleError,
)
from shyam.continuity.models import (
    ContinuityOutcome,
    ContinuityRequest,
    ContinuityResult,
    ContinuitySession,
    ContinuityTarget,
)
from shyam.continuity.state import (
    ContinuityState,
    is_terminal,
    is_valid_transition,
)
from shyam.navigation.models import NavigationRequest
from shyam.providers.zarya.models import VerificationOutcome
from shyam.trust.models import TrustStatus

if TYPE_CHECKING:
    from shyam.discovery.ecosystem_registry import EcosystemRegistry
    from shyam.events.bus import EventBus
    from shyam.navigation.navigator import HybridNavigator
    from shyam.providers.flux.provider import FluxProvider
    from shyam.providers.zarya.provider import ZaryaProvider
    from shyam.trust.service import TrustService

logger = logging.getLogger("shyam.continuity.service")


class ContinuityService:
    """Coordinates cross-device work continuity.

    Dependencies are injected — S16 does not construct its own
    navigator, trust service, or providers.

    Lifecycle ownership:
        S16 owns the continuity lifecycle.
        S18 owns the execution lifecycle.
        Flux owns the transfer lifecycle.
    """

    def __init__(
        self,
        navigator: HybridNavigator,
        trust_service: TrustService,
        flux_provider: FluxProvider,
        zarya_provider: ZaryaProvider,
        ecosystem_registry: EcosystemRegistry,
        event_bus: EventBus | None = None,
    ) -> None:
        self._navigator = navigator
        self._trust = trust_service
        self._flux = flux_provider
        self._zarya = zarya_provider
        self._registry = ecosystem_registry
        self._events = event_bus
        self._sessions: dict[str, ContinuitySession] = {}
        self._work_continuities: dict[str, str] = {}  # work_id -> continuity_id
        self._lock = asyncio.Lock()

    @property
    def active_sessions(self) -> int:
        """Count of non-terminal continuity sessions."""
        return sum(
            1 for s in self._sessions.values()
            if not is_terminal(s.state)
        )

    def get_session(self, continuity_id: str) -> ContinuitySession | None:
        """Retrieve a continuity session by ID."""
        return self._sessions.get(continuity_id)

    # ── Public API ──────────────────────────────────────────────────────────

    async def request_continuity(
        self,
        request: ContinuityRequest,
    ) -> ContinuitySession:
        """Initiate a cross-device work continuity attempt.

        This is the main entry point. It runs the full coordination
        pipeline and returns the final session state.

        Args:
            request: The continuity request with work, artifacts,
                     and target constraints.

        Returns:
            ContinuitySession in a terminal state.

        Raises:
            DuplicateContinuityError: If work_id already has an
                active continuity attempt.
        """
        async with self._lock:
            # Idempotency check
            existing_id = self._work_continuities.get(request.work_id)
            if existing_id:
                existing = self._sessions.get(existing_id)
                if existing and not is_terminal(existing.state):
                    raise DuplicateContinuityError(
                        continuity_id=existing_id,
                        work_id=request.work_id,
                    )

            session = ContinuitySession(request=request)
            self._sessions[session.continuity_id] = session
            self._work_continuities[request.work_id] = session.continuity_id

        logger.info(
            "Continuity requested: %s (work=%s, source=%s)",
            session.continuity_id[:8],
            request.work_id,
            request.source_device_id,
        )

        # Run the coordination pipeline
        try:
            session = await self._run_pipeline(session)
        except ContinuityError:
            raise
        except Exception as exc:
            logger.exception(
                "Unexpected error in continuity %s",
                session.continuity_id[:8],
            )
            session = self._transition(
                session,
                ContinuityState.FAILED,
                result=ContinuityResult(
                    outcome=ContinuityOutcome.FAILED,
                    reason=f"Unexpected error: {exc}",
                ),
            )

        return session

    # ── Pipeline stages ──────────────────────────────────────────────────

    async def _run_pipeline(
        self,
        session: ContinuitySession,
    ) -> ContinuitySession:
        """Execute the full continuity coordination pipeline."""

        # Stage 1: VALIDATING
        session = self._transition(session, ContinuityState.VALIDATING)
        session = await self._validate(session)
        if is_terminal(session.state):
            return session

        # Stage 2: TARGET_SELECTED
        session = self._transition(session, ContinuityState.TARGET_SELECTED)
        session = await self._select_target(session)
        if is_terminal(session.state):
            return session

        # Stage 3: AUTHORIZED
        session = self._transition(session, ContinuityState.AUTHORIZED)
        session = await self._verify_trust(session)
        if is_terminal(session.state):
            return session

        # Stage 4: PREPARING
        session = self._transition(session, ContinuityState.PREPARING)
        session = await self._prepare_artifacts(session)
        if is_terminal(session.state):
            return session

        # Stage 5: TRANSFERRING
        session = self._transition(session, ContinuityState.TRANSFERRING)
        session = await self._transfer_artifacts(session)
        if is_terminal(session.state):
            return session

        # Stage 6: RECONSTRUCTING + CONTINUING (N4 handles internally)
        session = self._transition(session, ContinuityState.RECONSTRUCTING)
        session = self._transition(session, ContinuityState.CONTINUING)
        session = await self._continue_on_target(session)
        if is_terminal(session.state):
            return session

        # Stage 7: VERIFYING
        session = self._transition(session, ContinuityState.VERIFYING)
        session = self._verify_result(session)

        return session

    async def _validate(
        self,
        session: ContinuitySession,
    ) -> ContinuitySession:
        """Validate the continuity request."""
        req = session.request

        if not req.portable_work:
            return self._fail(session, "Empty portable_work")

        if not req.work_id:
            return self._fail(session, "Missing work_id")

        if req.continuity_intent == "MIGRATION":
            return self._transition(
                session,
                ContinuityState.UNSUPPORTED,
                result=ContinuityResult(
                    outcome=ContinuityOutcome.UNSUPPORTED,
                    reason="MIGRATION intent not supported in S16 first slice.",
                ),
            )

        return session

    async def _select_target(
        self,
        session: ContinuitySession,
    ) -> ContinuitySession:
        """Use S9 HybridNavigator to select a target node."""
        req = session.request

        try:
            snapshot = self._registry.create_snapshot()
            nav_request = NavigationRequest(
                capability="zarya.work.continue",
                constraints=req.target_constraints,
            )
            nav_result = self._navigator.navigate(nav_request, snapshot)

            if not nav_result.has_selection or nav_result.selected is None:
                return self._fail(
                    session,
                    f"No eligible target: {nav_result.reason}",
                )

            selected = nav_result.selected
            provider_meta = selected.metadata.get("provider", {}) if isinstance(selected.metadata.get("provider"), dict) else {}
            node_meta = selected.metadata.get("node", {}) if isinstance(selected.metadata.get("node"), dict) else {}

            flux_peer_id = (
                selected.metadata.get("flux_peer_id")
                or provider_meta.get("flux_peer_id")
                or node_meta.get("flux_peer_id")
            )
            zarya_url = (
                selected.metadata.get("zarya_url")
                or provider_meta.get("zarya_url")
                or node_meta.get("zarya_url")
            )
            target = ContinuityTarget(
                node_id=selected.node_id,
                provider_id=selected.provider_id,
                device_id=selected.node_id,  # S13 device mapping
                flux_peer_id=flux_peer_id,
                zarya_url=zarya_url,
            )

            # Rebuild session with target (frozen model)
            session = session.model_copy(
                update={
                    "target": target,
                    "updated_at": datetime.now(UTC),
                }
            )
            self._sessions[session.continuity_id] = session
            return session

        except Exception as exc:
            return self._fail(session, f"Target selection failed: {exc}")

    async def _verify_trust(
        self,
        session: ContinuitySession,
    ) -> ContinuitySession:
        """Verify S13 trust for the selected target."""
        if session.target is None:
            return self._fail(session, "No target selected")

        try:
            trust_record = await self._trust.get_record(
                session.target.device_id,
            )

            if trust_record is None or trust_record.status == TrustStatus.UNKNOWN:
                return self._fail(
                    session,
                    f"No trust relationship with {session.target.device_id}",
                )

            if trust_record.status != TrustStatus.TRUSTED:
                return self._fail(
                    session,
                    f"Target trust status: {trust_record.status}",
                )

            # Mark trust verified
            target = session.target.model_copy(
                update={"trust_verified": True}
            )
            session = session.model_copy(
                update={
                    "target": target,
                    "updated_at": datetime.now(UTC),
                }
            )
            self._sessions[session.continuity_id] = session
            return session

        except Exception as exc:
            return self._fail(session, f"Trust verification failed: {exc}")

    async def _prepare_artifacts(
        self,
        session: ContinuitySession,
    ) -> ContinuitySession:
        """Determine required artifacts for transfer."""
        # For the first vertical slice, artifacts come from the request.
        # Future: inspect PortableWork to derive artifact list.
        return session

    async def _transfer_artifacts(
        self,
        session: ContinuitySession,
    ) -> ContinuitySession:
        """Use Flux to transfer required artifacts to the target."""
        if session.target is None:
            return self._fail(session, "No target for transfer")

        req = session.request
        if not req.artifact_paths:
            # No artifacts to transfer — skip
            session = session.model_copy(
                update={
                    "result": ContinuityResult(
                        outcome=ContinuityOutcome.SUCCESS,
                        transfer_completed=True,
                    ),
                    "updated_at": datetime.now(UTC),
                }
            )
            self._sessions[session.continuity_id] = session
            return session

        try:
            loop = asyncio.get_running_loop()
            last_transfer_id = None

            for artifact_path in req.artifact_paths:
                transfer_target = session.target.flux_peer_id or session.target.node_id
                transfer_result = await loop.run_in_executor(
                    None,
                    self._flux.transfer,
                    transfer_target,
                    artifact_path,
                )
                last_transfer_id = getattr(
                    transfer_result, "transfer_id", None
                )

            session = session.model_copy(
                update={
                    "transfer_id": last_transfer_id,
                    "updated_at": datetime.now(UTC),
                }
            )
            self._sessions[session.continuity_id] = session
            return session

        except Exception as exc:
            return self._fail(
                session,
                f"Artifact transfer failed: {exc}",
                outcome=ContinuityOutcome.FAILED,
            )

    async def _continue_on_target(
        self,
        session: ContinuitySession,
    ) -> ContinuitySession:
        """Invoke Zarya N4 continue_work on the target."""
        if session.target is None:
            return self._fail(session, "No target for continuation")

        req = session.request

        try:
            loop = asyncio.get_running_loop()
            if session.target.zarya_url:
                continuation_resp = await loop.run_in_executor(
                    None,
                    self._zarya.continue_work,
                    req.portable_work,
                    req.source_device_id,
                    session.continuity_id,
                    session.target.zarya_url,
                )
            else:
                continuation_resp = await loop.run_in_executor(
                    None,
                    self._zarya.continue_work,
                    req.portable_work,
                    req.source_device_id,
                    session.continuity_id,
                )

            session = session.model_copy(
                update={
                    "operation_id": continuation_resp.operation_id,
                    "result": ContinuityResult(
                        outcome=self._map_zarya_outcome(
                            continuation_resp.outcome
                        ),
                        transfer_completed=True,
                        reconstruction_completed=(
                            continuation_resp.reconstruction_completed
                        ),
                        execution_completed=(
                            continuation_resp.execution_completed
                        ),
                        zarya_outcome=continuation_resp.outcome.value,
                        reason=continuation_resp.summary,
                    ),
                    "updated_at": datetime.now(UTC),
                }
            )
            self._sessions[session.continuity_id] = session
            return session

        except Exception as exc:
            return self._fail(
                session,
                f"Target continuation failed: {exc}",
            )

    def _verify_result(
        self,
        session: ContinuitySession,
    ) -> ContinuitySession:
        """Inspect the continuation result and set final outcome."""
        if session.result is None:
            return self._transition(
                session,
                ContinuityState.UNKNOWN,
                result=ContinuityResult(
                    outcome=ContinuityOutcome.UNKNOWN,
                    reason="No result to verify.",
                ),
            )

        result = session.result

        # Preserve uncertainty per the brief:
        # reconstruction success != work completion
        if result.zarya_outcome == VerificationOutcome.VERIFIED_SUCCESS.value:
            final_outcome = ContinuityOutcome.SUCCESS
        elif result.zarya_outcome == VerificationOutcome.VERIFIED_FAILURE.value:
            final_outcome = ContinuityOutcome.FAILED
        else:
            # UNKNOWN or anything else stays UNKNOWN
            final_outcome = ContinuityOutcome.UNKNOWN

        final_result = result.model_copy(
            update={"outcome": final_outcome}
        )

        if final_outcome == ContinuityOutcome.SUCCESS:
            return self._transition(
                session,
                ContinuityState.COMPLETED,
                result=final_result,
            )
        elif final_outcome == ContinuityOutcome.FAILED:
            return self._transition(
                session,
                ContinuityState.FAILED,
                result=final_result,
            )
        else:
            return self._transition(
                session,
                ContinuityState.UNKNOWN,
                result=final_result,
            )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _transition(
        self,
        session: ContinuitySession,
        target_state: ContinuityState,
        result: ContinuityResult | None = None,
    ) -> ContinuitySession:
        """Perform a validated state transition."""
        if not is_valid_transition(session.state, target_state):
            raise InvalidContinuityTransitionError(
                continuity_id=session.continuity_id,
                current=session.state.value,
                attempted=target_state.value,
            )

        updates: dict[str, Any] = {
            "state": target_state,
            "updated_at": datetime.now(UTC),
        }
        if result is not None:
            updates["result"] = result

        session = session.model_copy(update=updates)
        self._sessions[session.continuity_id] = session

        logger.debug(
            "Continuity %s -> %s",
            session.continuity_id[:8],
            target_state.value,
        )
        return session

    def _fail(
        self,
        session: ContinuitySession,
        reason: str,
        outcome: ContinuityOutcome = ContinuityOutcome.FAILED,
    ) -> ContinuitySession:
        """Transition to FAILED with a reason."""
        return self._transition(
            session,
            ContinuityState.FAILED,
            result=ContinuityResult(
                outcome=outcome,
                reason=reason,
            ),
        )

    @staticmethod
    def _map_zarya_outcome(
        zarya_outcome: VerificationOutcome,
    ) -> ContinuityOutcome:
        """Map Zarya S18 outcome to S16 continuity outcome.

        Deliberately conservative: only VERIFIED_SUCCESS maps to
        SUCCESS. Everything else preserves uncertainty.
        """
        if zarya_outcome == VerificationOutcome.VERIFIED_SUCCESS:
            return ContinuityOutcome.SUCCESS
        elif zarya_outcome == VerificationOutcome.VERIFIED_FAILURE:
            return ContinuityOutcome.FAILED
        return ContinuityOutcome.UNKNOWN
