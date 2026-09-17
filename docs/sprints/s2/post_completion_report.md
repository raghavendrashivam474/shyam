---

# 🟣 SHYAM — Sprint S2 Post-Completion Report

**To:** Senior Architect / Tech Lead
**From:** S2 Implementation
**Branch:** `feature/s2-node-identity-discovery`
**Baseline:** `v0.1` (S1 Runtime Core — 21 tests, frozen)
**Date:** 2026-09-17

---

## 1. Executive Summary

S2 is complete. The Shyam runtime now has a **persistent node identity**, a **transport-neutral event envelope**, and a **functional local peer discovery engine** — all running on zero new external dependencies.

| Metric | S1 Baseline | S2 Result |
|---|---|---|
| Tests | 21 passed | **39 passed** |
| Ruff violations | 0 | **0** |
| External dependencies added | — | **0** |
| S1 tests broken | — | **0** |
| Code coverage (src/shyam) | unmeasured | **92%** |
| New source modules | — | 7 files |
| New test modules | — | 4 files |

The one-line mission from the brief has been fulfilled:

> *S1 made Shyam a running runtime. S2 makes that runtime a recognizable, persistent Shyam node that can see its local peers.*

---

## 2. What Was Built

### 2.1 Persistent Node Identity (`src/shyam/identity/`)

**Problem S2 solves:** S1's `RuntimeState.runtime_id` is ephemeral — regenerated as a UUID on every process start. This makes it impossible to distinguish "same machine restarted" from "new machine joined."

**Implementation:**

- **`NodeIdentity`** (Pydantic model, `frozen=True`): Contains `node_id` (UUID), `node_name`, `created_at`, `protocol_version`. Minimal by design — no GPU/CPU/capability/Zarya/Flux fields.
- **`IdentityManager`**: Handles the full lifecycle:
  - First launch → generates UUID → persists atomically (write-to-tmp + rename) to `<data_dir>/identity/node.json`
  - Subsequent launches → loads and validates the same identity
  - Corrupted file → raises `IdentityCorruptionError` with explicit diagnostics (does **not** silently regenerate, which would cause identity splits)
- **Runtime ID ≠ Node ID** distinction is now structurally enforced. A process crash on Monday and restart on Tuesday produces a new `runtime_id` but the same `node_id`.

**Tests (6):** Model instantiation, immutability, first initialization, subsequent reload, corrupted JSON handling, invalid schema handling.

### 2.2 Transport-Neutral Event Envelope (`src/shyam/events/envelope.py`)

**Problem S2 solves:** S1's event bus dispatches raw Pydantic `Event` objects directly. This works for in-process pub/sub but creates a coupling problem when we eventually need to serialize events across network boundaries (NATS, gRPC, etc.). We need a wrapper that carries routing/metadata without polluting domain event schemas.

**Implementation:**

- **`EventEnvelope[T: Event]`**: Uses Python 3.13 native PEP 695 generic syntax (`class EventEnvelope[T: Event](BaseModel)`). Fields: `event_id`, `event_type`, `occurred_at`, `source_node_id`, `payload` (the actual `Event`), `metadata` (dict).
- **`EventBus` evolution**: The `publish()` method now handles two dispatch paths:
  - **Raw `Event` published** → delivered to `Event`-type subscribers as before, AND automatically wrapped in an `EventEnvelope` and delivered to `EventEnvelope` subscribers.
  - **`EventEnvelope` published** → the inner `payload` is extracted and delivered to `Event`-type subscribers, AND the envelope itself is delivered to `EventEnvelope` subscribers.
- **Result:** Complete backward compatibility. All 4 S1 event tests pass unchanged. No subscriber code needs to know whether events arrive raw or enveloped.

**Key design decision:** The envelope is transport-neutral. It contains no NATS-specific fields (`jetstream_sequence`, `consumer_name`, etc.). When a distributed broker is introduced in a future sprint, an adapter layer will map between `EventEnvelope` and the broker's native message format.

**Tests (3):** Envelope wrapping, enveloped-payload-to-raw-subscriber routing, raw-event-to-envelope-subscriber routing.

### 2.3 Local Peer Discovery (`src/shyam/discovery/`)

**Problem S2 solves:** Shyam nodes need to find each other on the local network. This is the foundation for all future multi-node orchestration.

**Implementation:**

- **`Peer`** (Pydantic model, `frozen=True`): `node_id`, `node_name`, `address`, `port`, `protocol_version`, `discovered_at`, `last_seen`, `metadata`. Has a `touch()` method that returns an immutable copy with updated `last_seen`.
- **`DiscoveryService`**: Fully asynchronous, built on `asyncio.DatagramProtocol` + `socket` (standard library only).
  - **Announce loop**: Periodically broadcasts a JSON payload containing the node's identity over UDP to the configured broadcast address.
  - **Listener**: Receives datagrams, parses peer announcements, ignores self-broadcasts.
  - **Peer state machine**: New peer → `PeerDiscoveredEvent`. Changed attributes → `PeerUpdatedEvent`. Silent `last_seen` refresh on repeated heartbeats.
  - **Reaper loop**: Periodically scans the peer map. Any peer whose `last_seen` exceeds the expiry threshold is removed and a `PeerLostEvent` is fired. The reaper's polling interval scales dynamically to `max(0.05, min(1.0, expiry / 3.0))` so it works correctly in both production (6s expiry → 1s poll) and test (0.3s expiry → 0.1s poll) configurations.
  - **Socket fallback**: If binding to `0.0.0.0` fails (common in CI/containers), falls back to `127.0.0.1` with a logged warning.
- **Discovery events**: `NodeIdentityReadyEvent`, `PeerDiscoveredEvent`, `PeerUpdatedEvent`, `PeerLostEvent` — all extend S1's `Event` base class.

**Tests (6):** Model instantiation, immutability, `touch()` copy semantics, event creation, service lifecycle (start/stop), full peer state machine (discover → update → expire → lost).

### 2.4 Runtime Integration (`src/shyam/core/runtime.py`)

**Changes to `ShyamRuntime`:**

- `start()` now initializes `IdentityManager`, loads/creates the persistent identity, publishes `NodeIdentityReadyEvent`, and launches `DiscoveryService` as a non-blocking background task.
- `stop()` shuts down the discovery service (cancels background tasks, closes UDP transport, clears peer map) before proceeding with the existing S1 shutdown sequence.
- Discovery failure during startup is caught by the existing error-handling path and transitions the runtime to `LifecycleState.ERROR`.
- A new `discovery_enabled` flag in `ShyamSettings` allows disabling discovery entirely (tested).

**No second lifecycle state machine was created.** Discovery is a component managed by the runtime, not a parallel runtime.

### 2.5 Configuration Extension (`src/shyam/core/config.py`)

Added four new fields to `ShyamSettings` (all with sensible defaults, `frozen=True` preserved):

| Field | Default | Purpose |
|---|---|---|
| `discovery_enabled` | `True` | Toggle local peer discovery |
| `discovery_port` | `54321` | UDP broadcast port |
| `discovery_interval` | `2.0` | Seconds between announcements |
| `discovery_expiry` | `6.0` | Seconds before peer is considered lost |

### 2.6 CLI Enrichment (`src/shyam/cli.py`)

The CLI startup banner now displays:

```
==================================================
  🟣 SHYAM RUNTIME ONLINE
  Runtime ID: <ephemeral UUID>
  Node ID:    <persistent UUID>
  Node Name:  shyam-core
  Discovery:  enabled
==================================================
```

### 2.7 Two-Node Integration Test (`tests/integration/test_two_node_discovery.py`)

The crown jewel of S2 verification. This test:

1. Starts **Node A** and **Node B** as independent `ShyamRuntime` instances sharing a UDP port.
2. Waits for mutual discovery (both nodes see each other).
3. Stops **Node B**.
4. Waits for **Node A**'s reaper to detect the departure.
5. Asserts `PeerLostEvent` was fired with Node B's identity.

This is the first meaningful end-to-end proof that two Shyam processes can recognize each other.

---

## 3. What Was NOT Built (Intentionally)

Per the S2 brief's non-negotiable exclusions:

| Excluded | Reason |
|---|---|
| Zarya integration | Later sprint |
| Flux integration | Later sprint |
| Capability registry | Later sprint |
| Provider system | Later sprint |
| Device registry | Later sprint |
| Hybrid Navigation | Much later |
| Workflow engine | Much later |
| Cloud communication | Shyam remains local-first |
| LLM integration | Not S2 |
| NATS / Redis / distributed broker | S2 is local-only |
| CRDT / synchronization | Not S2 |
| Full device discovery (BT/WiFi/USB) | S2 discovers Shyam peers only |

No silent architectural drift occurred. Every exclusion from the brief was respected.

---

## 4. Architectural Decisions

### ADR-002: Node Identity Separation, Event Envelope, and Local Peer Discovery

**Status:** Accepted

Key decisions recorded:

1. **Identity persistence via atomic file write** (tmp + rename) rather than SQLite or any database. Rationale: S2 is not the storage sprint. The existing S1 data directory mechanism is sufficient.
2. **PEP 695 generics** for `EventEnvelope[T: Event]` rather than `typing.Generic[T]` + `TypeVar`. Rationale: Python 3.13 is the minimum target; native syntax is cleaner and Ruff enforces it.
3. **Dual-dispatch event bus** rather than replacing the bus or requiring all subscribers to accept envelopes. Rationale: Preserves 100% backward compatibility with S1 code while enabling future envelope-aware subscribers.
4. **UDP broadcast** for local discovery rather than mDNS/Zeroconf. Rationale: Zero external dependencies. `asyncio.DatagramProtocol` provides everything needed. mDNS can be added as an alternative adapter later.
5. **Dynamic reaper interval** (`expiry / 3`) rather than hardcoded sleep. Rationale: Prevents test flakiness with short expiry values while keeping production CPU usage negligible.

---

## 5. Test Coverage Report

```
src/shyam/core/config.py          100%
src/shyam/core/lifecycle.py       100%
src/shyam/core/logging.py         100%
src/shyam/core/state.py           100%
src/shyam/core/runtime.py          90%  (error recovery paths)
src/shyam/identity/model.py       100%
src/shyam/identity/manager.py      92%  (I/O error paths)
src/shyam/events/bus.py            96%  (edge-case dispatch paths)
src/shyam/events/envelope.py      100%
src/shyam/discovery/model.py      100%
src/shyam/discovery/service.py     88%  (socket fallback, error logging)
src/shyam/cli.py                   78%  (signal handlers, main entry)
─────────────────────────────────────────
TOTAL                              92%
```

**Coverage gaps are honest:** The uncovered lines are primarily OS-level error handling (socket bind failures, signal handler edge cases, I/O exceptions during identity persistence). These are difficult to unit-test without mocking `socket` and `os` internals, and the brief explicitly warned against gaming coverage with trivial getter tests.

**Recommendation for S3:** Introduce a `pytest-cov` threshold of `--cov-fail-under=85` in `pyproject.toml` to prevent regression.

---

## 6. Known Limitations & Risks

| # | Limitation | Severity | Mitigation |
|---|---|---|---|
| 1 | **UDP broadcast doesn't cross subnets.** Nodes on different VLANs/subnets won't discover each other. | Low (S2 scope) | Expected. Hybrid Navigation (future sprint) will handle cross-network discovery. |
| 2 | **No discovery authentication.** Any process on the LAN can spoof a Shyam peer announcement. | Medium (future) | Acceptable for local-first S2. Future sprints should add HMAC signing or mTLS before any trust decisions. |
| 3 | **Single discovery port.** Two Shyam instances on the same machine must share a port or use different configs. | Low | Handled by `SO_REUSEADDR`. Tests use isolated ports. |
| 4 | **Identity file is plaintext JSON.** No encryption at rest. | Low (local-first) | Acceptable for S2. Future storage sprint should address secrets management. |
| 5 | **No graceful peer reconnection.** If a peer's IP changes (DHCP lease renewal), it appears as a new peer. | Low | The old entry will expire via reaper. Future sprints can add IP-change detection. |
| 6 | **Event bus is still in-process only.** The envelope is transport-ready but no adapter exists yet. | Expected | This is the entire point of S2's envelope — the adapter comes later. |

---

## 7. Dependency Audit

| Package | S1 | S2 | Change |
|---|---|---|---|
| `pydantic` | ✅ | ✅ | No version change |
| `fastapi` | unused | unused | Still under `api` extra |
| `uvicorn` | unused | unused | Still under `api` extra |
| **New packages** | — | **None** | Zero dependency creep |

All S2 functionality (UDP networking, JSON serialization, UUID generation, async task management) uses Python standard library exclusively.

---

## 8. Repository Hygiene

- `.gitattributes` added with `* text=auto eol=lf` normalization (resolves S1's recurring Windows CRLF warnings).
- All commits are on `feature/s2-node-identity-discovery` branch, cleanly separated from `main`.
- Commit history:

```
0ab909f feat(identity): implement NodeIdentity model and persistent IdentityManager (S2)
5a0d21b feat(events): introduce EventEnvelope with PEP 695 type parameters (S2)
0f3c4a2 feat(discovery): implement UDP-based peer DiscoveryService (S2)
5f8a324 feat(discovery): introduce Peer model and discovery domain events (S2)
ffb0645 feat(runtime): integrate persistent identity and background peer discovery (S2)
d3bbac2 test(integration): verify two-node mutual peer discovery and peer loss (S2)
1f9284f chore(s2): complete S2, update CLI banner, finalize ADR-002 and report
```

---

## 9. Recommendations for S3

Based on S2 implementation experience:

1. **Introduce coverage gate.** Add `--cov-fail-under=85` to `pyproject.toml` pytest config. S2's 92% coverage is a good baseline to protect.
2. **Storage sprint.** S2's identity persistence is intentionally minimal (single JSON file). S3 should establish a proper storage abstraction before more subsystems start writing files ad-hoc.
3. **Discovery authentication.** Before any sprint builds trust decisions on peer identity (Zarya, Flux), add HMAC-signed announcements to prevent LAN spoofing.
4. **Event bus adapter interface.** The `EventEnvelope` is ready. S3 or S4 should define the abstract `EventTransport` protocol that NATS/gRPC adapters will implement.
5. **Configuration validation.** `ShyamSettings` is frozen but doesn't validate cross-field constraints (e.g., `discovery_expiry` should be > `discovery_interval * 2`). Add Pydantic validators.
6. **Consider mDNS adapter.** UDP broadcast works for S2 but mDNS/Bonjour would be more robust for production local discovery. The `DiscoveryService` abstraction supports plugging in alternative transports.

---

## 10. Definition of Done — Verification Checklist

### Identity
- [x] Every Shyam installation has a persistent Node ID
- [x] Node ID survives process restart
- [x] Runtime ID and Node ID remain separate
- [x] Identity corruption is handled explicitly

### Event Architecture
- [x] `EventEnvelope` exists
- [x] Existing local event behavior still works (4/4 S1 event tests green)
- [x] Envelope is transport-neutral
- [x] No distributed broker introduced

### Discovery
- [x] Local Shyam peers can be discovered
- [x] Peer information is represented cleanly
- [x] Duplicate peers are handled (idempotent `last_seen` update)
- [x] Peer updates are handled (`PeerUpdatedEvent`)
- [x] Lost peers are detected (`PeerLostEvent` via reaper)
- [x] Discovery runs asynchronously (non-blocking)
- [x] Discovery shuts down cleanly

### Runtime
- [x] Runtime starts normally
- [x] Identity initializes correctly
- [x] Discovery starts without blocking startup
- [x] Runtime shutdown stops discovery
- [x] Existing lifecycle behavior remains intact (5/5 S1 runtime tests green)

### Quality
- [x] All 21 S1 tests remain green
- [x] 18 new S2 tests cover core behavior
- [x] Integration test demonstrates two-node mutual discovery
- [x] Ruff is clean (0 violations)
- [x] Coverage measured at 92%
- [x] `.gitattributes` added
- [x] ADR-002 documented and accepted

---

## 11. The Architectural Picture After S2

```
                         SHYAM
                           │
                 ┌─────────┴─────────┐
                 │                   │
              Runtime              Node
                 │                   │
        ┌────────┼────────┐          │
        │        │        │          │
      State   Lifecycle  Events    Identity
                          │            │
                     EventEnvelope     │
                                       ▼
                              Local Discovery
                                       │
                            ┌──────────┼──────────┐
                            ▼          ▼          ▼
                          Node A     Node B     Node C
```

**Not yet:** Zarya, Flux, AI, Navigation, Workflows, Cloud. Those come later, and S2's architecture is ready to support them without rework.

---

**S2 is done. The runtime knows what node it is, remembers that identity across restarts, and can see its local peers. Ship it.**