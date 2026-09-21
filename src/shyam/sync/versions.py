"""Version vector comparison and merge operations — S14.

Provides deterministic causality reasoning across independent Shyam nodes.
Does not assume a central global clock or monotonic timestamp ordering.
"""

from __future__ import annotations

from enum import StrEnum

from shyam.sync.models import NodeVersionMap


class VersionComparison(StrEnum):
    """Result of comparing two NodeVersionMaps (Local vs Remote)."""

    EQUAL = "equal"
    AHEAD = "ahead"          # Local has all remote facts plus more
    BEHIND = "behind"        # Remote has all local facts plus more (Local should update)
    CONCURRENT = "concurrent"  # Both have independent unseen mutations (Merge required)


def compare_versions(local: NodeVersionMap, remote: NodeVersionMap) -> VersionComparison:
    """Compare local vs remote version vectors.

    Semantics:
        - EQUAL: All node versions match identically.
        - BEHIND: Remote has >= version for every node, and strictly > on at least one.
        - AHEAD: Local has >= version for every node, and strictly > on at least one.
        - CONCURRENT: Neither dominates (e.g. Local is ahead on Node A, Remote is ahead on Node B).
    """
    all_keys = set(local.versions.keys()) | set(remote.versions.keys())

    if not all_keys:
        return VersionComparison.EQUAL

    local_has_greater = False
    remote_has_greater = False

    for key in all_keys:
        v_local = local.get_version(key)
        v_remote = remote.get_version(key)

        if v_local > v_remote:
            local_has_greater = True
        elif v_remote > v_local:
            remote_has_greater = True

    if local_has_greater and remote_has_greater:
        return VersionComparison.CONCURRENT
    if remote_has_greater:
        return VersionComparison.BEHIND
    if local_has_greater:
        return VersionComparison.AHEAD
    return VersionComparison.EQUAL


def merge_version_maps(v1: NodeVersionMap, v2: NodeVersionMap) -> NodeVersionMap:
    """Compute the component-wise supremum (maximum) of two version vectors."""
    all_keys = set(v1.versions.keys()) | set(v2.versions.keys())
    merged = {
        node_id: max(v1.get_version(node_id), v2.get_version(node_id))
        for node_id in all_keys
    }
    return NodeVersionMap(versions=merged)
