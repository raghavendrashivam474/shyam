"""S16 Continuity domain models.

Frozen Pydantic models for continuity requests, targets, sessions,
and results. Strict identity separation per ADR-015.

Identity ownership:
    work_id       -> Zarya N2 (logical work)
    operation_id  -> Zarya N4/S18 (execution)
    device_id     -> S13 (device identity)
    artifact_id   -> Zarya N3 (artifact)
    transfer_id   -> Flux (transfer operation)
    continuity_id -> S16 (continuity attempt)
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shyam.continuity.state import ContinuityState
from shyam.navigation.models import NavigationConstraints


# ---------------------------------------------------------------------------
# Outcome
# ---------------------------------------------------------------------------

class ContinuityOutcome(StrEnum):
    """Final outcome of a continuity attempt.

    Distinct from Zarya S18 execution outcomes.
    S16 reports what *it* knows; Zarya reports execution truth.
    """

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class ContinuityRequest(BaseModel):
    """Describes a request to continue work on a different node.

    The portable_work field carries the Zarya N3 PortableWork
    representation as a plain dict. S16 does not interpret its
    internal structure — it passes it through to target Zarya N4.
    """

    model_config = ConfigDict(frozen=True)

    work_id: str = Field(
        ...,
        description="Logical work identity from Zarya N2.",
    )
    source_device_id: str = Field(
        ...,
        description="Device identity of the source node (S13).",
    )
    portable_work: dict[str, Any] = Field(
        ...,
        description="PortableWork dict representation from Zarya N3.",
    )
    artifact_paths: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Local file paths of artifacts required on the target.",
    )
    target_constraints: NavigationConstraints = Field(
        default_factory=NavigationConstraints,
        description="S9 navigation constraints for target selection.",
    )
    continuity_intent: str = Field(
        default="COPY",
        description="Semantic intent: COPY, HANDOFF, or MIGRATION. S16 first slice = COPY.",
    )

    @field_validator("work_id")
    @classmethod
    def validate_work_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("work_id must be a non-empty string")
        return v.strip()

    @field_validator("continuity_intent")
    @classmethod
    def validate_intent(cls, v: str) -> str:
        allowed = {"COPY", "HANDOFF", "MIGRATION"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"continuity_intent must be one of {allowed}, got '{v}'")
        return upper


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------

class ContinuityTarget(BaseModel):
    """Represents the selected target for continuity.

    References existing ecosystem identities — does not invent new ones.
    """

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(
        ...,
        description="Target node identity from S8/S9.",
    )
    provider_id: str = Field(
        ...,
        description="Target provider identity from S9.",
    )
    device_id: str = Field(
        ...,
        description="Target device identity from S13.",
    )
    trust_verified: bool = Field(
        default=False,
        description="Whether S13 trust has been verified for this target.",
    )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

class ContinuityResult(BaseModel):
    """What S16 knows about the outcome of a continuity attempt.

    Critical: this is NOT the same as Zarya S18 execution outcome.
    S16 preserves uncertainty — never converts reconstruction success
    into work completion.
    """

    model_config = ConfigDict(frozen=True)

    outcome: ContinuityOutcome = Field(
        ...,
        description="S16-level continuity outcome.",
    )
    transfer_completed: bool = Field(
        default=False,
        description="Whether Flux artifact transfer completed.",
    )
    reconstruction_completed: bool = Field(
        default=False,
        description="Whether target Zarya reconstruction completed.",
    )
    execution_completed: bool = Field(
        default=False,
        description="Whether target Zarya execution completed.",
    )
    zarya_outcome: str | None = Field(
        default=None,
        description="Raw Zarya S18 outcome: VERIFIED_SUCCESS, VERIFIED_FAILURE, or UNKNOWN.",
    )
    reason: str = Field(
        default="",
        description="Human-readable explanation of the outcome.",
    )


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class ContinuitySession(BaseModel):
    """Represents one continuity attempt from request to outcome.

    Identity separation:
        continuity_id != work_id != operation_id != transfer_id
    """

    model_config = ConfigDict(frozen=True)

    continuity_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique S16 continuity attempt identity.",
    )
    request: ContinuityRequest = Field(
        ...,
        description="The original continuity request.",
    )
    target: ContinuityTarget | None = Field(
        default=None,
        description="Selected target (populated after TARGET_SELECTED).",
    )
    state: ContinuityState = Field(
        default=ContinuityState.REQUESTED,
        description="Current lifecycle state.",
    )
    transfer_id: str | None = Field(
        default=None,
        description="Flux transfer identity (populated during TRANSFERRING).",
    )
    operation_id: str | None = Field(
        default=None,
        description="Target Zarya operation identity (populated during CONTINUING).",
    )
    result: ContinuityResult | None = Field(
        default=None,
        description="Final result (populated at terminal state).",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the continuity session was created.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the session was last updated.",
    )
