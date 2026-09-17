# ADR-003: Capability Model & Local Capability Registry

## Status
Accepted

## Date
2026-09-17

## Context
In S1, Shyam established its runtime core and lifecycle. In S2, Shyam established persistent Node Identity (NodeIdentity) and UDP local peer discovery (DiscoveryService).

With nodes identifiable and discoverable on a local network, Shyam needed a formal way to describe and reason about **what a node can do**. 

The fundamental architectural principle is:
\\\	ext
Capability != Provider != Node != Execution
\\\

A Capability describes an *ability* (e.g. \ile.read\, \screen.capture\), not the implementation providing it, the device hosting it, or the mechanism executing it.

## Decision

1. **Formal Capability Model (\Capability\):**
   - Implemented as a frozen (immutable) Pydantic model in \shyam.capabilities.model\.
   - Requires namespaced, dot-separated identifiers (e.g., \ile.read\, \shyam.runtime.inspect\).
   - Uses semantic versioning strings (\X.Y.Z\).
   - Holds extensible metadata and an \AvailabilityStatus\ (\REGISTERED\, \AVAILABLE\, \UNAVAILABLE\).
   - Completely decoupled from \NodeIdentity\, device info, and execution logic.

2. **Local In-Memory Registry (\CapabilityRegistry\):**
   - Implemented in \shyam.capabilities.registry\.
   - Thread-safe and asynchronous, maintaining \O(1)\ lookups by \capability_id\.
   - Explicit duplicate protection: raises \DuplicateCapabilityError\ on duplicates unless \overwrite=True\ is set.
   - Supports namespace prefix querying and availability status filtering.
   - Keeps state strictly in memory; no premature disk persistence or database complexity is introduced.

3. **Capability Domain Events & Envelope Integration:**
   - Emits \CapabilityRegisteredEvent\, \CapabilityUpdatedEvent\, and \CapabilityUnregisteredEvent\ over the existing \EventBus\.
   - All events are 100% compatible with S2's transport-neutral \EventEnvelope\.

4. **Runtime Introspection Baseline:**
   - \ShyamRuntime\ initializes the \CapabilityRegistry\ on startup and registers a default synthetic introspection capability (\shyam.runtime.inspect\).

## Consequences

### Positive
- Formal, machine-readable vocabulary for abilities without coupling to provider implementations.
- Zero new external dependencies (pure Python standard library + existing Pydantic).
- Local-first and lightweight; sets the stage for S4 (Provider Abstraction) and S5+ (Zarya/Flux adapters).

### Negative / Deferrals
- No distributed capability replication across nodes (deferred to ecosystem/discovery sprints).
- Capabilities are not yet executable (execution fabric arrives in later sprints).
- Registrations are ephemeral across process restarts (storage abstraction to be addressed if persistence is required).
