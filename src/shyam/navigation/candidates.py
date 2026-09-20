"""Candidate Discovery - S9.

Translates ecosystem discovery records (EcosystemSnapshot, DiscoveredNode,
DiscoveredProvider) into normalized NavigationCandidate evaluation models.
"""

from __future__ import annotations

import logging

from shyam.discovery.ecosystem_models import EcosystemSnapshot
from shyam.navigation.models import NavigationCandidate

logger = logging.getLogger("shyam.navigation.candidates")


class CandidateDiscoverer:
    """Extracts potential NavigationCandidates from EcosystemSnapshots."""

    @staticmethod
    def discover_candidates(
        snapshot: EcosystemSnapshot,
        capability_id: str,
    ) -> list[NavigationCandidate]:
        """Scan the ecosystem snapshot for providers offering the requested capability.

        Returns:
            List of matching NavigationCandidate triples (Node, Provider, Capability).
        """
        candidates: list[NavigationCandidate] = []

        for node_id, node in snapshot.nodes.items():
            for provider_id, provider in node.providers.items():
                for cap in provider.capabilities:
                    if cap.capability_id == capability_id:
                        # Safely combine metadata to provide rich context for policies
                        merged_metadata = {
                            "node": dict(node.metadata),
                            "provider": dict(provider.metadata),
                        }

                        candidate = NavigationCandidate(
                            node_id=node.node_id,
                            node_name=node.node_name,
                            provider_id=provider.provider_id,
                            provider_name=provider.name,
                            capability_id=cap.capability_id,
                            is_local=node.is_local,
                            node_state=node.state,
                            provider_status=provider.status,
                            capability_availability=cap.availability,
                            metadata=merged_metadata,
                        )
                        candidates.append(candidate)

        logger.debug(
            "Discovered %d candidates for capability '%s'",
            len(candidates),
            capability_id,
        )
        return candidates
