"""Navigation Domain Models - S9.

Frozen Pydantic models for navigation requests, candidates, and results.
These are provider-independent and operate on the normalized S8 ecosystem
snapshot abstractions.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shyam.capabilities.model import AvailabilityStatus
from shyam.discovery.ecosystem_models import EcosystemNodeState


class NavigationConstraints(BaseModel):
    """Optional constraints that narrow candidate selection."""

    model_config = ConfigDict(frozen=True)

    preferred_node: str | None = Field(
        default=None,
        description="If set, prefer this node_id when multiple candidates are valid.",
    )
    preferred_provider: str | None = Field(
        default=None,
        description="If set, prefer this provider_id when multiple candidates are valid.",
    )
    local_only: bool = Field(
        default=False,
        description="If True, reject all non-local candidates.",
    )
    remote_allowed: bool = Field(
        default=True,
        description="If False, reject all non-local candidates (alias for local_only).",
    )
    required_node_state: EcosystemNodeState | None = Field(
        default=None,
        description="If set, candidates whose node state differs are rejected.",
    )
    required_provider_status: AvailabilityStatus | None = Field(
        default=None,
        description="If set, candidates whose provider status differs are rejected.",
    )


class NavigationRequest(BaseModel):
    """A structured request to navigate the ecosystem for a capability."""

    model_config = ConfigDict(frozen=True)

    capability: str = Field(
        ...,
        description="Required namespaced capability ID (e.g. 'file.read').",
    )
    constraints: NavigationConstraints = Field(
        default_factory=NavigationConstraints,
        description="Optional constraints to narrow selection.",
    )

    @field_validator("capability")
    @classmethod
    def validate_capability(cls, v: str) -> str:
        """Capability must be a non-empty namespaced identifier."""
        if not v or "." not in v:
            raise ValueError(
                f"Navigation capability must be namespaced (e.g. 'file.read'), got: '{v}'"
            )
        return v


class NavigationCandidate(BaseModel):
    """A potential execution target extracted from the ecosystem snapshot.

    Distinct from DiscoveredNode/DiscoveredProvider: a candidate represents
    a specific (node, provider, capability) triple that *could* satisfy
    the current navigation request.
    """

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(description="Node hosting this candidate.")
    node_name: str = Field(description="Human-readable node name.")
    provider_id: str = Field(description="Provider exposing the capability.")
    provider_name: str = Field(description="Human-readable provider name.")
    capability_id: str = Field(description="The matched capability ID.")
    is_local: bool = Field(description="True if the hosting node is local.")
    node_state: EcosystemNodeState = Field(description="Current node lifecycle state.")
    provider_status: AvailabilityStatus = Field(description="Current provider status.")
    capability_availability: AvailabilityStatus = Field(
        description="Current capability availability."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Merged metadata from node and provider for selection context.",
    )


class RejectedCandidate(BaseModel):
    """A candidate that was evaluated and rejected, with an explainable reason."""

    model_config = ConfigDict(frozen=True)

    candidate: NavigationCandidate
    reason: str = Field(description="Human-readable explanation of why this candidate was rejected.")


class NavigationResult(BaseModel):
    """The deterministic output of the Hybrid Navigator.

    Contains the selected target (if any), the selection reason,
    alternative valid candidates, and all rejected candidates with reasons.
    """

    model_config = ConfigDict(frozen=True)

    capability: str = Field(description="The capability that was navigated for.")
    selected: NavigationCandidate | None = Field(
        default=None,
        description="The chosen execution target, or None if no valid candidate exists.",
    )
    reason: str = Field(
        default="",
        description="Human-readable explanation of the selection decision.",
    )
    alternatives: list[NavigationCandidate] = Field(
        default_factory=list,
        description="Other valid candidates that were not selected.",
    )
    rejected: list[RejectedCandidate] = Field(
        default_factory=list,
        description="Candidates that were evaluated and rejected, with reasons.",
    )

    @property
    def has_selection(self) -> bool:
        """True if a target was successfully selected."""
        return self.selected is not None
