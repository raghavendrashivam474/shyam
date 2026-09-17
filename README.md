# Shyam

> **Local-first, decentralized personal computing ecosystem and orchestration layer.**

Shyam discovers, coordinates, and composes capabilities exposed by independent sovereign products and trusted devices across a personal computing mesh.

---

## 1. Vision & Core Principle

Shyam acts as the orchestrator of personal computing capabilities without absorbing the specialized execution or transport domains of its underlying systems.

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

### Sovereign Boundaries

* Shyam orchestrates. Zarya executes and verifies.
* Shyam decides what needs to reach where. Flux decides how it gets there.
* Shyam does not absorb the internals of Zarya, Flux, or any provider.

## 2. Sovereign Products

### Zarya (Execution Substrate)

- Platform for personal desktop agents, computer work, and verified tool execution.
- **Authoritative Boundary**: Intent → Action → Observation → Verification → Outcome.
- **Ownership**: Computer execution, execution state, local authorization, safety sandboxing, artifact state, and verification.
- Rule: Shyam requests bounded work from Zarya; Shyam never bypasses Zarya's authorization, safety checks, or verification.

### Aryntra Flux (Connectivity Substrate)

- Substrate for mesh connectivity and resilient data movement.
- Ownership: Peer discovery, device identity, path discovery & health, path selection, multiplexed sessions, 
  transport (TCP/QUIC/- BLE), chunking, transfer integrity, and resume capabilities.
- Rule: Shyam expresses high-level data movement intent (e.g., "Send artifact X to Peer Y"); Flux handles all 
  transport mechanics, chunking, and retry logic.

## 3. Architecture Overview
```text
Experience Plane
────────────────────────────────
User Intent | API | UI | External Clients
             │
             ▼
Intelligence Plane
────────────────────────────────
Hybrid Navigator | Capability Resolver | Workflow Engine
Context Manager  | Policy Engine
             │
             ▼
Execution Plane
────────────────────────────────
Provider SDK | Zarya Adapter | Flux Adapter | Device Agents
```

## 4. Roadmap
```
Milestone    Tag    Focus
S0    v0.0    Foundation (Current)
S1    v0.1    Runtime Skeleton
S2    v0.2    Capability Model
S3    v0.3    Provider System
S4    v0.4    Hybrid Navigation
S5    v0.5    Zarya Integration
S6    v0.6    Flux Integration
S7    v0.7    First Composite Workflow
S8    v0.8    Ecosystem State
S9    v0.9    Shyam Node
S10    v0.10    Decentralized Synchronization
S11    v0.11    Recovery & Reconstitution
S12    v0.12    Trust & Policy
S13    v0.13    Context Continuity
S14    v0.14    Dynamic Hybrid Navigation
S15    v0.15    Ecosystem Hardening
S16    v0.16    Shyam V0 Release
```

## 5. Current Milestone Status

* Milestone: S0 — Foundation
* Target Tag: v0.0
* State: Repository structure, architectural boundary documentation, and package metadata established. 
  No runtime engines or capability mockups are prematurely implemented.

## 6. Repository Layout
```text
shyam/
├── apps/               # Application entry points (e.g., shyam-core)
├── packages/           # Modular workspace packages (contracts, capabilities, transport)
├── src/shyam/          # Core Shyam source tree
│   ├── api/            # API definitions
│   ├── capabilities/   # Capability catalog & descriptors
│   ├── context/        # Context management & state continuity
│   ├── core/           # Core runtime configuration & abstractions
│   ├── events/         # Event bus & lifecycle definitions
│   ├── identity/       # Identity & cryptographic bindings
│   ├── navigation/     # Hybrid navigation engine
│   ├── policy/         # Policy enforcement & security bounds
│   ├── providers/      # Provider adapters (Zarya, Flux, custom)
│   ├── storage/        # Persistence abstractions
│   └── workflow/       # Multi-step workflow orchestration
├── tests/              # Unit, integration, and contract tests
├── docs/               # Architecture, ADRs, integration boundaries, development guides
├── scripts/            # Development, build, and deployment automation
└── examples/           # Integration & orchestration examples
```

## 7. Development Setup

### Prerequisites

- Python 3.13+
- uv or standard Python venv

### Installation
```Bash

# Clone the repository
git clone https://github.com/<owner>/shyam.git
cd shyam

# Set up virtual environment
python -m venv .venv

# Activate environment (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

## 8. 

- [Architecture Overview](docs/architecture/overview.md)
- [Zarya Integration Boundary](docs/architecture/zarya-integration-boundary.md)
- [Aryntra Flux Integration Boundary](docs/architecture/flux-integration-boundary.md)
- [Development Setup Guide](docs/development/development-setup.md)
- [Repository Guidelines](docs/development/repository-guidelines.md)
- [Contributing Guidelines](docs/development/contributing-guidelines.md)
- [Architectural Decision Records (ADR)](docs/development/architectural-decision-records.md)

## 9. 

> MIT License. See LICENSE for details.
