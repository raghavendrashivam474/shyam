# ADR-015: Cross-Device Work Continuity (S16)

## Status

**Proposed** — pending architecture confirmation

## Date

2026-09-24

## Context

Shyam S16 introduces cross-device work continuity: the ability for an
active piece of work on one trusted Shyam node to continue on another
trusted Shyam node.

S16 is a **continuity coordinator**, not a new execution engine, transfer
engine, or navigation system. It orchestrates existing sovereign subsystems:

- **S9** (HybridNavigator) for target selection
- **S12** (EcosystemContext) for ecosystem state projection
- **S13** (TrustService) for trust/identity verification
- **S14** (SyncService) for synchronized state consumption
- **Zarya N4** for target-side work continuation
- **Flux** for artifact transfer between nodes

## Architectural Gap Identified

### ZaryaProvider does not expose N4 continuation

**Current state:** The Shyam `ZaryaProvider` exposes a generic
`execute(tool_name, args)` method used by the S10 `ZaryaExecutor`.
There is no dedicated method for Zarya N4's `continue_portable_work()`
operation.

**Why this matters:** S16 must invoke N4 continuation as a first-class
provider operation, not as a generic tool call. The continuation pipeline
(VALIDATE → SUPPORT_CHECK → RESOLVE → AUTHORIZE → RECONSTRUCT → EXECUTE)
has distinct semantics, input types (`PortableWork`), and output types
(`ContinuationResult`) that do not map cleanly to the generic
`execute(tool, args)` pattern.

**Proposed minimal change:**

Add a `continue_work()` method to `ZaryaProvider` that accepts a
`PortableWork` representation (dict or JSON) and returns a structured
`ContinuationResult`. This method delegates to the underlying Zarya
client's N4 endpoint.

```python
# Proposed addition to ZaryaProvider
def continue_work(
    self,
    portable_work: dict[str, Any],
) -> ContinuationResult:
    """Invoke Zarya N4 continue_portable_work on the target node."""
    ...
```

This does not import Zarya internals into Shyam. The provider boundary
remains intact. The Zarya client handles serialization and HTTP transport.

### No new Flux capabilities needed

The existing Flux provider already exposes:

- **transfer(peer_id, artifact_path, ...)** — `flux.transfer.send`
- **get_transfer_status(transfer_id)** — `flux.transfer.status`
- **cancel_transfer(transfer_id)** — `flux.transfer.cancel`

These are sufficient for S16's first vertical slice (file-based work).

## Decision

1. S16 lives in `src/shyam/continuity/` as a new subsystem.
2. S16 consumes S9, S12, S13, S14, ZaryaProvider, and FluxProvider
   through their existing public contracts.
3. ZaryaProvider will be extended with continue_work() as the
   minimal change to support N4 continuation.
4. No new identity, trust, sync, navigation, or transfer subsystems
   will be created inside S16.
5. First vertical slice: file-based Zarya work continuity.
6. Source work is preserved (COPY semantics, not HANDOFF) for S16.

## Identity Model

S16 maintains strict identity separation:

| Identity | Owner | Meaning |
| :--- | :--- | :--- |
| work_id | Zarya N2 | Logical piece of work |
| operation_id | Zarya N4/S18 | Particular execution |
| device_id | S13 | Device identity |
| artifact_id | Zarya N3 | Particular artifact |
| transfer_id | Flux | Transfer operation |
| continuity_id | S16 | Continuity attempt |

## Lifecycle

```text
REQUESTED → VALIDATING → TARGET_SELECTED → AUTHORIZED →
PREPARING → TRANSFERRING → RECONSTRUCTING → CONTINUING →
VERIFYING → COMPLETED
```

Terminal states: `FAILED`, `CANCELLED`, `UNSUPPORTED`, `UNKNOWN`

## Consequences

### Positive

- Existing subsystems remain sovereign and unmodified
- Clear ownership boundaries prevent duplication
- Minimal provider extension keeps integration surface small

### Negative

- ZaryaProvider extension requires coordination with Zarya team
- S16 cannot be fully tested end-to-end until N4 is available on target

### Risks

- If Zarya N4 contract changes, S16 provider adapter must update
- Cross-system idempotency requires careful identity management

### Alternatives Considered

1. Use generic execute(tool, args) for N4: Rejected because
   continuation semantics (PortableWork in, ContinuationResult out)
   don't fit the tool/args pattern.
2. Build S16 as a workflow (S10): Rejected because continuity is
   a coordination concern, not a step-based execution plan.
3. Defer S16 until Zarya N4 is fully stable: Rejected because
   the provider abstraction lets us decouple S16 from N4 internals.
