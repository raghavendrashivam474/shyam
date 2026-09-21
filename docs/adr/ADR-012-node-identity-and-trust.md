# ADR-012: Persistent Cryptographic Node Identity and Local Trust Model

## Status
Accepted

## Context
Prior to Sprint 13 (v0.13.0), Shyam tracked nodes purely via discovery (S8) and context aggregation (S12). A node was identified by a UUID-based `NodeIdentity` generated locally, but there was no mechanism to cryptographically authenticate a node or define trust relationships between nodes.

With state synchronization (S14), device bootstrap (S15), and cross-device work continuity (S16) upcoming, Shyam requires a foundation where:
1. Nodes possess persistent, asymmetric cryptographic identities capable of signing and verification.
2. Nodes maintain local, sovereign trust policies distinguishing trusted peers from unknown or revoked devices.
3. The distinction **Discovery ≠ Identity ≠ Trust** is strictly preserved.

## Decision
1. **Cryptographic Identity (`shyam.identity.crypto`)**:
   - Every Shyam node generates an **Ed25519** signing keypair on first startup.
   - Public identity is represented by `CryptoIdentity` (containing `node_id`, base64 public key, algorithm name, timestamp), which is safe for serialization and sharing across discovery.
   - Private key material is held exclusively in memory via `KeyPair` and persisted to local secure storage (`<data_dir>/crypto/private.key`). It is strictly forbidden from appearing in Pydantic models, JSON dumps, log lines, or events.

2. **Logical vs. Cryptographic Separation**:
   - `NodeIdentity.node_id` remains the primary logical identifier across S8–S12.
   - `CryptoIdentity` binds cryptographically to this `node_id`, allowing future verification (S14) without breaking existing discovery models.

3. **Local Trust Policy (`shyam.trust`)**:
   - Trust is local and unilateral: each node maintains its own `TrustStore` (`trust_store.json`).
   - States: `UNKNOWN`, `TRUSTED`, `REVOKED`.
   - Relationships: `NONE`, `PERSONAL`, `PEER`, `INFRASTRUCTURE`.
   - Nodes self-trust their local identity with `PERSONAL` relationship on initialization.
   - Domain events `TrustGrantedEvent` and `TrustRevokedEvent` notify the runtime of policy changes.

4. **Preserved Boundaries**:
   - Discovery (S8) remains responsible solely for "what nodes exist."
   - Navigator (S9), Workflow (S10), Composite (S11), and Context (S12) remain decoupled from trust logic. Discovery does not imply trust, and trust does not imply automatic execution.

## Consequences

### Positive
- Persistent Ed25519 cryptographic identity survived across runtime restarts.
- Strict security boundary preventing private key leakage into public models or logs.
- Unilateral local trust policy ready to authorize synchronization in S14.
- 100% backward compatibility with S0–S12 test suites.

### Negative / Tradeoffs
- Requires `cryptography>=42.0.0` dependency.
- Trust is initially local-only; bidirectional pairing/bootstrap flows will be required in S15.
