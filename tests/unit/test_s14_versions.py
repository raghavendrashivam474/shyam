"""Unit tests for S14 version vector comparison and merge."""

from shyam.sync.models import NodeVersionMap
from shyam.sync.versions import (
    VersionComparison,
    compare_versions,
    merge_version_maps,
)


def test_compare_empty_maps():
    v1 = NodeVersionMap()
    v2 = NodeVersionMap()
    assert compare_versions(v1, v2) == VersionComparison.EQUAL


def test_compare_identical_maps():
    v1 = NodeVersionMap(versions={"A": 3, "B": 2})
    v2 = NodeVersionMap(versions={"A": 3, "B": 2})
    assert compare_versions(v1, v2) == VersionComparison.EQUAL


def test_compare_local_behind():
    v_local = NodeVersionMap(versions={"A": 3, "B": 2})
    v_remote = NodeVersionMap(versions={"A": 4, "B": 2})
    assert compare_versions(v_local, v_remote) == VersionComparison.BEHIND


def test_compare_local_ahead():
    v_local = NodeVersionMap(versions={"A": 5, "B": 2})
    v_remote = NodeVersionMap(versions={"A": 3, "B": 2})
    assert compare_versions(v_local, v_remote) == VersionComparison.AHEAD


def test_compare_concurrent():
    # Local has newer A, Remote has newer B
    v_local = NodeVersionMap(versions={"A": 5, "B": 1})
    v_remote = NodeVersionMap(versions={"A": 2, "B": 4})
    assert compare_versions(v_local, v_remote) == VersionComparison.CONCURRENT


def test_compare_disjoint_nodes():
    v_local = NodeVersionMap(versions={"A": 1})
    v_remote = NodeVersionMap(versions={"B": 1})
    assert compare_versions(v_local, v_remote) == VersionComparison.CONCURRENT


def test_merge_version_maps():
    v1 = NodeVersionMap(versions={"A": 5, "B": 2, "C": 1})
    v2 = NodeVersionMap(versions={"A": 3, "B": 6, "D": 4})
    merged = merge_version_maps(v1, v2)

    assert merged.versions == {
        "A": 5,
        "B": 6,
        "C": 1,
        "D": 4,
    }
