# ADR 0001: Repository Foundation & Sovereign Boundary Architecture

## Status
Accepted

## Context
Shyam is designed as a local-first, decentralized orchestration layer for personal computing. It coordinates workflows across sovereign subsystems (such as Zarya for computer execution and Aryntra Flux for mesh connectivity). Without explicit architectural boundaries established from day zero, projects often suffer from architectural drift—accidentally re-implementing low-level transport mechanisms or execution internals inside the orchestration engine.

## Decision
1. **Three-Plane Architecture:** Establish Experience, Intelligence, and Execution planes.
2. **Sovereign Boundaries:**
   * **Zarya:** Authoritative boundary for computer work, sandboxing, safety, and outcome verification. Shyam requests bounded actions and consumes verified outcomes.
   * **Aryntra Flux:** Authoritative boundary for peer discovery, path evaluation, transport protocols (QUIC/TCP/BLE), chunking, and resume integrity. Shyam requests high-level data movement.
3. **Repository Layout:** Separate application entry points (`apps/`), shared packages (`packages/`), core source (`src/shyam/`), tests (`tests/`), and documentation (`docs/`).
4. **Milestone Discipline:** Strictly prohibit premature implementation of future milestone abstractions (S1-S16) during milestone S0.

## Alternatives Considered
* *Monolithic internal implementation:* Embedding transport and execution logic directly inside Shyam. (Rejected: Destroys modularity and duplicates existing sovereign systems).
* *Single-directory flat structure:* (Rejected: Fails to enforce separation between core engine, packages, and application binaries).

## Consequences
* **Positive:** Clear, immutable boundaries between orchestration, execution, and transport. Reproducible development environment and zero architectural ambiguity for contributors.
* **Negative:** Requires strict discipline and adapter layers to bridge sovereign systems.

## Migration / Compatibility
Initial baseline established at Milestone S0 (`v0.0`).
