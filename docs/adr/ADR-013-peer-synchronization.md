# ADR-013: Peer State Synchronization & Causality Tracking

## Status
Accepted (v0.14.0)

## Context
Following Sprint 13 (Persistent Node Identity and Local Trust Policy), Shyam nodes can cryptographically prove their identity and locally categorize remote nodes into trust relationships (TRUSTED, UNKNOWN, REVOKED).

Sprint 14 introduces peer synchronization so that trusted nodes can exchange, reconcile, and converge on observed ecosystem state facts without central cloud coordination, distributed database locks, or global clocks.

## Architectural Boundaries & Principles
1. **S8 Discovery Ownership**: S8 continues to own node discovery and availability heartbeats. S14 does not replace discovery.
2. **S12 State Ownership**: S12 EcosystemStateStore maintains local state truth. S14 synchronizes explicitly defined, non-sensitive state facts.
3. **S13 Identity & Trust**: S14 strictly gates all inbound state via SyncAuthenticator, verifying Ed25519 signatures and checking local trust status before state parsing.
4. **Transport Decoupling**: S14 defines a canonical wire format (SyncEnvelope) transported over existing connectivity layers (Flux/HTTP/Transport adapters) without embedding raw networking sockets into domain logic.

## Decision
1. **Canonical JSON Serialization (RFC 8785 subset)**: All signable payloads are deterministically sorted and minified prior to signing with Ed25519 keypairs.
2. **Per-Node Vector Clocks (NodeVersionMap)**: Independent monotonic counters per node enable deterministic causality classification (EQUAL, AHEAD, BEHIND, CONCURRENT).
3. **Component-wise Supremum Merge**: Merging two versions computes the component-wise supremum, eliminating last-writer-wins clobbering while resolving concurrent branches deterministically.
4. **Loop & Replay Prevention**: Message IDs and vector map comparisons ensure idempotent delivery and prevent infinite echo loops between synchronizing peers.

## Consequences
- **Positive**: Cryptographically secure, decentralized peer synchronization with zero external database dependencies.
- **Positive**: Strict preservation of S8, S12, and S13 ownership boundaries.
- **Future Integration**: S15 (Bootstrap) and S16 (Work Continuity) can leverage SyncService as the trusted data exchange substrate.
