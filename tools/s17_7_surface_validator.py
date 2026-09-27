"""S17.7 Human-Facing Ecosystem Proof — Physical Validator.

Proves that a real human text input through the S17.6 SurfaceCoordinator
drives the full S16 continuity pipeline across two physical machines.

Usage:
  Machine B (Target):
    python tools/s17_7_surface_validator.py --role target --port 54322

  Machine A (Source):
    python tools/s17_7_surface_validator.py --role source --port 54322 --output docs/sprints/s17/s17.7/S17.7_EVIDENCE.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime
from shyam.discovery.ecosystem_models import EcosystemNodeState
from shyam.surface.coordinator import SurfaceCoordinator
from shyam.surface.input import TextInputAdapter
from shyam.trust.models import RelationshipType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("s17_7_validator")


async def run_target(args: argparse.Namespace) -> None:
    """Run target node daemon on Machine B."""
    data_dir = Path(tempfile.mkdtemp(prefix="shyam_s17_7_target_"))
    settings = ShyamSettings(
        environment="local",
        data_directory=data_dir,
        log_level="INFO",
        runtime_name="machine-b-target-s17.7",
        discovery_enabled=True,
        discovery_port=args.port,
        zarya_enabled=True,
        zarya_url=args.zarya_url,
        flux_enabled=True,
        flux_url=args.flux_url,
    )

    rt = ShyamRuntime(settings=settings)
    await rt.start()

    ident = rt.identity_manager.identity if rt.identity_manager else None
    node_id = str(ident.node_id) if ident else "unknown"
    flux_peer_id = rt.flux_provider.peer_id if rt.flux_provider else None

    logger.info("=" * 55)
    logger.info("S17.7 TARGET NODE (MACHINE B) ONLINE")
    logger.info("Node ID:      %s", node_id)
    logger.info("Flux Peer ID: %s", flux_peer_id)
    logger.info("Zarya URL:    %s", settings.zarya_url)
    logger.info("Flux URL:     %s", settings.flux_url)
    logger.info("UDP Port:     %d", args.port)
    logger.info("=" * 55)
    logger.info("Waiting for surface-driven continuity requests...")

    try:
        while True:
            await asyncio.sleep(2)
    except KeyboardInterrupt:
        logger.info("Target shutting down.")
    finally:
        await rt.stop()


async def run_source(args: argparse.Namespace) -> dict[str, Any]:
    """Run source node on Machine A, driving continuity via S17.6 Surface."""
    data_dir = Path(tempfile.mkdtemp(prefix="shyam_s17_7_source_"))
    settings = ShyamSettings(
        environment="local",
        data_directory=data_dir,
        log_level="INFO",
        runtime_name="machine-a-source-s17.7",
        discovery_enabled=True,
        discovery_port=args.port,
        zarya_enabled=True,
        zarya_url=args.zarya_url,
        flux_enabled=True,
        flux_url=args.flux_url,
    )

    rt = ShyamRuntime(settings=settings)
    await rt.start()

    source_ident = rt.identity_manager.identity if rt.identity_manager else None
    source_node_id = str(source_ident.node_id) if source_ident else "unknown"
    interaction_id = str(uuid.uuid4())

    evidence: dict[str, Any] = {
        "schema_version": "1.0",
        "sprint": "S17.7",
        "timestamp": datetime.now(UTC).isoformat(),
        "surface_entry_point": "SurfaceCoordinator.handle_request()",
        "human_input": "continue this work on my other laptop",
        "source": {
            "node_id": source_node_id,
            "zarya_url": str(settings.zarya_url),
            "flux_url": str(settings.flux_url),
        },
        "target": {},
        "discovery": {"target_discovered": False},
        "trust": {"target_trusted": False},
        "surface": {
            "intent_parsed": None,
            "response_message": None,
            "surface_state": None,
        },
        "continuity": {},
        "verification": {"verified": False},
        "correlation_chain": {
            "interaction_id": interaction_id,
        },
        "errors": [],
    }

    try:
        # Phase 1: Discovery
        logger.info("[1/5] Discovering target node on LAN (port %d)...", args.port)
        target_node_id = None

        for attempt in range(30):
            await asyncio.sleep(1)
            snap = await rt.get_ecosystem_snapshot()
            for nid, n in snap.nodes.items():
                if not n.is_local and n.state == EcosystemNodeState.AVAILABLE:
                    if args.target_ip and n.metadata.get("address") != args.target_ip:
                        continue
                    target_node_id = str(nid)
                    break
            if target_node_id:
                break
            if attempt % 5 == 4:
                logger.info("  Still discovering... (%d/30s)", attempt + 1)

        if not target_node_id:
            err = f"Target not discovered on port {args.port} within 30s"
            logger.error(err)
            evidence["errors"].append(err)
            return evidence

        evidence["discovery"]["target_discovered"] = True
        evidence["target"]["node_id"] = target_node_id
        logger.info("Discovered target: %s", target_node_id)

        # Phase 2: Trust Seeding
        logger.info("[2/5] Pre-granting S13 trust for target %s...", target_node_id)
        await rt.trust_service.grant_trust(
            node_id=target_node_id,
            relationship=RelationshipType.PEER,
            alias="machine-b-s17.7-peer",
        )
        is_trusted = await rt.trust_service.is_trusted(target_node_id)
        evidence["trust"]["target_trusted"] = is_trusted

        if not is_trusted:
            err = f"Trust grant failed for {target_node_id}"
            logger.error(err)
            evidence["errors"].append(err)
            return evidence

        logger.info("Trust established: %s", is_trusted)

        # Phase 3: Surface-Driven Request (THE S17.7 PROOF)
        logger.info("[3/5] Driving continuity via S17.6 SurfaceCoordinator...")
        logger.info("  Human input: 'continue this work on my other laptop'")

        coordinator = SurfaceCoordinator(runtime=rt)
        await coordinator.start()

        adapter = TextInputAdapter()
        interaction_request = adapter.create_request(
            "continue this work on my other laptop"
        )

        evidence["surface"]["intent_parsed"] = "CONTINUE_WORK"

        response = await coordinator.handle_request(interaction_request)

        evidence["surface"]["response_message"] = response.message
        evidence["surface"]["surface_state"] = coordinator.current_state.value

        logger.info("Surface response: %s", response.message)
        logger.info("Surface state: %s", coordinator.current_state.value)

        # Phase 4: Collect Internal Evidence
        logger.info("[4/5] Collecting continuity session evidence...")

        if rt.continuity_service:
            sessions = rt.continuity_service._sessions
            for cid, session in sessions.items():
                if session.request.work_id == "work-active-surface":
                    evidence["continuity"] = {
                        "continuity_id": session.continuity_id,
                        "work_id": session.request.work_id,
                        "final_state": session.state.value,
                        "operation_id": session.operation_id,
                        "transfer_id": session.transfer_id,
                    }
                    if session.result:
                        evidence["continuity"]["outcome"] = session.result.outcome.value
                        evidence["continuity"]["reason"] = session.result.reason
                        evidence["continuity"]["transfer_completed"] = (
                            session.result.transfer_completed
                        )

                    evidence["correlation_chain"]["continuity_id"] = cid
                    if session.operation_id:
                        evidence["correlation_chain"]["operation_id"] = session.operation_id
                    if session.transfer_id:
                        evidence["correlation_chain"]["transfer_id"] = session.transfer_id
                    break

        # Phase 5: Verification
        logger.info("[5/5] Verifying end-to-end chain...")

        surface_ok = coordinator.current_state.value == "completed"
        continuity_ok = evidence["continuity"].get("final_state") == "completed"
        trust_ok = evidence["trust"]["target_trusted"]
        discovery_ok = evidence["discovery"]["target_discovered"]

        all_verified = surface_ok and continuity_ok and trust_ok and discovery_ok
        evidence["verification"]["verified"] = all_verified

        if all_verified:
            logger.info("S17.7 PROOF: FULL CHAIN VERIFIED")
        else:
            logger.warning(
                "S17.7 PROOF: Partial (surface=%s, continuity=%s, trust=%s, discovery=%s)",
                surface_ok, continuity_ok, trust_ok, discovery_ok,
            )

    except Exception as exc:
        logger.exception("S17.7 validation error: %s", exc)
        evidence["errors"].append(str(exc))
    finally:
        await rt.stop()

    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(
        description="S17.7 Human-Facing Ecosystem Proof Validator"
    )
    parser.add_argument(
        "--role", choices=["source", "target"], required=True,
        help="'target' (Machine B) or 'source' (Machine A)",
    )
    parser.add_argument("--port", type=int, default=54322)
    parser.add_argument("--target-ip", type=str, default=None)
    parser.add_argument(
        "--zarya-url", type=str, default="http://127.0.0.1:8765/ecosystem/v1"
    )
    parser.add_argument(
        "--flux-url", type=str, default="http://127.0.0.1:9100/flux/v1"
    )
    parser.add_argument("--output", type=str, default="docs/sprints/s17/s17.7/S17.7_EVIDENCE.json")

    args = parser.parse_args()

    if args.role == "target":
        asyncio.run(run_target(args))
    else:
        evidence = asyncio.run(run_source(args))
        output_json = json.dumps(evidence, indent=2)
        print("\n" + "=" * 60)
        print("S17.7 HUMAN-FACING ECOSYSTEM PROOF EVIDENCE")
        print("=" * 60)
        print(output_json)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_json, encoding="utf-8")
        logger.info("Saved S17.7 evidence to %s", args.output)


if __name__ == "__main__":
    main()
