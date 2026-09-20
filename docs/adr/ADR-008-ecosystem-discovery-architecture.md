# ADR-008: Ecosystem Discovery Architecture

* **Status**: Proposed
* **Date**: 2026-09-20
* **Sprints**: S8 — Ecosystem Discovery
* **Author**: Shyam Developer Team

## 1. Context and Problem Statement

Prior to S8, the Shyam core runtime was capable of communicating with individual, sovereign providers (Local Provider Fabric in S5, Zarya EIP-1 in S6, and Aryntra Flux Gateway in S7). It also had a low-level, UDP-based local peer discovery mechanism (S2) designed strictly for raw local-network node-announcements.

However, Shyam lacked a **provider-independent, normalized representation of what computing resources exist in its local ecosystem**. 

Without this representation, Shyam could not answer fundamental questions such as:
1. What nodes (local and remote) currently exist in the available ecosystem?
2. What providers are currently active on each of those nodes?
3. What explicit capabilities do those providers expose, and what is their version/availability?
4. How is the overall reachability or freshness of those entities tracked?

To bridge the gap between low-level communication and the future **S9 Hybrid Navigator** (which will decide *where* to route specific intents), Shyam required a clean, locally-maintained map of the surrounding ecosystem.

## 2. Decision and Architectural Principles

We introduced an **Ecosystem Discovery** layer (`shyam.discovery.ecosystem_*`) residing within the Shyam runtime that maintains a unified in-memory registry of discovered nodes, providers, and capabilities.

### 2.1 Separation of Concerns

We enforce strict separation between three core ecosystem concepts:

* **Provider**: Answers *"How do I communicate with this product/service?"* (owned by S4–S7).
* **Discovery**: Answers *"What products/services/nodes are currently known to exist?"* (owned by S8).
* **Navigation**: Answers *"Which available provider/node/path should satisfy this intent?"* (deferred to S9).

```text
Provider  ≠  Discovery  ≠  Navigation
```

### 2.2 Hard Provider Boundaries

Ecosystem Discovery operates strictly as a consumer of existing public provider interfaces:

   1. Local Node & Fabric: Consumes LocalProviderFabric, ProviderRegistry, and CapabilityRegistry.
   2. Zarya Sovereign Agent: Consumes ZaryaProvider.descriptor and ZaryaProvider.capability_definitions. It does NOT 
       interact with Zarya internal memory or bypass the EIP-1 contract.
   3. Flux Gateway: Consumes FluxProvider.discover_peers() and FluxProvider.descriptor. It does NOT import flux_core or 
       duplicate peer-routing logic.
   4. Shyam UDP Peers: Ingests raw network Peer models emitted by the low-level UDP DiscoveryService.

## 3. Domain Model and State Semantics

### 3.1 Core Normalized Entities

* **`DiscoveredCapability`**: Normalized capability descriptor (`capability_id`, `name`, `version`, `description`, `availability`).
* **`DiscoveredProvider`**: Normalized provider descriptor (`provider_id`, `name`, `version`, `capabilities: tuple[DiscoveredCapability, ...]`, `status: AvailabilityStatus`, `metadata`, `last_seen`).
* **`DiscoveredNode`**: Normalized ecosystem node (`node_id`, `node_name`, `state: EcosystemNodeState`, `is_local: bool`, `protocol_version`, `providers: dict[str, DiscoveredProvider]`, `metadata`, `first_seen`, `last_seen`).
* **`EcosystemSnapshot`**: Point-in-time immutable capture of the discovered ecosystem (`timestamp`, `local_node_id`, `nodes: dict[str, DiscoveredNode]`).

### 3.2 Normalized Node Lifecycle States (`EcosystemNodeState`)

* **`KNOWN`**: Node is recorded but reachability or active communication has not been actively verified.
* **`AVAILABLE`**: Node is actively reachable, responsive, and ready to receive capability queries or delegations.
* **`UNAVAILABLE`**: Node was previously known or reached but is currently unreachable (e.g., failed heartbeat, connection refused).
* **`STALE`**: Node has not been observed or refreshed within the freshness window (`stale_threshold_secs`), pending active reconciliation.

## 4. Discovery Lifecycle and Staleness Reconciliation

Discovery is deterministic, local-first, and does not require a distributed background daemon or external database:

1. **Local Node Registration**: On runtime start, the local node is registered as `AVAILABLE` with all locally loaded providers and explicitly registered capabilities. Local nodes are exempted from staleness expiration.
2. **Provider Discovery & Ingestion**:
   - Local providers from `LocalProviderFabric` are ingested.
   - Connected `ZaryaProvider` tools are normalized and registered.
   - Discovered mesh peers from `FluxProvider.discover_peers()` are normalized as remote nodes.
3. **UDP Peer Ingestion**: When the S2 UDP peer discovery detects a remote node announcement, the node is normalized into the `EcosystemRegistry`.
4. **Staleness Reconciliation**: Inactivity exceeding `stale_threshold_secs` transitions remote nodes from `AVAILABLE` to `STALE`, emitting domain notifications without deleting historical knowledge.

## 5. Ecosystem Domain Events

All state transitions emit typed domain events on the shared `EventBus`:

* `EcosystemNodeDiscoveredEvent`: Emitted when a new node is discovered for the first time.
* `EcosystemNodeUpdatedEvent`: Emitted when a node's state, provider map, or metadata changes.
* `EcosystemNodeStaleEvent`: Emitted when a remote node exceeds the freshness timeout.
* `EcosystemNodeLostEvent`: Emitted when a node is explicitly removed from the registry.

## 6. Consequences and Future S9 Compatibility

### Positive
* **Decoupled Architecture**: Navigation algorithms (S9) can query `EcosystemRegistry` or `get_ecosystem_snapshot()` without knowing the underlying transport (Zarya EIP-1 vs Flux Gateway vs UDP).
* **Provider Agnostic**: Adding new provider types in the future will only require defining a normalizer into `DiscoveredProvider` without modifying the core discovery layer.
* **100% Backward Compatible**: Preserved all existing S0–S7 contracts, runtime semantics, and the 184-test baseline.

### Negative / Limitations
* Discovery state is currently held in-memory per node (no distributed consensus or cross-node synchronization — explicitly deferred to S14).
* S8 does not evaluate trust or identity certificates between nodes (deferred to S13).
