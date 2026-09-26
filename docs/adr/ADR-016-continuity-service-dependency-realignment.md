# ADR-016: S16 Continuity Service Dependency Realignment

## Status
Accepted

## Date
2026-09-25

## Context
During S17.1 physical and integration validation across real multi-node instances, execution of `ContinuityService.request_continuity()` failed in both the target selection and trust verification stages when running against concrete `EcosystemRegistry` (S8) and `TrustService` (S13) instances.

Analysis revealed an interface divergence introduced during S16 development:
1. S16 `ContinuityService._select_target()` called `self._registry.snapshot` (assuming a property), whereas authoritative S8 `EcosystemRegistry` defines `create_snapshot(local_node_id: str = "") -> EcosystemSnapshot`.
2. S16 `ContinuityService._verify_trust()` called `self._trust.get_relationship()` synchronously, whereas authoritative S13 `TrustService` defines `async def get_record(node_id: str) -> TrustRecord`.
3. S16 unit tests passed in isolation because mock objects were configured to conform to S16's assumed interface rather than the authoritative S8/S13 contracts.

## Decision
Align `ContinuityService` with authoritative S8 and S13 contracts:
1. In `ContinuityService._select_target()`, replace `self._registry.snapshot` with `self._registry.create_snapshot()`.
2. In `ContinuityService._verify_trust()`, replace `self._trust.get_relationship()` with `await self._trust.get_record(session.target.device_id)`.
3. Update `tests/unit/test_s16_service.py` to mock the authoritative signatures (`create_snapshot` and `AsyncMock` for `get_record`).

## Consequences
* **Positive:** Real multi-node runtimes execute without mock shims. S8 and S13 remain authoritative owners of discovery and trust.
* **Compatibility:** No external breaking changes to public APIs.
* **Test Coverage:** All unit tests and multi-node integration tests pass.
