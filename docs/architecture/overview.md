# Shyam Architecture Overview

## 1. System Intent

Shyam is a **local-first, decentralized personal computing ecosystem and orchestration layer**.

Its core responsibility is to discover, resolve, and compose capabilities exposed by sovereign products and trusted devices across an individual's personal computing environment.

```text
                    SHYAM
          Personal Computing Ecosystem
                       │
                Hybrid Navigation
                       │
          ┌────────────┼────────────┐
          │            │            │
        Zarya         Flux      Other Providers
          │            │            │
       Execution   Connectivity   Capabilities
          │            │            │
          └────────────┼────────────┘
                       │
                Trusted Devices
```

## 2. Layered Architectural Planes

>Shyam organizes responsibilities across three discrete planes:

```text
┌─────────────────────────────────────────────────────────┐
│                    EXPERIENCE PLANE                     │
│  User Intent  │  API  │  UI Shell  │  External Clients  │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│                   INTELLIGENCE PLANE                    │
│  Hybrid Navigator      │  Capability Resolver           │
│  Workflow Coordinator  │  Context Continuity Manager    │
│  Policy Engine         │  Ecosystem State               │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│                    EXECUTION PLANE                      │
│  Provider SDK    │  Zarya Adapter   │  Flux Adapter     │
│  Device Agents   │  Custom Extension Adapters           │
└─────────────────────────────────────────────────────────┘
```

### Experience Plane

- Ingests human and programmatic intent.
- Surfaces system-wide capabilities, workflow progress, and device availability.
- Agnostic to how tasks are physically executed or routed.

### Intelligence Plane

- Hybrid Navigator: Evaluates available local/remote capabilities and determines optimal resolution paths.
- Capability Resolver: Indexes provider capabilities dynamically without hardcoding implementations.
- Workflow Coordinator: Manages multi-step, multi-device DAG execution.
- Context Manager: Preserves situational context across device transitions.
- Policy Engine: Enforces access control, approval requirements, and safety boundaries.

### Execution Plane

- Bridges the Intelligence Plane with sovereign systems through discrete adapter contracts.
- Interacts with Zarya for verified computer work.
- Interacts with Aryntra Flux for mesh routing and data movement.

## 3. Clear Boundaries of Ownership

### What Shyam Owns

- User intent decomposition into ecosystem workflows.
- Dynamic capability discovery across connected providers.
- Provider and device selection based on policy, proximity, and health.
- Multi-device workflow lifecycle coordination.
- Unified situational context continuity.
- Ecosystem-level access control and delegation policies.
- Global ecosystem topology awareness.

### What Shyam Does NOT Own

- **Zarya Internals**: Shyam does not execute desktop actions, inspect OS window hierarchies, 
  bypass safety rails, or fake execution outcomes.
- **Flux Internals**: Shyam does not manage raw network sockets, TCP/QUIC connections, packet chunking, 
  retry loops, or path probing.
- **OS Execution Mechanics**: Shyam delegates low-level process execution to dedicated sovereign agents.
- **Product Databases**: Shyam does not manipulate internal databases of sovereign systems; all coordination 
  occurs via explicit contracts.

## 4. Fundamental Rules for Contributors

1. Never absorb sovereign subsystems: If a capability belongs to Zarya (execution) or Flux (transport), 
   Shyam must consume it via an adapter contract, never by re-implementing it.
2. Preserve sovereign authority: Shyam cannot override Zarya's security/safety rejection or force transfers 
   when Flux determines no viable path exists.
3. Local-first autonomy: Every Shyam instance must function locally on isolated hardware without 
   requiring mandatory centralized cloud connectivity.
