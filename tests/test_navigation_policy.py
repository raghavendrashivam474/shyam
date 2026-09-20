"""Tests for S9.3 and S9.4 Eligibility Filtering and Selection Policies."""

from __future__ import annotations

from shyam.capabilities.model import AvailabilityStatus
from shyam.discovery.ecosystem_models import EcosystemNodeState
from shyam.navigation.models import NavigationCandidate, NavigationConstraints
from shyam.navigation.policy import NavigationPolicyEvaluator


def _make_candidate(
    node_id: str = "node-a",
    provider_id: str = "local.fs",
    is_local: bool = True,
    node_state: EcosystemNodeState = EcosystemNodeState.AVAILABLE,
    provider_status: AvailabilityStatus = AvailabilityStatus.AVAILABLE,
    capability_availability: AvailabilityStatus = AvailabilityStatus.AVAILABLE,
) -> NavigationCandidate:
    return NavigationCandidate(
        node_id=node_id,
        node_name=f"Node {node_id}",
        provider_id=provider_id,
        provider_name=f"Provider {provider_id}",
        capability_id="file.read",
        is_local=is_local,
        node_state=node_state,
        provider_status=provider_status,
        capability_availability=capability_availability,
    )


# ── S9.3 Eligibility Tests ──────────────────────────────────────────


class TestEligibilityFiltering:
    def test_eligible_candidate(self) -> None:
        cand = _make_candidate()
        result = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[cand],
            constraints=NavigationConstraints(),
        )
        assert result.has_selection is True
        assert result.selected == cand
        assert len(result.rejected) == 0

    def test_reject_unavailable_node(self) -> None:
        cand = _make_candidate(node_state=EcosystemNodeState.UNAVAILABLE)
        result = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[cand],
            constraints=NavigationConstraints(),
        )
        assert result.has_selection is False
        assert len(result.rejected) == 1
        assert "Node is unavailable" in result.rejected[0].reason

    def test_reject_stale_node(self) -> None:
        cand = _make_candidate(node_state=EcosystemNodeState.STALE)
        result = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[cand],
            constraints=NavigationConstraints(),
        )
        assert result.has_selection is False
        assert "Node state is stale" in result.rejected[0].reason

    def test_reject_unavailable_provider(self) -> None:
        cand = _make_candidate(provider_status=AvailabilityStatus.UNAVAILABLE)
        result = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[cand],
            constraints=NavigationConstraints(),
        )
        assert result.has_selection is False
        assert "Provider status is unavailable" in result.rejected[0].reason

    def test_rejects_local_only_constraint(self) -> None:
        # Candidate is remote, request demands local
        cand = _make_candidate(is_local=False, node_id="remote-node")
        result = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[cand],
            constraints=NavigationConstraints(local_only=True),
        )
        assert result.has_selection is False
        assert "local_only=True" in result.rejected[0].reason

    def test_rejects_remote_not_allowed_constraint(self) -> None:
        cand = _make_candidate(is_local=False, node_id="remote-node")
        result = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[cand],
            constraints=NavigationConstraints(remote_allowed=False),
        )
        assert result.has_selection is False
        assert "remote_allowed=False" in result.rejected[0].reason


# ── S9.4 Ranking & Selection Policy Tests ──────────────────────────


class TestSelectionPolicy:
    def test_prefer_local_by_default(self) -> None:
        local_cand = _make_candidate(node_id="local-node", is_local=True)
        remote_cand = _make_candidate(node_id="remote-node", is_local=False)

        # Pass remote first in the list to make sure we don't just pick index 0
        result = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[remote_cand, local_cand],
            constraints=NavigationConstraints(),
        )
        assert result.has_selection is True
        assert result.selected.node_id == "local-node"
        assert len(result.alternatives) == 1
        assert result.alternatives[0].node_id == "remote-node"

    def test_preferred_node_override(self) -> None:
        # We prefer "remote-node", even though there is a local candidate
        local_cand = _make_candidate(node_id="local-node", is_local=True)
        remote_cand = _make_candidate(node_id="remote-node", is_local=False)

        result = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[local_cand, remote_cand],
            constraints=NavigationConstraints(preferred_node="remote-node"),
        )
        assert result.has_selection is True
        assert result.selected.node_id == "remote-node"
        assert "Matched preferred node" in result.reason

    def test_preferred_provider_override(self) -> None:
        fs_cand = _make_candidate(provider_id="local.fs")
        zarya_cand = _make_candidate(provider_id="zarya.agent")

        result = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[fs_cand, zarya_cand],
            constraints=NavigationConstraints(preferred_provider="zarya.agent"),
        )
        assert result.has_selection is True
        assert result.selected.provider_id == "zarya.agent"
        assert "Matched preferred provider" in result.reason

    def test_deterministic_tie_breaker(self) -> None:
        # Both are remote, no node preferences
        cand_b = _make_candidate(node_id="node-b", is_local=False)
        cand_c = _make_candidate(node_id="node-c", is_local=False)

        # Regardless of input order, should stably sort alphabetically by node_id
        result_1 = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[cand_c, cand_b],
            constraints=NavigationConstraints(),
        )
        result_2 = NavigationPolicyEvaluator.evaluate(
            capability="file.read",
            candidates=[cand_b, cand_c],
            constraints=NavigationConstraints(),
        )

        assert result_1.selected.node_id == "node-b"
        assert result_2.selected.node_id == "node-b"
