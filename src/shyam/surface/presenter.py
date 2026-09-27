"""Human-friendly message formatting for the surface layer.

Converts internal Shyam states and outcomes into plain-language
strings the user can understand.  Internal detail is preserved
in the ``detail`` field for logging/debugging but is NOT shown
to the user by default.
"""

from __future__ import annotations

from shyam.continuity.models import ContinuityOutcome
from shyam.core.readiness import EcosystemReadiness
from shyam.surface.models import InteractionResponse, SurfaceState


class Presenter:
    """Format internal states into human-readable responses."""

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    _READINESS_MESSAGES: dict[EcosystemReadiness, str] = {
        EcosystemReadiness.READY: "● Shyam is ready",
        EcosystemReadiness.STARTING: "◐ Shyam is getting things ready…",
        EcosystemReadiness.DEGRADED: "△ Some capabilities are unavailable",
        EcosystemReadiness.UNAVAILABLE: "○ Shyam is unavailable",
    }

    def readiness_message(self, readiness: EcosystemReadiness) -> str:
        return self._READINESS_MESSAGES.get(readiness, "○ Shyam status unknown")

    # ------------------------------------------------------------------
    # Continuity outcomes
    # ------------------------------------------------------------------

    def success_response(self) -> InteractionResponse:
        return InteractionResponse(
            message="Done — work continued on your other laptop.",
            state=SurfaceState.COMPLETED,
        )

    def executing_response(self) -> InteractionResponse:
        return InteractionResponse(
            message="Moving your work…",
            state=SurfaceState.EXECUTING,
        )

    def failure_response(self, detail: str | None = None) -> InteractionResponse:
        return InteractionResponse(
            message="I couldn't continue this work right now.",
            state=SurfaceState.FAILED,
            detail=detail,
        )

    def unknown_intent_response(self) -> InteractionResponse:
        return InteractionResponse(
            message="I'm not sure how to help with that yet.",
            state=SurfaceState.IDLE,
        )

    def degraded_response(self) -> InteractionResponse:
        return InteractionResponse(
            message="Shyam isn't fully ready yet. Try again in a moment.",
            state=SurfaceState.DEGRADED,
        )
