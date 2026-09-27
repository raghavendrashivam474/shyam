"""Smoke test demonstrating S17.5 programmatic ecosystem readiness querying."""

import asyncio
from shyam.core.config import ShyamSettings
from shyam.core.runtime import ShyamRuntime

async def main():
    settings = ShyamSettings(
        environment="local",
        readiness_poll_interval=1.0,
        discovery_enabled=False,
    )
    runtime = ShyamRuntime(settings=settings)
    print("Starting Shyam...")
    async with runtime:
        print(f"Runtime State: {runtime.status.value}")
        print(f"Ecosystem Readiness: {runtime.readiness.value.upper()}")
        
        # Give a moment for readiness tracker
        await asyncio.sleep(0.5)
        
        snap = runtime.get_readiness_snapshot()
        print("\n=== S17.5 ECOSYSTEM STATUS ===")
        for comp_name, comp_snap in snap.components.items():
            print(f"  [{comp_snap.state.value.upper():12s}] {comp_name}")
        print(f"================================")
        print(f"Aggregate: {snap.readiness.value.upper()}")
        print(f"Details:   {snap.details}")
        print("================================\n")

if __name__ == "__main__":
    asyncio.run(main())
