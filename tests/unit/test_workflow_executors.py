"""Unit tests for Workflow Capability Executors and Registry."""

from unittest.mock import MagicMock
import pytest

from shyam.capabilities.model import AvailabilityStatus
from shyam.discovery.ecosystem_models import EcosystemNodeState
from shyam.navigation.models import NavigationCandidate
from shyam.providers.flux.models import FluxConnectResponse, FluxPeerInfo
from shyam.providers.flux.provider import FluxProvider
from shyam.providers.zarya.models import VerificationOutcome, WorkExecuteResponse
from shyam.providers.zarya.provider import ZaryaProvider
from shyam.workflow.errors import ExecutorNotFoundError, StepExecutionError
from shyam.workflow.executor import CapabilityExecutor, ExecutorRegistry
from shyam.workflow.executors.flux import FluxExecutor
from shyam.workflow.executors.local_fs import LocalFilesystemExecutor
from shyam.workflow.executors.zarya import ZaryaExecutor


def _create_candidate(provider_id: str, capability_id: str) -> NavigationCandidate:
    return NavigationCandidate(
        node_id="test-node",
        node_name="Test Node",
        provider_id=provider_id,
        provider_name="Test Provider",
        capability_id=capability_id,
        is_local=True,
        node_state=EcosystemNodeState.AVAILABLE,
        provider_status=AvailabilityStatus.AVAILABLE,
        capability_availability=AvailabilityStatus.AVAILABLE,
    )


def test_executor_registry_operations():
    """Verify registration, lookup, contains, and unregister in ExecutorRegistry."""
    registry = ExecutorRegistry()
    fs_exec = LocalFilesystemExecutor()

    assert not registry.contains("local.filesystem")
    with pytest.raises(ExecutorNotFoundError):
        registry.get("local.filesystem")

    registry.register("local.filesystem", fs_exec)
    assert registry.contains("local.filesystem")
    assert "local.filesystem" in registry
    assert registry.get("local.filesystem") is fs_exec

    removed = registry.unregister("local.filesystem")
    assert removed is fs_exec
    assert "local.filesystem" not in registry


@pytest.mark.asyncio
async def test_local_filesystem_executor_file_roundtrip(tmp_path):
    """Test LocalFilesystemExecutor writing, reading, and listing files."""
    executor = LocalFilesystemExecutor()
    test_file = tmp_path / "hello.txt"

    # 1. file.write
    write_target = _create_candidate("local.filesystem", "file.write")
    write_res = await executor.execute(
        write_target,
        {"path": str(test_file), "content": "Hello Shyam S10!"},
    )
    assert write_res["written_bytes"] > 0
    assert test_file.exists()

    # 2. file.read
    read_target = _create_candidate("local.filesystem", "file.read")
    read_res = await executor.execute(
        read_target,
        {"path": str(test_file)},
    )
    assert read_res["content"] == "Hello Shyam S10!"
    assert read_res["size_bytes"] == len("Hello Shyam S10!".encode("utf-8"))

    # 3. file.list
    list_target = _create_candidate("local.filesystem", "file.list")
    list_res = await executor.execute(
        list_target,
        {"path": str(tmp_path)},
    )
    assert "hello.txt" in list_res["entries"]
    assert list_res["count"] == 1


@pytest.mark.asyncio
async def test_local_filesystem_executor_file_not_found():
    """file.read on non-existent file raises StepExecutionError."""
    executor = LocalFilesystemExecutor()
    target = _create_candidate("local.filesystem", "file.read")

    with pytest.raises(StepExecutionError) as exc_info:
        await executor.execute(target, {"path": "/non/existent/path/never_here.txt"})
    assert "File not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_zarya_executor_delegation():
    """ZaryaExecutor correctly adapts calls to ZaryaProvider.execute()."""
    mock_provider = MagicMock(spec=ZaryaProvider)
    mock_provider.execute.return_value = WorkExecuteResponse(
        tool="zarya.file.read",
        outcome=VerificationOutcome.VERIFIED_SUCCESS,
        verified=True,
        result={"content": "Zarya content"},
    )

    executor = ZaryaExecutor(provider=mock_provider)
    target = _create_candidate("zarya.sovereign", "zarya.file.read")

    res = await executor.execute(target, {"path": "/data/report.json"})

    mock_provider.execute.assert_called_once_with(
        "zarya.file.read",
        {"path": "/data/report.json"},
    )
    assert res["outcome"] == "VERIFIED_SUCCESS"
    assert res["result"]["content"] == "Zarya content"


@pytest.mark.asyncio
async def test_flux_executor_delegation():
    """FluxExecutor correctly adapts calls to FluxProvider operations."""
    mock_provider = MagicMock(spec=FluxProvider)
    mock_provider.discover_peers.return_value = [
        FluxPeerInfo(
            peer_id="peer-99",
            address="192.168.1.100:9100",
            connectivity="reachable",
        )
    ]
    mock_provider.connect_peer.return_value = FluxConnectResponse(
        peer_id="peer-99",
        success=True,
        connected=True,
        connected_address="192.168.1.100:9100",
    )

    executor = FluxExecutor(provider=mock_provider)

    # 1. flux.peer.discover
    target_discover = _create_candidate("flux.connectivity", "flux.peer.discover")
    res_discover = await executor.execute(target_discover, {})
    assert len(res_discover) == 1
    assert res_discover[0]["peer_id"] == "peer-99"

    # 2. flux.peer.connect
    target_connect = _create_candidate("flux.connectivity", "flux.peer.connect")
    res_connect = await executor.execute(target_connect, {"peer_id": "peer-99"})
    assert res_connect["success"] is True
    assert res_connect["connected_address"] == "192.168.1.100:9100"
