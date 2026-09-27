"""Surface-layer data models.

These models exist ONLY at the human-interaction boundary.
They do not replace or duplicate any internal Shyam models.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class SurfaceState(StrEnum):
    """Transient UI states visible to the human."""

    IDLE = "idle"
    LISTENING = "listening"
    UNDERSTANDING = "understanding"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"


class UserIntent(StrEnum):
    """Semantic intents parsed from human input.

    S17.6 first slice only supports CONTINUE_WORK.
    Later sprints will expand this enum.
    """

    CONTINUE_WORK = "continue_work"
    UNKNOWN = "unknown"


class InteractionRequest(BaseModel):
    """Raw human input normalised into a surface request."""

    text: str
    source: str = "text"  # "text" | "voice"


class InteractionResponse(BaseModel):
    """Human-readable response produced by the surface."""

    message: str
    state: SurfaceState
    detail: str | None = None
