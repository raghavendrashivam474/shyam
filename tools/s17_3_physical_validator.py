"""S17.3 Standalone Physical Two-Machine Validation CLI Tool.

Run on Machine A (source) or Machine B (target) to validate cross-device
work continuity across the physical network.

Usage:
  Machine B (Target):
    python tools/s17_3_physical_validator.py --role target --bind-ip 0.0.0.0 --port 54321

  Machine A (Source):
    python tools/s17_3_physical_validator.py --role source --target-ip 192.168.1.50
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shyam.continuity.models import ContinuityRequest, ContinuityState
from shyam.continuity.service import ContinuityService
from shyam.core.runtime import ShyamRuntime, ShyamSettings
from shyam.discovery.ecosystem_models import EcosystemNodeState
from shyam.navigation.models import NavigationConstraints
from shyam.trust.models import RelationshipType, TrustRecord, TrustStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("s17_3_validator")


async def run_target(args: argparse.Namespace) -> None:
    """Run target node daemon on Machine B."""
    data_dir = Path(tempfile.mkdtemp(prefix="shyam_target_node_"))
    settings = ShyamSettings(
        environment="local",
        data_directory=data_dir,
        log_level="INFO",
        runtime_name="machine-b-target",
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
    logger.info("==================================================")
    logger.info("TARGET NODE (MACHINE B) ONLINE")
    logger.info("Node ID:   %s", ident.node_id if ident else "unknown")
    logger.info("Node Name: %s", ident.node_name if ident else "unknown")
    logger.info("Zarya URL: %s", settings.zarya_url)
    logger.info("Flux URL:  %s", settings.flux_url)
    logger.info("Discovery Port: %d", args.port)
    logger.info("==================================================")
    logger.info("Listening for source announcements and continuity requests... (Ctrl+C to stop)")

    try:
        while True:
            await asyncio.sleep(2)
            snap = await rt.get_ecosystem_snapshot()
            remote_nodes = [nid for nid, n in snap.nodes.items() if not n.is_local]
            if remote_nodes:
                logger.info("Discovered peers on LAN: %s", remote_nodes)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down target node...")
    finally:
        await rt.stop()


async def run_source(args: argparse.Namespace) -> dict:
    """Run continuity validation probe on Machine A."""
    data_dir = Path(tempfile.mkdtemp(prefix="shyam_source_node_"))
    settings = ShyamSettings(
        environment="local",
        data_directory=data_dir,
        log_level="INFO",
        runtime_name="machine-a-source",
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
    source_node_id = str(source_ident.node_id) if source_ident else "unknown-source"

    evidence = {
        "timestamp": datetime.now(UTC).isoformat(),
        "source": {
            "node_id": source_node_id,
            "node_name": source_ident.node_name if source_ident else "machine-a-source",
        },
        "target": {},
        "discovery_pass": False,
        "trust_pass": False,
        "transfer_pass": False,
        "continuation_pass": False,
        "outcome": "UNKNOWN",
        "errors": [],
    }

    try:
        logger.info("[1/5] Discovering target node on LAN...")
        target_node_id = None
        target_node_meta = {}

        # Wait up to 10 seconds for discovery
        for _ in range(20):
            await asyncio.sleep(0.5)
            snap = await rt.get_ecosystem_snapshot()
            for nid, n in snap.nodes.items():
                if not n.is_local and n.state == EcosystemNodeState.AVAILABLE:
                    if args.target_ip and n.metadata.get("address") != args.target_ip:
                        continue
                    target_node_id = nid
                    target_node_meta = n.metadata
                    break
            if target_node_id:
                break

        if not target_node_id:
            msg = f"Target node not discovered on port {args.port} (target_ip={args.target_ip})"
            logger.error(msg)
            evidence["errors"].append(msg)
            return evidence

        evidence["discovery_pass"] = True
        evidence["target"] = {
            "node_id": target_node_id,
            "metadata": target_node_meta,
        }
        logger.info("Discovered target node: %s", target_node_id)

        # 2. Grant S13 Trust to Target Node
        logger.info("[2/5] Establishing S13 trust for target node %s...", target_node_id)
        await rt.trust_service.grant_trust(
            node_id=target_node_id,
            relationship=RelationshipType.PEER,
            alias="machine-b-physical-peer",
        )
        is_trusted = await rt.trust_service.is_trusted(target_node_id)
        if not is_trusted:
            msg = f"Failed to establish S13 trust for node {target_node_id}"
            logger.error(msg)
            evidence["errors"].append(msg)
            return evidence
        evidence["trust_pass"] = True

        # 3. Prepare Payload Artifact
        logger.info("[3/5] Preparing deterministic artifact payload...")
        artifact_path = data_dir / "s17_3_physical_work.json"
        artifact_content = json.dumps({
            "test_run": "S17.3_PHYSICAL_VALIDATION",
            "source_node": source_node_id,
            "target_node": target_node_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }).encode("utf-8")
        artifact_path.write_bytes(artifact_content)
        artifact_sha256 = hashlib.sha256(artifact_content).hexdigest()
        logger.info("Artifact SHA-256: %s", artifact_sha256)

        # 4. Invoke Continuity
        logger.info("[4/5] Executing Shyam S16 Continuity to target node...")
        req = ContinuityRequest(
            work_id=f"work-phys-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            source_device_id=source_node_id,
            portable_work={
                "task_name": "s17_3_physical_execution",
                "sha256": artifact_sha256,
            },
            artifact_paths=(str(artifact_path),),
            target_constraints=NavigationConstraints(preferred_node=target_node_id),
            continuity_intent="COPY",
        )

        session = await rt.continuity_service.request_continuity(req)
        evidence["continuity_session_id"] = session.continuity_id
        evidence["continuity_state"] = session.state.value

        if session.result:
            evidence["outcome"] = session.result.outcome.value
            evidence["result_reason"] = session.result.reason
            evidence["transfer_completed"] = session.result.transfer_completed
            evidence["reconstruction_completed"] = session.result.reconstruction_completed
            evidence["execution_completed"] = session.result.execution_completed

        if session.state == ContinuityState.COMPLETED:
            evidence["transfer_pass"] = True
            evidence["continuation_pass"] = True
            logger.info("✅ CONTINUITY OPERATION COMPLETED SUCCESSFULLY!")
        else:
            logger.warning("Continuity finished in non-completed state: %s", session.state)

    except Exception as exc:
        logger.exception("Physical continuity test encountered exception: %s", exc)
        evidence["errors"].append(str(exc))
    finally:
        await rt.stop()

    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="S17.3 Physical Continuity Validator")
    parser.add_argument("--role", choices=["source", "target"], required=True, help="Role: source (Node A) or target (Node B)")
    parser.add_argument("--port", type=int, default=54321, help="Discovery UDP port (default: 54321)")
    parser.add_argument("--target-ip", type=str, default=None, help="Target LAN IP filter (for source role)")
    parser.add_argument("--zarya-url", type=str, default="http://127.0.0.1:8765/ecosystem/v1", help="Zarya endpoint URL")
    parser.add_argument("--flux-url", type=str, default="http://127.0.0.1:9100/flux/v1", help="Flux endpoint URL")
    parser.add_argument("--output-json", type=str, default="s17_3_physical_evidence.json", help="Path to write JSON evidence")

    args = parser.parse_args()

    if args.role == "target":
        asyncio.run(run_target(args))
    else:
        evidence = asyncio.run(run_source(args))
        print("\n" + "=" * 60)
        print("S17.3 PHYSICAL VALIDATION EVIDENCE")
        print("=" * 60)
        print(json.dumps(evidence, indent=2))
        Path(args.output_json).write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        logger.info("Saved evidence report to %s", args.output_json)


if __name__ == "__main__":
    main()
