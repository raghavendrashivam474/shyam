"""Tests for S9.1 Navigation Domain Models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shyam.capabilities.model import AvailabilityStatus
from shyam.discovery.ecosystem_models import EcosystemNodeState
from shyam.navigation.models import (
    NavigationCandidate,
    NavigationConstraints,
    NavigationRequest,
    NavigationResult,
    RejectedCandidate,
)


# ── NavigationConstraints ──────────────────────────────────────────


class TestNavigationConstraints:
    def test_defaults(self) -> None:
        c = NavigationConstraints()
        assert c.preferred_node is None
        assert c.preferred_provider is None
        assert c.local_only is False
        assert c.remote_allowed is True
        assert c.required_node_state is None
        assert c.required_provider_status is None

    def test_frozen(self) -> None:
        c = NavigationConstraints(local_only=True)
        with pytest.raises(ValidationError):
            c.local_only = False  # type: ignore[misc]

    def test_with_preferences(self) -> None:
        c = NavigationConstraints(
            preferred_node="node-a",
            preferred_provider="local.fs",
        )
        assert c.preferred_node == "node-a"
        assert c.preferred_provider == "local.fs"


# ── NavigationRequest ──────────────────────────────────────────────


class TestNavigationRequest:
    def test_minimal(self) -> None:
        req = NavigationRequest(capability="file.read")
        assert req.capability == "file.read"
        assert req.constraints.local_only is False

    def test_with_constraints(self) -> None:
        req = NavigationRequest(
            capability="file.read",
            constraints=NavigationConstraints(local_only=True),
        )
        assert req.constraints.local_only is True

    def test_rejects_unnamespaced_capability(self) -> None:
        with pytest.raises(ValidationError, match="namespaced"):
            NavigationRequest(capability="read")

    def test_rejects_empty_capability(self) -> None:
        with pytest.raises(ValidationError):
            NavigationRequest(capability="")

    def test_frozen(self) -> None:
        req = NavigationRequest(capability="file.read")
        with pytest.raises(ValidationError):
            req.capability = "file.write"  # type: ignore[misc]


# ── NavigationCandidate ────────────────────────────────────────────


class TestNavigationCandidate:
    def _make(self, **overrides: object) -> NavigationCandidate:
        defaults = dict(
            node_id="node-a",
            node_name="Node A",
            provider_id="local.fs",
            provider_name="Local Filesystem",
            capability_id="file.read",
            is_local=True,
            node_state=EcosystemNodeState.AVAILABLE,
            provider_status=AvailabilityStatus.AVAILABLE,
            capability_availability=AvailabilityStatus.AVAILABLE,
        )
        defaults.update(overrides)
        return NavigationCandidate(**defaults)  # type: ignore[arg-type]

    def test_creation(self) -> None:
        c = self._make()
        assert c.node_id == "node-a"
        assert c.is_local is True
        assert c.node_state == EcosystemNodeState.AVAILABLE

    def test_remote_candidate(self) -> None:
        c = self._make(is_local=False, node_id="node-b")
        assert c.is_local is False

    def test_frozen(self) -> None:
        c = self._make()
        with pytest.raises(ValidationError):
            c.node_id = "node-z"  # type: ignore[misc]


# ── RejectedCandidate ──────────────────────────────────────────────


class TestRejectedCandidate:
    def test_creation(self) -> None:
        candidate = NavigationCandidate(
            node_id="node-x",
            node_name="Node X",
            provider_id="remote.fs",
            provider_name="Remote FS",
            capability_id="file.read",
            is_local=False,
            node_state=EcosystemNodeState.UNAVAILABLE,
            provider_status=AvailabilityStatus.UNAVAILABLE,
            capability_availability=AvailabilityStatus.UNAVAILABLE,
        )
        rejected = RejectedCandidate(
            candidate=candidate,
            reason="node unavailable",
        )
        assert rejected.reason == "node unavailable"
        assert rejected.candidate.node_id == "node-x"


# ── NavigationResult ───────────────────────────────────────────────


class TestNavigationResult:
    def _make_candidate(self, node_id: str = "node-a") -> NavigationCandidate:
        return NavigationCandidate(
            node_id=node_id,
            node_name=f"Node {node_id}",
            provider_id="local.fs",
            provider_name="Local FS",
            capability_id="file.read",
            is_local=True,
            node_state=EcosystemNodeState.AVAILABLE,
            provider_status=AvailabilityStatus.AVAILABLE,
            capability_availability=AvailabilityStatus.AVAILABLE,
        )

    def test_no_selection(self) -> None:
        result = NavigationResult(capability="file.read")
        assert result.has_selection is False
        assert result.selected is None

    def test_with_selection(self) -> None:
        c = self._make_candidate()
        result = NavigationResult(
            capability="file.read",
            selected=c,
            reason="eligible local provider",
        )
        assert result.has_selection is True
        assert result.selected.node_id == "node-a"
        assert result.reason == "eligible local provider"

    def test_with_alternatives_and_rejected(self) -> None:
        selected = self._make_candidate("node-a")
        alt = self._make_candidate("node-b")
        rej_cand = self._make_candidate("node-c")
        rejected = RejectedCandidate(candidate=rej_cand, reason="unavailable")

        result = NavigationResult(
            capability="file.read",
            selected=selected,
            reason="preferred local",
            alternatives=[alt],
            rejected=[rejected],
        )
        assert result.has_selection is True
        assert len(result.alternatives) == 1
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == "unavailable"

    def test_frozen(self) -> None:
        result = NavigationResult(capability="file.read")
        with pytest.raises(ValidationError):
            result.capability = "file.write"  # type: ignore[misc]
