"""Navigation Policy - S9.

Implements deterministic candidate filtering and ranking policies.
Decisions are fully explainable and repeatable across runs.
"""

from __future__ import annotations

import logging

from shyam.capabilities.model import AvailabilityStatus
from shyam.discovery.ecosystem_models import EcosystemNodeState
from shyam.navigation.models import (
    NavigationCandidate,
    NavigationConstraints,
    NavigationResult,
    RejectedCandidate,
)

logger = logging.getLogger("shyam.navigation.policy")


class NavigationPolicyEvaluator:
    """Evaluates candidates against constraints and applies selection ranking."""

    @staticmethod
    def evaluate(
        capability: str,
        candidates: list[NavigationCandidate],
        constraints: NavigationConstraints,
    ) -> NavigationResult:
        """Filter and rank candidates to select the single best target.

        The evaluation pipeline is as follows:
        1. Eligibility Filtering (Remove candidates that violate explicit constraints or state requirements)
        2. Candidate Ranking (Sort eligible candidates deterministically by locality and preference weights)
        3. Stable Tie-breaking (Apply guaranteed deterministic ordering)

        Returns:
            A structured NavigationResult detailing the winner and explainable reasons for all candidates.
        """
        eligible: list[NavigationCandidate] = []
        rejected: list[RejectedCandidate] = []

        # --- Stage 1: Eligibility Filtering ---
        for cand in candidates:
            # Check node state
            if cand.node_state == EcosystemNodeState.UNAVAILABLE:
                rejected.append(RejectedCandidate(candidate=cand, reason="Node is unavailable"))
                continue
            if cand.node_state == EcosystemNodeState.STALE:
                rejected.append(RejectedCandidate(candidate=cand, reason="Node state is stale"))
                continue

            # Check provider availability
            if cand.provider_status == AvailabilityStatus.UNAVAILABLE:
                rejected.append(RejectedCandidate(candidate=cand, reason="Provider status is unavailable"))
                continue

            # Check capability availability
            if cand.capability_availability == AvailabilityStatus.UNAVAILABLE:
                rejected.append(
                    RejectedCandidate(candidate=cand, reason="Capability availability is unavailable")
                )
                continue

            # Check local_only constraint
            if constraints.local_only and not cand.is_local:
                rejected.append(
                    RejectedCandidate(candidate=cand, reason="Violates constraint: local_only=True")
                )
                continue

            # Check remote_allowed constraint
            if not constraints.remote_allowed and not cand.is_local:
                rejected.append(
                    RejectedCandidate(candidate=cand, reason="Violates constraint: remote_allowed=False")
                )
                continue

            # Check explicit required node state
            if constraints.required_node_state and cand.node_state != constraints.required_node_state:
                rejected.append(
                    RejectedCandidate(
                        candidate=cand,
                        reason=f"Violates constraint: required_node_state={constraints.required_node_state}",
                    )
                )
                continue

            # Check explicit required provider status
            if (
                constraints.required_provider_status
                and cand.provider_status != constraints.required_provider_status
            ):
                rejected.append(
                    RejectedCandidate(
                        candidate=cand,
                        reason=f"Violates constraint: required_provider_status={constraints.required_provider_status}",
                    )
                )
                continue

            # If all checks pass, candidate is eligible
            eligible.append(cand)

        if not eligible:
            return NavigationResult(
                capability=capability,
                selected=None,
                reason="No eligible candidates found matching requirements.",
                alternatives=[],
                rejected=rejected,
            )

        # --- Stage 2: Candidate Ranking & Selection ---
        # Define a sorting/ranking key that maximizes deterministic preference matches.
        # Python's sort is stable. We will construct a key where LOWER score is better.
        def ranking_key(c: NavigationCandidate) -> tuple[int, int, int, str, str]:
            # Preference 1: Explicitly preferred node matches
            node_pref = 0 if (constraints.preferred_node == c.node_id) else 1

            # Preference 2: Explicitly preferred provider matches
            prov_pref = 0 if (constraints.preferred_provider == c.provider_id) else 1

            # Preference 3: Locality (Local targets are preferred over remote ones by default)
            locality_pref = 0 if c.is_local else 1

            # Tie-breakers: Stable alphabetical order of node_id and provider_id to make it 100% deterministic
            return (node_pref, prov_pref, locality_pref, c.node_id, c.provider_id)

        # Sort the eligible candidates according to the ranking key
        ranked = sorted(eligible, key=ranking_key)

        selected = ranked[0]
        alternatives = ranked[1:]

        # Create an explainable decision reason
        reason_parts = [
            f"Selected candidate on node '{selected.node_id}' via provider '{selected.provider_id}'."
        ]
        if constraints.preferred_node == selected.node_id:
            reason_parts.append("Matched preferred node constraint.")
        if constraints.preferred_provider == selected.provider_id:
            reason_parts.append("Matched preferred provider constraint.")
        if selected.is_local:
            reason_parts.append("Preferred local execution.")
        else:
            reason_parts.append("Resolved to remote execution.")

        return NavigationResult(
            capability=capability,
            selected=selected,
            reason=" ".join(reason_parts),
            alternatives=alternatives,
            rejected=rejected,
        )
