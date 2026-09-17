# ADR-002: Node Identity Separation, Event Envelope, and Local Peer Discovery

## Status
Accepted

## Context
In S1, Shyam established a single-process runtime core with an ephemeral `runtime_id` (UUID generated on every startup) and an in-process asynchronous event bus (`EventBus`).

S2 introduced multi-node awareness:
1. A Shyam node process must have a persistent **Node Identity** (`NodeIdentity`) distinct from its ephemeral `RuntimeState.runtime_id`.
2. The event bus must wrap domain events in a transport-neutral **`EventEnvelope`** to decouple event dispatch from local in-memory representations without introducing external brokers.
3. The runtime must support pluggable, asynchronous **Local Peer Discovery** (`DiscoveryService`) running safely in the background.

## Decision
1. **Node Identity Separation**: `NodeIdentity` contains `node_id`, `node_name`, `created_at`, `protocol_version`, persisted to `<data_dir>/identity/node.json`. Corrupted identity files fail fast with explicit `IdentityCorruptionError` diagnostics.
2. **Event Envelope**: Domain events are wrapped in `EventEnvelope[T]` carrying `event_id`, `event_type`, `occurred_at`, `source_node_id`, `payload`, and optional `metadata`. The local bus seamlessly handles both direct models and enveloped messages for complete backward compatibility.
3. **Transport-Neutral Discovery**: Discovery service is modeled via an asynchronous UDP broadcast/listener provider running non-blocking background routines (`_announce_loop` and `_reap_loop`), fully managed through the `ShyamRuntime` lifecycle.

## Consequences
- Process restarts preserve node identity deterministically.
- Event structure is ready for future adapters without modifying subscriber handler signatures or adding NATS/Redis dependencies.
- Zero external broker dependencies were introduced in S2.
