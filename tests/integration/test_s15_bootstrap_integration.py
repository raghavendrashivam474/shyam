"""End-to-end integration tests for S15 Device Bootstrap & Recovery."""

import pytest
from pathlib import Path

from shyam.bootstrap.models import BootstrapState, RecoveryRequest, RecoveryScenario
from shyam.bootstrap.transport import BootstrapTransport
from shyam.bootstrap.models import BootstrapRequest, BootstrapResponse
from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.sync.models import SyncOutcome
from shyam.trust.models import TrustStatus


class RuntimeBootstrapTransport(BootstrapTransport):
    """Bridge transport connecting two ShyamRuntime instances directly in-process."""

    def __init__(self, authority_runtime: ShyamRuntime) -> None:
        self.authority = authority_runtime

    async def send_request(
        self,
        endpoint_id: str,
        request: BootstrapRequest,
    ) -> BootstrapResponse:
        return await self.authority.bootstrap.handle_incoming_request(request)


@pytest.mark.asyncio
async def test_two_runtime_bootstrap_and_state_exchange(tmp_path: Path) -> None:
    """Test full bootstrap lifecycle between an authority runtime and a new client runtime."""
    auth_dir = tmp_path / "authority_runtime"
    client_dir = tmp_path / "client_runtime"

    auth_settings = ShyamSettings(
        data_directory=auth_dir,
        runtime_name="authority-desktop",
        discovery_enabled=False,
        zarya_enabled=False,
        flux_enabled=False,
    )
    client_settings = ShyamSettings(
        data_directory=client_dir,
        runtime_name="new-android-phone",
        discovery_enabled=False,
        zarya_enabled=False,
        flux_enabled=False,
    )

    async with ShyamRuntime(auth_settings) as auth_runtime:
        async with ShyamRuntime(client_settings) as client_runtime:
            transport = RuntimeBootstrapTransport(auth_runtime)

            # Pre-conditions:
            auth_node_id = str(auth_runtime.identity_manager.identity.node_id)
            client_node_id = str(client_runtime.identity_manager.identity.node_id)

            assert not await auth_runtime.trust.is_trusted(client_node_id)
            assert not await client_runtime.trust.is_trusted(auth_node_id)

            # Execute Client Bootstrap
            session = await client_runtime.bootstrap.execute_client_bootstrap(
                authority_endpoint="inproc://authority",
                transport=transport,
            )

            # Post-conditions:
            assert session.state == BootstrapState.READY
            assert session.is_successful

            # Verify mutual trust was established in S13
            assert await auth_runtime.trust.is_trusted(client_node_id)
            assert await client_runtime.trust.is_trusted(auth_node_id)

            # Update facts on authority and exchange sync envelope via S14
            await auth_runtime.sync.update_local_facts(
                capabilities={auth_node_id: ["system.compute.v1"]},
                availability={auth_node_id: "ONLINE"},
            )
            env = await auth_runtime.sync.create_sync_envelope()
            sync_res = await client_runtime.sync.process_incoming_envelope(env)

            # Client should successfully converge with authority state
            assert sync_res.outcome in (SyncOutcome.APPLIED, SyncOutcome.CONFLICT, SyncOutcome.ALREADY_CURRENT)
            caps = await client_runtime.sync.get_node_capabilities(auth_node_id)
            assert "system.compute.v1" in caps


@pytest.mark.asyncio
async def test_revoked_node_cannot_bootstrap(tmp_path: Path) -> None:
    """Security verification: Revoked nodes are hard-rejected during bootstrap."""
    auth_dir = tmp_path / "auth"
    client_dir = tmp_path / "client"

    auth_settings = ShyamSettings(data_directory=auth_dir, discovery_enabled=False)
    client_settings = ShyamSettings(data_directory=client_dir, discovery_enabled=False)

    async with ShyamRuntime(auth_settings) as auth_runtime:
        async with ShyamRuntime(client_settings) as client_runtime:
            client_node_id = str(client_runtime.identity_manager.identity.node_id)

            # Revoke client identity in authority's trust store beforehand
            await auth_runtime.trust.revoke_trust(
                node_id=client_node_id,
                reason="Compromised credentials",
            )

            transport = RuntimeBootstrapTransport(auth_runtime)

            with pytest.raises(Exception, match="is REVOKED"):
                await client_runtime.bootstrap.execute_client_bootstrap(
                    authority_endpoint="inproc://auth",
                    transport=transport,
                )

            # Client should remain untrusted
            assert not await auth_runtime.trust.is_trusted(client_node_id)


@pytest.mark.asyncio
async def test_recovery_lifecycle_integration(tmp_path: Path) -> None:
    """Test device recovery after state loss."""
    node_dir = tmp_path / "recoverable_node"
    settings = ShyamSettings(data_directory=node_dir, discovery_enabled=False)

    async with ShyamRuntime(settings) as runtime:
        node_id = str(runtime.identity_manager.identity.node_id)

        # Scenario 1: State Lost, Identity Intact
        rec_req = RecoveryRequest(
            scenario=RecoveryScenario.STATE_LOST_IDENTITY_INTACT,
            existing_node_id=node_id,
        )
        res = await runtime.bootstrap.recover_device(rec_req)
        assert res.success
        assert res.new_node_id == node_id

        # Scenario 2: Identity Lost
        rec_req_lost = RecoveryRequest(
            scenario=RecoveryScenario.IDENTITY_LOST,
            existing_node_id=node_id,
        )
        res_lost = await runtime.bootstrap.recover_device(rec_req_lost)
        assert res_lost.success
        assert res_lost.new_node_id != node_id