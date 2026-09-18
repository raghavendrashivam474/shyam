# ADR-005: Local Provider Fabric

## Status

Accepted

## Context

Sprint 4 (ADR-004) established the abstract representation of Provider and implemented the ProviderRegistry as an async, event-aware, in-memory repository on the local node. However, this registry remained intentionally empty.

Sprint 5 transitions Shyam from pure metadata representation to possessing its first concrete local provider implementations, requiring a clean subsystem to discover, construct, validate, initialize, and manage these components at runtime.

## Decision

We establish the **Local Provider Fabric** (LocalProviderFabric) alongside the existing registries in the core ShyamRuntime.

```text

                SHYAM RUNTIME
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
  CapabilityRegistry      LocalProviderFabric
                                 │
                                 ▼
                         ProviderRegistry
                                 │
                     ┌───────────┴───────────┐
                     ▼                       ▼
             local.filesystem         [other approved
                 Provider              local provider]
                     │
                     ├── file.read
                     ├── file.write
                     └── file.list
```

### 1. Concrete Local Provider Contract

> We define LocalProvider as an abstract base class. It owns a stable descriptor property representing the canonical Provider metadata. It exposes:
- capability_definitions: Explicit list of Capability domain models to be registered at startup.
- initialize(): Async resource setup hook.
- shutdown(): Async resource teardown hook.

### 2. Initial Provider Set
We introduce the local.filesystem provider as the first concrete implementation. It advertises three explicit capabilities:
- File.read
- File.write
- File.list

These are defined as formal, explicit Capability objects under FILESYSTEM_CAPABILITY_DEFINITIONS and are registered by the fabric at startup.

### 3. No Auto-Invention of Capabilities
We explicitly prohibit reflection, dynamic class introspection, or heuristic string parsing to generate capabilities. Capabilities remain explicit, first-class domain objects. If a provider references capability IDs for which it does not supply formal definitions, those IDs are left unregistered (preserving ADR-004's boundary where a provider may reference unregistered capabilities).

### 4. Provider Lifecycle and Status Transitions
The local fabric manages the state transitions of concrete providers cleanly:
- **Construction**: Created with status REGISTERED.
- **Pre-Initialization**: Registered in the ProviderRegistry with status REGISTERED.
- **Successful Init**: Upgraded to AVAILABLE in the registry.
- **Failed Init**: Re-registered with status UNAVAILABLE.
- **Teardown**: Gracefully calls shutdown() on each provider during runtime stop.

### 5. Non-Blocking Infrastructure Failure Policy
If a local provider fails to initialize, the fabric catches the exception, registers the provider as UNAVAILABLE, and allows the runtime startup to proceed. Local providers are non-blocking infrastructure, not critical process identity.

### 6. Execution Boundary Protection
The Local Provider Fabric and the LocalProvider implementations remain **strictly metadata-aware and resource-aware**. They do not provide execution methods (execute, 
ead, write). All invocation and routing concerns are deferred to the workflow and execution layers of future sprints.

## Consequences

- The ProviderRegistry is populated with actual, validated, local providers at runtime startup.
- Baseline integration tests are updated to assert the presence of local.filesystem and its associated capabilities (4 capabilities, 1 provider post-startup).
- There is 0% coupling to any remote systems or plugin download engines.
- No third-party dependencies are introduced.

## Deferred / Out of Scope

- Remote provider representation, Zarya integration, Flux integration.
- Distributed/ecosystem discovery.
- Provider selection, navigation, and intent routing.
- Worker execution engines.
- Provider health-monitoring/watchdog daemons.
- Persistent registry storage.
