"""Tests for S9.5 Hybrid Navigator and Decision Explainability."""

from __future__ import annotations

from datetime import UTC, datetime

from shyam.capabilities.model import AvailabilityStatus
from shyam.discovery.ecosystem_models import (
    DiscoveredCapability,
    DiscoveredNode,
    DiscoveredProvider,
    EcosystemNodeState,
    EcosystemSnapshot,
)
from shyam.navigation.models import NavigationConstraints, NavigationRequest
from shyam.navigation.navigator import HybridNavigator


def _make_snapshot(
    nodes_data: list[dict[str, object]],
    local_node_id: str = "local-node",
) -> EcosystemSnapshot:
    """Helper to assemble a mocked EcosystemSnapshot."""
    nodes: dict[str, DiscoveredNode] = {}
    now = datetime.now(UTC)

    for data in nodes_data:
        node_id = str(data["node_id"])
        is_local = bool(data.get("is_local", False))
        state = data.get("state", EcosystemNodeState.AVAILABLE)
        assert isinstance(state, EcosystemNodeState)

        providers: dict[str, DiscoveredProvider] = {}
        for prov_data in data.get("providers", []):  # type: ignore[attr-defined]
            prov_id = str(prov_data["provider_id"])
            prov_status = prov_data.get("status", AvailabilityStatus.AVAILABLE)
            assert isinstance(prov_status, AvailabilityStatus)

            caps: list[DiscoveredCapability] = []
            for cap_id in prov_data.get("capabilities", []):
                caps.append(
                    DiscoveredCapability(
                        capability_id=str(cap_id),
                        name=f"Capability {cap_id}",
                        availability=AvailabilityStatus.AVAILABLE,
                    )
                )

            providers[prov_id] = DiscoveredProvider(
                provider_id=prov_id,
                name=f"Provider {prov_id}",
                capabilities=tuple(caps),
                status=prov_status,
                last_seen=now,
            )

        nodes[node_id] = DiscoveredNode(
            node_id=node_id,
            node_name=f"Node {node_id}",
            is_local=is_local,
            state=state,
            providers=providers,
            first_seen=now,
            last_seen=now,
        )

    return EcosystemSnapshot(
        local_node_id=local_node_id,
        nodes=nodes,
    )


def test_navigator_integration_success() -> None:
    # Ecosystem has a local node with file.read and a remote node with file.read
    snapshot = _make_snapshot(
        [
            {
                "node_id": "local-node",
                "is_local": True,
                "providers": [
                    {
                        "provider_id": "local.fs",
                        "capabilities": ["file.read"],
                    }
                ],
            },
            {
                "node_id": "remote-node",
                "is_local": False,
                "providers": [
                    {
                        "provider_id": "remote.fs",
                        "capabilities": ["file.read"],
                    }
                ],
            },
        ]
    )

    navigator = HybridNavigator()
    req = NavigationRequest(capability="file.read")

    result = navigator.navigate(req, snapshot)

    # Should select local candidate by default
    assert result.has_selection is True
    assert result.selected is not None
    assert result.selected.node_id == "local-node"
    assert result.selected.provider_id == "local.fs"

    # Should document alternative
    assert len(result.alternatives) == 1
    assert result.alternatives[0].node_id == "remote-node"
    assert len(result.rejected) == 0


def test_navigator_integration_explain_rejections() -> None:
    # Ecosystem has:
    # 1. Unreachable/stale remote node with file.read
    # 2. Unavailable local provider with file.read
    # 3. Available remote node with file.read (violating local-only constraint)
    snapshot = _make_snapshot(
        [
            {
                "node_id": "stale-node",
                "is_local": False,
                "state": EcosystemNodeState.STALE,
                "providers": [
                    {
                        "provider_id": "stale.prov",
                        "capabilities": ["file.read"],
                    }
                ],
            },
            {
                "node_id": "local-node",
                "is_local": True,
                "providers": [
                    {
                        "provider_id": "bad.prov",
                        "status": AvailabilityStatus.UNAVAILABLE,
                        "capabilities": ["file.read"],
                    }
                ],
            },
            {
                "node_id": "remote-node",
                "is_local": False,
                "providers": [
                    {
                        "provider_id": "remote.fs",
                        "capabilities": ["file.read"],
                    }
                ],
            },
        ]
    )

    navigator = HybridNavigator()
    req = NavigationRequest(
        capability="file.read",
        constraints=NavigationConstraints(local_only=True),
    )

    result = navigator.navigate(req, snapshot)

    # No candidate should win
    assert result.has_selection is False
    assert result.selected is None

    # Verify explainability: each candidate should be rejected with a clear reason
    assert len(result.rejected) == 3

    rejection_reasons = {r.candidate.node_id: r.reason for r in result.rejected}
    assert "stale-node" in rejection_reasons
    assert "Node state is stale" in rejection_reasons["stale-node"]

    assert "local-node" in rejection_reasons
    assert "Provider status is unavailable" in rejection_reasons["local-node"]

    assert "remote-node" in rejection_reasons
    assert "local_only=True" in rejection_reasons["remote-node"]
