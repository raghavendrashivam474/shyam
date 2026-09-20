"""Hybrid Navigator - S9.

High-level coordinator that runs the candidate discovery and policy evaluation
pipelines over an EcosystemSnapshot to resolve a NavigationRequest.
"""

from __future__ import annotations

import logging

from shyam.discovery.ecosystem_models import EcosystemSnapshot
from shyam.navigation.candidates import CandidateDiscoverer
from shyam.navigation.models import NavigationRequest, NavigationResult
from shyam.navigation.policy import NavigationPolicyEvaluator

logger = logging.getLogger("shyam.navigation.navigator")


class HybridNavigator:
    """Orchestrates candidate discovery and deterministic evaluation."""

    def __init__(self) -> None:
        self._discoverer = CandidateDiscoverer()
        self._evaluator = NavigationPolicyEvaluator()

    def navigate(
        self,
        request: NavigationRequest,
        snapshot: EcosystemSnapshot,
    ) -> NavigationResult:
        """Resolve a NavigationRequest against an EcosystemSnapshot.

        1. Discover all candidates hosting the requested capability.
        2. Evaluate/Filter/Rank them deterministically using policy.
        3. Explain and return the result.
        """
        logger.info(
            "Starting hybrid navigation for capability '%s' (nodes in snapshot: %d)",
            request.capability,
            snapshot.total_nodes,
        )

        # Step 1: Discover candidates
        candidates = self._discoverer.discover_candidates(
            snapshot=snapshot,
            capability_id=request.capability,
        )

        # Step 2 & 3: Evaluate eligibility and select best candidate
        result = self._evaluator.evaluate(
            capability=request.capability,
            candidates=candidates,
            constraints=request.constraints,
        )

        if result.has_selection:
            assert result.selected is not None  # Type narrowing
            logger.info(
                "Navigation successful: Selected target Node '%s' via Provider '%s' [Reason: %s]",
                result.selected.node_id,
                result.selected.provider_id,
                result.reason,
            )
        else:
            logger.warning(
                "Navigation failed for capability '%s': %s",
                request.capability,
                result.reason,
            )

        return result
