# ADR-004: Provider Abstraction and Local Provider Registry

## Status

Accepted

## Context

In S3, we established formal capability modeling (`Capability` as "what can be done") and implemented a local `CapabilityRegistry` to track capabilities advertised by the local node. 

However, capabilities only describe abilities abstractly; they do not specify who or what component performs them, how they are managed, or how they are grouped for execution. To enable modularity (including future Zarya/Flux integrations and the local provider fabric), we need to introduce an abstraction that links capabilities to their specific implementations without coupling the Shyam core runtime to execution contexts, remote network protocols, or specific runner modules.

## Decision

We introduce the Provider Domain under `shyam.providers` to formalize the boundary:
* **Capability** = WHAT can be done (stable identifier, namespaced).
* **Provider** = WHO/HOW provides it (metadata, identifier, version, and a collection of referenced capability IDs).
* **Node** = WHERE the capability/provider exists.
* **Execution** = ACTUALLY performing the work (delegated to future workflows/navigation subsystems).

### Technical Details

1. **Decoupled Reference:** The `Provider` model references capabilities using a flat list of capability IDs (`tuple[str, ...]`) instead of nesting full `Capability` models. This prevents double-source-of-truth errors and keeps capability definitions strictly owned by the `CapabilityRegistry`.
2. **Local Registry:** We introduce an in-memory `ProviderRegistry` managed by the `ShyamRuntime` alongside the `CapabilityRegistry`.
3. **Query Engine Interface:** The `ProviderRegistry` exposes `find_by_capability(capability_id)` to resolve multiple providers offering the same capability.
4. **Lifecycle Events:** Registration, unregistration, and status updates emit domain events (`ProviderRegisteredEvent`, etc.) over the central async `EventBus`.

### Exclusions & Boundaries

To preserve strict focus and avoid scope creep:
* **No Execution:** Providers in S4 only describe and advertise metadata; they do not implement `.execute()` or `.invoke()`.
* **No External Adapters:** No Zarya or Flux adapters are implemented in this sprint.
* **No Persistence:** The `ProviderRegistry` is strictly in-memory, mirroring the `CapabilityRegistry` pattern.

## Consequences

### Positive
* **Clean Separation:** Deep decoupling makes future provider implementations (like Zarya desktop controls or Flux remote integrations) easy to plug in without modifying Shyam's core logic.
* **Multi-Provider Capability Queries:** S9's navigation system can now seamlessly query "which providers can perform `file.read`?" and receive both `local.filesystem` and a future remote provider.
* **Cohesive Events:** Integrating provider events directly into the centralized `EventBus` guarantees full traceability across node components.

### Negative / Deferred
* No remote provider network calls or remote registry sync (deferred to S8).
* Trust, signing, and permission modeling for registered providers are deferred to the security architecture.
