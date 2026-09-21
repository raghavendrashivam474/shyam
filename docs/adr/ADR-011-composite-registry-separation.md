# ADR-011: Separation of Composite Capability and Provider Capability Registries

## Context
In S3, Shyam introduced the CapabilityRegistry to track capabilities advertised by local nodes and remote peers. These represent raw, discoverable *abilities* (e.g., ile.read, ile.write) mapping directly to underlying execution provider adapters (local, Zarya, Flux).

In S11, we introduce Composite Capabilities (e.g., ile.copy), which are orchestrated sequences of existing capabilities. 

We considered two design options:
1. **Unified Registry**: Force composite definitions into the existing CapabilityRegistry.
2. **Segregated Registries**: Keep the primitive provider capabilities in CapabilityRegistry and introduce a dedicated CompositeCapabilityRegistry for composite recipes.

## Decision
We selected **Option 2 (Segregated Registries)**.

The CompositeCapabilityRegistry is implemented in src/shyam/composite/registry.py.

## Justification
1. **Conceptual Separation of Concerns**: Provider capabilities represent discoverable endpoints and network/device capabilities (interfaces). Composite capabilities represent workflow templates or recipes (orchestration logic). Mixing them complicates discovery, filtering, and query APIs.
2. **Validation Requirements**: Composites have strict structural validation requirements (e.g., ensuring step bindings reference valid inputs or preceding step outputs). A unified registry would require either overloading primitive models with composite validation logic or bypassing validation altogether.
3. **Execution Path Divergence**: Invoking a primitive capability requires direct S9 navigation and S10 execution. Invoking a composite capability requires step-by-step binding resolution, single-step workflow construction, and sequential execution. Separating their registries maintains pure SRP (Single Responsibility Principle) at the architecture boundary.

## Consequences
- The public ShyamRuntime exposes self.capabilities (primitive, discoverable capabilities) and self.composites (composite orchestration templates) separately.
- Invocation of composite capabilities runs through a dedicated ShyamRuntime.invoke_composite(...) method, preserving separate execution metrics and error hierarchies.
