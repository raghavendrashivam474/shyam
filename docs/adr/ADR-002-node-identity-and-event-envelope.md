# ADR-002: Node Identity Separation, Event Envelope, and Local Peer Discovery

## Status
Proposed (S2 Implementation)

## Context
In S1, Shyam established a single-process runtime core with an ephemeral `runtime_id` (UUID generated on every startup) and an in-process asynchronous event bus (`EventBus`). 

S2 introduces multi-node awareness:
1. A Shyam process must have a persistent **Node Identity** (`NodeIdentity`) distinct from its ephemeral `RuntimeState.runtime_id`.
2. The event bus must wrap domain events in a transport-neutral **`EventEnvelope`** to decouple event dispatch from local in-memory representations without introducing external brokers.
3. The runtime must support pluggable **Local Peer Discovery** (`DiscoveryService`) running asynchronously in the background.

## Decision
1. **Node Identity Separation**: `NodeIdentity` contains `node_id`, `node_name`, `created_at`, `protocol_version`, persisted to `<data_dir>/identity/node.json`. Corrupted identity files fail fast with explicit error diagnostics.
2. **Event Envelope**: Domain events are wrapped in `EventEnvelope[T]` carrying `event_id`, `event_type`, `occurred_at`, `source_node_id`, `payload`, and optional `metadata`. The local bus handles both direct models and enveloped messages for backward compatibility.
3. **Transport-Neutral Discovery**: Discovery service is modeled via a clean async protocol/interface with an initial UDP multicast/broadcast local provider, fully isolated from runtime lifecycle transitions.

## Consequences
- Process restarts preserve node identity.
- Event structure is ready for future adapters without modifying handler signatures or adding NATS/Redis dependencies.
- Zero external broker dependencies are added in S2.
